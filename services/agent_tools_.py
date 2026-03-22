
from databricks import sql
from typing import Annotated
from config import settings,medical_codes,read_sohea_mapping_file,tooth_codes
from langchain.agents import tool
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import VectorizedQuery
from langchain_openai import  AzureOpenAIEmbeddings
import httpx
import json
import threading
from services.common.utils import logger
http_client = httpx.Client(verify=False)

"""
Langchain azure openai embeddings
"""
embeddings_connector = AzureOpenAIEmbeddings(
    azure_endpoint=settings.LLM_Config['embedding']['endpoint'],
    api_key=settings.LLM_Config['embedding']['subscription_key'],
    api_version=settings.LLM_Config['embedding']['api_version'],
    model=settings.LLM_Config['embedding']['model_name'],
    http_client=httpx.Client(verify=False)
)

'''
Method to execute generated sql query (With Client-Side 3-Minute Kill Switch)
'''
def sql_query_executor(sql_query):
    # Step 1: Establish Connection
    try:
        databricks_connection = sql.connect(
            server_hostname=settings.dbhostname,
            http_path=settings.sqlurl,
            access_token=settings.dbaccesstoken,
            verify=False
        )
        cursor = databricks_connection.cursor()
    except Exception as connection_error:
        logger_message = f"Databricks: Connection Error: {str(connection_error)}"
        print(logger_message)
        logger.error(logger_message)
        return  logger_message

    # Step 2: Define the Client-Side Kill Switch
    def cancel_query():
        try:
            logger_message = "Databricks: ⚠️ 3-Minute Timeout Reached. Cancelling Databricks query from Python..."
            print(logger_message)
            logger.error(logger_message)
            cursor.cancel()
            # Destroy the connection  
            databricks_connection.close()
        except Exception:
            pass

    # Initialize a 180-second (3 minute) timer
    timeout_timer = threading.Timer(180.0, cancel_query)

    try:
        # Step 3: Start Client-Side Timer (Protects your Python/FastAPI server)
        timeout_timer.start()
        
        # Step 4: Execute the LLM's Query
        cursor.execute(sql_query)
        results = cursor.fetchall()
        return results

    except Exception as e:
        error_msg = str(e).lower()
        # Catch Python cancellation exceptions
        if "cancel" in error_msg or "interrupt" in error_msg or "timeout" in error_msg:
            logger_message = "Databricks: Query was cancelled due to exceeding the 3-minute limit. This is likely due to a long-running query or one with massive CROSS JOINs or missing ON conditions. Please review and optimize your query."
            print(logger_message)
            logger.error(logger_message)
            return logger_message
        logger_message = f"Databricks: Error executing query: {str(e)}"
        print(logger_message)
        logger.error(logger_message)
        return logger_message

    finally:
        # Step 5: Safe Cleanup
        timeout_timer.cancel()
        
        try:
            cursor.close()
        except Exception as e:
            logger_message = f"Databricks: Error closing cursor: {str(e)}"
            print(logger_message)
            logger.error(logger_message)
            
        try:
            databricks_connection.close()
        except Exception as cleanup_error:
            logger_message = f"Databricks: Error closing connection: {str(cleanup_error)}"
            print(logger_message)
            logger.error(logger_message)
    

@tool
def fetch_record(sql_query: Annotated[str, "SQL Query to fetch records from the database."]):
    """
    Executes the provided SQL query against the connected database and returns the fetched results.

    Args:
        sql_query (str): The SQL query string to execute.

    Returns:
        list: A list of rows fetched from the database or an error message string.
    """
    return sql_query_executor(sql_query)
def catalog_query_exec(table_name):
    query = f'''
    DESCRIBE
    {table_name}
    '''
    return sql_query_executor(query)

'''
Method to execure AI Search query
'''
def run_query(index_name_,reqbody,select_fields_,top_=50):
    search_client = SearchClient(
        endpoint=settings.search_endpoint,
        index_name=index_name_,
        credential=AzureKeyCredential(settings.search_key)
    )

    embedded_query = embeddings_connector.embed_query(reqbody['query'])

    # Vectorized query
    vector_query = VectorizedQuery(
        vector=embedded_query,
        k_nearest_neighbors=20,
        fields="content_vector"
    )
    formatted_context = []
    try:
        if reqbody['datasource'].lower()=='research':
            datasource_filter  = f"datasource eq '{reqbody['datasource'].lower()}'"
        else:
            datasource_filter  = f"datasource eq '{reqbody['datasource'].upper()}'"
        targettables = reqbody.get('selected_table_name', [])
        targetfilenames = reqbody.get('filenames',[])
        if targettables:
            targettable_filter = " or ".join(f"targettable eq '{t}'" for t in targettables)
            targettable_filter = f"({targettable_filter})"
            combined_filter = f"{datasource_filter} and {targettable_filter}"
        elif targetfilenames:
            targetfilenames_filter = " or ".join(f"filename eq '{t}'" for t in targetfilenames)
            targetfilenames_filter = f"({targetfilenames_filter})"
            combined_filter = f"{datasource_filter} and {targetfilenames_filter}"
        else:
            combined_filter = datasource_filter
        if 'yearnumber' in reqbody:
            combined_filter+=f"and yearnumber eq '{reqbody['yearnumber']}'"
        print(f"combined filter",combined_filter,reqbody)
        if reqbody['datasource'].lower()=='research':
            docs = search_client.search(
                search_text=reqbody['query'],
                vector_queries=[vector_query],
                top=top_,
                select=select_fields_,
                semantic_configuration_name="sem-config",
                query_type="semantic",
                filter=combined_filter,
                scoring_profile="freshness-score"
            )
        else:
            docs = search_client.search(
                search_text=reqbody['query'],
                vector_queries=[vector_query],
                top=top_,
                select=select_fields_,
                semantic_configuration_name="sem-config",
                query_type="semantic",
                filter=combined_filter
            )

        
        for doc in docs:
            # print('Search Score',doc.get('@search.score'),doc.get('title'),doc.get('published_year'),doc.get('@search.semantic.score'),doc.get('reranker_score'))
            row = {}

            for field in select_fields_:
                if field=='id':
                    continue
                key = 'tablename' if field == 'targettable' else field
                row[key] = doc.get(field, '')
                row['search_score'] = doc.get('@search.score')
            formatted_context.append(row)
    except Exception as e:
        print(f"Error in run_query: {str(e)}")
        return f" Error {str(e)} please inform this error to user"
        
    return formatted_context
