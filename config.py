
from dotenv import load_dotenv
import os
import ast
import re
import json
load_dotenv('.env',override=True)

class Settings:
    def __init__(self):
        # env-based settings
        self.LLM_Config = ast.literal_eval(os.getenv('LLM_Config',{}))
        self.search_endpoint = os.getenv('AI_SEARCH_ENDPOINT')
        self.search_key = os.getenv('AI_SEARCH_API_KEY')
        self.research_search_index=os.getenv('RESEARCH_AI_INDEX')
        self.research_search_section_index=os.getenv('RESEARCH_AI_SECTION_INDEX')
        self.semantic_search_index=os.getenv('SEMANTIC_AI_SEARCH_INDEX','source-catalog-ai-data-explorer')
        self.sohea_search_index = os.getenv('SOHEA_INDEX','sohea-catalog-ai-data-explorer')
        self.medical_code_index=os.getenv('MEDICAL_CODE_INDEX','medical-code-ai-data-explorer')
        self.dbhostname = os.getenv('DATABRICKS_HOSTNAME')
        self.sqlurl = os.getenv('SQL_WAREHOUSE_LINK')
        self.dbaccesstoken = os.getenv('DATABRICKS_TOKEN')
        self.storage_dburl = os.getenv('COSMOS_DB_URI')
        self.storage_dbsecretkey = os.getenv('COSMOS_DB_KEY')
        self.storage_dbname = os.getenv('COSMOS_DB_NAME','backend-ai-data-explorer')
        self.db_schema = os.getenv('DATABRICKS_CATALOG_NAME') 
        self.model_input_cost = os.getenv('OPENAI_MODEL_INPUT_COST')
        self.model_output_cost = os.getenv('OPENAI_MODEL_OUTPUT_COST')
        self.group_ids={
            "DE_Internal_User":os.getenv('DE_Internal_User'),
            "DE_External_User":os.getenv('DE_External_User'),
            "DE_Approvers":os.getenv('DE_Approvers'),
            "DE_AIDataExplorer_User":os.getenv('DE_AIDataExplorer_User')
        }
        self.internal_group_ids = {
            "DE_Admin_User":os.getenv('DE_Admin_User'),

            "Databricks_Merative_Reader":os.getenv('Databricks_Merative_Reader'),
            "Databricks_Merative_Writer":os.getenv('Databricks_Merative_Writer'),
            "DataLake_Merative_Ingestor":os.getenv('DataLake_Merative_Ingestor'),

            "Databricks_HCN_Reader":os.getenv('Databricks_HCN_Reader'),
            "Databricks_HCN_Writer":os.getenv('Databricks_HCN_Writer'),
            "DataLake_HCN_Ingestor":os.getenv('DataLake_HCN_Ingestor'),

            "Databricks_Survey_Reader":os.getenv('Databricks_Survey_Reader'),
            "Databricks_Survey_Writer":os.getenv('Databricks_Survey_Writer'),
            "DataLake_Survey_Reader":os.getenv('DataLake_Survey_Reader'),
            "DataLake_Survey_Writer":os.getenv('DataLake_Survey_Writer'),
            "DataLake_Survey_Ingestor":os.getenv('DataLake_Survey_Ingestor'),

            "Databricks_CQIP_Merative_Reader":os.getenv('Databricks_CQIP_Merative_Reader'),
            "Databricks_CQIP_HCN_Reader":os.getenv('Databricks_CQIP_HCN_Reader'),
            "Databricks_CQIP_Surveys_Reader":os.getenv('Databricks_CQIP_Surveys_Reader'),
            
            "Databricks_SOHEA_Reader":os.getenv('Databricks_SOHEA_Survey_Reader'),
            "Databricks_SOHEA_Writer":os.getenv('Databricks_SOHEA_Survey_Writer'),
            "Databricks_CQIP_DDMA_Reader" : os.getenv('Databricks_CQIP_DDMA_Reader'),
            "Databricks_DDMA_Reader" : os.getenv('Databricks_DDMA_Reader'),
            "Databricks_DDMA_Writer" : os.getenv('Databricks_DDMA_Writer'),
            "DataLake_DDMA_Ingestor" : os.getenv('DataLake_DDMA_Ingestor')

        }
        self.external_group_ids={
            "DataLake_External_User_Merative_Reader":os.getenv('DataLake_External_User_Merative_Reader'),
            "DataLake_External_User_HCN_Reader":os.getenv("DataLake_External_User_HCN_Reader"),
            "DataLake_External_User_Surveys_Reader":os.getenv('DataLake_External_User_Surveys_Reader'),
            "DataLake_External_User_SOHEA_Reader":os.getenv('DataLake_External_User_SOHEA_Survey_Reader'),
            "DataLake_External_User_DDMA_Reader":os.getenv('DataLake_External_User_DDMA_Reader')
        }


settings = Settings()

with open('medical_codes.json','r') as file:
    medical_codes = json.load(file)

medical_codes_json_keys = medical_codes.keys()

try:
    with open('Tooth_codes.json','r') as file:
        tooth_codes = json.load(file)
except FileNotFoundError:
    tooth_codes = {}
    print("warning:Tooth_codes.json file not found")
tooth_codes_json_keys = tooth_codes.keys()
print(f'Initial Check! `LLM_Config` type: {type(settings.LLM_Config)}')


def get_latest_sohea_year_file():
    """
    Finds the latest year from files in the fixed folder './sohea_mapping'.
    First tries exact naming convention: SOHEA_Questions_mapping_YYYY.json

    Returns:
        latest_year (int or None)
        latest_file (str or None)
    """
    folder_path = "./sohea_mapping_files"  # fixed folder
    if not os.path.exists(folder_path):
        print(f"Folder {folder_path} does not exist.")
        return None, None

    files = os.listdir(folder_path)
    year_files = []

    # Check exact naming convention
    for f in files:
        match = re.search(r'SOHEA_Questions_mapping_(\d{4})\.json', f)
        if match:
            year_files.append((int(match.group(1)), f))

    # Pick latest year
    if year_files:
        latest_year, latest_file = max(year_files, key=lambda x: x[0])
        return latest_year, latest_file
    else:
        return None, None
def read_sohea_mapping_file(filename):
    with open(f'./sohea_mapping_files/{filename}','r') as file:
        question_mapping = json.load(file)

    return question_mapping


def get_year_check_configs():
    return {
        'ahrf':{
            'sql': f'''select distinct release_year_number from
                {settings.db_schema}.sem_survey.sem_ahrf_state_national_survey
                order by release_year_number desc
                limit 5'''
        },
        'hpsa':{
            'sql': f'''select distinct YEAR(hpsa_designation_date) as available_year from
                {settings.db_schema}.sem_survey.sem_hpsa_dental
                order by available_year desc
                limit 5'''
        },
        'dqddma':{
            'sql': f'''select distinct YEAR(service_date) as available_year from
                {settings.db_schema}.sem_dental_payer.vw_sem_dental_claim
                order by available_year desc
                limit 5'''
        },
        'sohea':{
            'sql': f'''select distinct year_number as available_year from
                {settings.db_schema}.sem_sohea.vw_sem_sohea_survey
                order by available_year desc
                limit 5'''
        },
        'merative':{
            'sql': f'''select distinct YEAR(service_date) as available_year from
                {settings.db_schema}.sem_merative.vw_sem_merative_claim_summary
                order by available_year desc
                limit 5'''
        }
    }