@tool
def column_metadata_extractor(
    reqbody: Annotated[str, "A JSON string with query and datasource"]
) -> str:

    """
    Executes the provided query against the connected database and returns the fetched columns metadata and Medical codes from AI Search.

    Args:
        reqbody (str): A JSON string with query and datasource.

    Returns:
        str: A string of column metadata fetched from the database.
    """
    try:
        reqbody = json.loads(reqbody)
        print('Column metadata extractor received reqbody',reqbody)
        if 'databricks_tables' in reqbody:
            table_info = []
            for databricks_table in reqbody['databricks_tables']:
            
                table_info.append({"tableName":databricks_table,"metadata":catalog_query_exec(databricks_table)})
            return table_info
        if reqbody['datasource'].lower() in ['research']:
            top_docs = int(reqbody['top_docs'])
            if top_docs>10:
                top_docs=10
            select_fields_ = ["id","content","url","title","authors","filename","published_year"]
            index_name_ = settings.research_search_index
            formatted_context = run_query(index_name_,reqbody,select_fields_,top_=top_docs)
            # Sort by search_score DESC, then published_year DESC
            sorted_docs = sorted(
                formatted_context,
                key=lambda x: (x["search_score"], x["published_year"]),
                reverse=True
            )

            # Take top 5
            top_docs_sorted = sorted_docs[:5]
            if reqbody['whole_document_needed?'].lower()=='no':
                top_sections = 5
                index_name_ = settings.research_search_section_index
                doc_sections = []
                for row in top_docs_sorted:
                    reqbody['filenames']=[row['filename']]
                    print(reqbody)
                    formatted_context = run_query(index_name_,reqbody,select_fields_,top_=top_sections)
                    print(formatted_context)
                    doc_sections.extend(formatted_context)
                return doc_sections
            return formatted_context
        select_fields_ = ["id", "colname", "targettable", "description", "sourcetable", "query_mode","characteristics_desc"]  
        if reqbody['datasource'].lower() in ['ahrf','hpsa']:
            index_name_ = settings.semantic_search_index
            formatted_context = run_query(index_name_,reqbody,select_fields_)
        elif reqbody['datasource'].lower() in['sohea']:
            index_name_ = settings.sohea_search_index        
            formatted_context = run_query(index_name_,reqbody,select_fields_)

        if 'selected_table_name' in reqbody:
           
            if any(table in reqbody['selected_table_name'] for table in [
                    f'{settings.db_schema }.reference.ref_cdt_code_lookup',
                    f'{settings.db_schema }.reference.ref_icd_code_lookup',
                    f'{settings.db_schema }.reference.ref_cpt_code_lookup'
                ]):
                index_name_ = settings.medical_code_index
                reqbody['datasource']='MERATIVE'
                print('..... INDEXNAME',index_name_)
                select_fields_ =["id", "colname","value", "targettable", "description", "sourcetable", "query_mode"]
                formatted_context = run_query(index_name_,reqbody,select_fields_,top_=100)
            
        return json.dumps(formatted_context)
    except Exception as e:
        # raise e
        print(f"Error in column_metadata_extractor: {str(e)}")
        return e
@tool
def medical_code_extractor_json_file(
    reqbody: Annotated[str, "A JSON string with query and datasource"]
) -> str:
    
    """
    Executes and returns the fetched MEDICAL codes metadata from json file.

    Args:
        reqbody (str): A JSON string with query and datasource.

    Returns:
        str: A string of MEDICAL codes fetched from the JSON.

    """
    reqbody = json.loads(reqbody)
    if 'json' in reqbody:            
            
        #2. ELSE (Merative/others) --> return MEDICAL CODES
        return {key: medical_codes[key] for key in reqbody['json_keys'] if key in medical_codes}

@tool
def tooth_code_extractor(
    reqbody: Annotated[str, "A JSON string with query and datasource"]
) -> str:
    
    """
    Executes and returns the fetched Tooth codes metadata.

    Args:
        reqbody (str): A JSON string with query and datasource.

    Returns:
        str: A string of tooth codes fetched from the JSON.

    """
    reqbody = json.loads(reqbody)
    if 'json' in reqbody:            
            if reqbody.get('is_tooth_code', False):
                return tooth_codes  # Ensure 'tooth_codes' is defined somewhere        
@tool
def sohea_mapping_file_reader(reqbody):
    """
    Reads the SOHEA question mapping file.
    reqbody may be a JSON string or a dict.
    """
    if isinstance(reqbody, str):
        reqbody = json.loads(reqbody)

    filename = reqbody.get("filename")
    return read_sohea_mapping_file(filename)
'''
Initialized Agent Tootls
'''
tools_ = [fetch_record,tooth_code_extractor]
meta_data_tools_=[column_metadata_extractor,medical_code_extractor_json_file,tooth_code_extractor]
sohea_agent_tools_ = [sohea_mapping_file_reader]
functionality_test_tool = [fetch_record]