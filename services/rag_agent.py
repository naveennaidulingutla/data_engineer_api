"""Generator function for retrieval-augmented generation (RAG)"""

from langchain.prompts import PromptTemplate
from langchain.agents import create_react_agent,AgentExecutor
from langchain_core.agents import AgentAction
from services.prompts import user_prompt_rephraser,column_retriever, query_response_generator,final_response_generator,intent_classifier,research_explorer,sohea_classifier,validation_agent

from langchain_openai import AzureChatOpenAI
from services.agent_tools_ import tools_,meta_data_tools_,sql_query_executor,sohea_agent_tools_
import ast
from datetime import datetime
import json
from services.common.utils import message_client,session_client,logger,source_specific_user_prompts
from typing import List, Optional, Union, Literal
from pydantic import BaseModel,Field
from pydantic import ValidationError
import traceback
from typing import List, Optional, Union, Literal
from langchain_core.output_parsers import PydanticOutputParser
from config import settings,get_latest_sohea_year_file,get_year_check_configs
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from zoneinfo import ZoneInfo
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from langchain_community.callbacks.manager import get_openai_callback
class Followup(BaseModel):
    type: Literal["sql", "visualization", "general"]
    label: str

class Chart(BaseModel):
    type: Literal["bar", "pie", "line"]
    x: List[str]
    y: Union[List[int], List[float], List[List[int]], List[List[float]]]
    xlabel: Optional[str] = None
    ylabel: Optional[str] = None
    title: str
    series: Optional[List[str]] = None

class FinalResponseModel(BaseModel):
    sqlCode: str = Field(description="SQL Queries used to generate the answer ( SEND Empty string if no Queries found)")
    visualization: Optional[Chart] = Field(default=None,description=" Data Visualizaition Choose best Chart among bar / pie / line  Follow  **CHARTING INSTRUCTIONS RULES**")
    followups: List[Followup] = Field(default=[],description="Array of followup questions as json objects each containing type and label, Follow  **Followup Suggestion RULES**")
    viewVisualization: bool = Field(default=False, description="Set to True if the user question involves visualization example : show bar chart or pie chart ..; otherwise False.")
class FinalResponseModel_Research_Explorer(BaseModel):
    followups: List[Followup] = Field(default=[],description="Array of followup questions as json objects each containing type and label, Follow  **Followup Suggestion RULES**")
    
parser = PydanticOutputParser(pydantic_object=FinalResponseModel)
parser_research_explorer = PydanticOutputParser(pydantic_object=FinalResponseModel_Research_Explorer)

'''
Chat Agent Main Class to generate final response
'''
class Main():
    def __init__(self,sessionId,input_text,datasource,userId):
        self.sessionId=sessionId
        self.userPrompt = input_text
        self.dataSource = datasource
        self.rephrased_query = []
        self.userId = userId
        self.chatId=1
        self.streamed_response=''
        self.total_input_tokens=0
        self.total_output_tokens=0
        self.application_name='AI Research Explorer' if datasource.lower()=='research' else 'AI Data Explorer'
        self.llm_config_key =  next(
                                (key for key in settings.LLM_Config.keys() if datasource.lower() in key.lower()),
                                'default'  # default if no match found
                                )
        self.model_name=settings.LLM_Config[self.llm_config_key]['model_name']
        self.llm_connector = AzureChatOpenAI(
                                            azure_deployment=settings.LLM_Config[self.llm_config_key]['deployment_name'], 
                                            api_version=settings.LLM_Config[self.llm_config_key]['api_version'],
                                            azure_endpoint=settings.LLM_Config[self.llm_config_key]['endpoint'],
                                            api_key = settings.LLM_Config[self.llm_config_key]['subscription_key'],
                                            temperature=0,
                                            max_tokens=None,
                                            timeout=30,
                                            max_retries=1,
                                            
                                        )
        self.llm_connector_agent = AzureChatOpenAI(
                                                    azure_deployment=settings.LLM_Config[self.llm_config_key]['deployment_name'], 
                                                    api_version=settings.LLM_Config[self.llm_config_key]['api_version'],
                                                    azure_endpoint=settings.LLM_Config[self.llm_config_key]['endpoint'],
                                                    api_key = settings.LLM_Config[self.llm_config_key]['subscription_key'],
                                                    temperature=0,
                                                    max_tokens=None,
                                                    timeout=30,
                                                    max_retries=1,
                                                    model_kwargs={"stream_options": {"include_usage": True}}
                                                    
                                                    )
    def get_current_chat_id(self):
        query = 'SELECT c.chatId from c ORDER BY c.chatId DESC OFFSET 0 LIMIT 1'
        msg_data = message_client.fetchRecord(query,[self.userId,self.sessionId])
        if len(msg_data['response'])>0:
            self.chatId=msg_data['response'][0]['chatId']+1
    def fetch_previous_chat_info(self,cols):
        query = f'SELECT {cols} from c ORDER BY c.chatId DESC OFFSET 0 LIMIT 5'
        #filtering on sessionId and userEmail
        msg_data = message_client.fetchRecord(query,[self.userId,self.sessionId])

        print('Messages history: ',msg_data['response'])
        return msg_data['response']

    def invoke_llm(self,prompt_input,stage_name=False):
        '''
        Invoke LLM to generate response
        '''
        try:
            start_time = datetime.now()
            with get_openai_callback() as cb:

                response = self.llm_connector.invoke([{"role": "user", "content": prompt_input}])
                self.total_input_tokens+=cb.prompt_tokens
                self.total_output_tokens+=cb.completion_tokens
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} {stage_name} LLM Invoke - Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens} TimeTaken: {duration_ms:.2f} ms"
                print(log_str)
                logger.info(log_str)
            return response.content
        except Exception as e:
            print("Exception during Azure OpenAI call:\n%s", traceback.format_exc())
            log_str = f"Session ID  {self.sessionId} Error occured while invoking LLM  {str(e)}"
            print(log_str)
            logger.error(log_str)
    def calculate_cost(self):
        INPUT_RATE = float(settings.LLM_Config[self.llm_config_key]['inputcost'])/ 1_000_000     # $ per input token
        OUTPUT_RATE = float(settings.LLM_Config[self.llm_config_key]['outputcost'])/ 1_000_000    # $ per output token

        cost_input = self.total_input_tokens * INPUT_RATE
        cost_output = self.total_output_tokens * OUTPUT_RATE

        total_cost = cost_input + cost_output

        return cost_input,cost_output,total_cost

    def response_validator(self,final_response):
        MAX_RETRIES=5
        if final_response:
            try:
                parsed_json = json.loads(final_response)
                if "visualization" in parsed_json and parsed_json["visualization"] == {}:
                    parsed_json["visualization"] = None
                if self.dataSource.lower()=='research':
                    validated = FinalResponseModel_Research_Explorer(**parsed_json)
                    final_response = validated.dict()
                    final_response['visualization']=None
                    final_response['sqlCode']=''
                    final_response['viewVisualization']=False
                else:
                    validated = FinalResponseModel(**parsed_json)
                    final_response = validated.dict()
                return final_response
            except (json.JSONDecodeError,ValidationError) as e:
                ERROR_latest = str(e)
                for attempt in range(1, MAX_RETRIES + 1):
                    
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Retrying JSON/Validation fix via LLM (Attempt {attempt}) Error details: {ERROR_latest}"
                    print(log_str)
                    logger.info(log_str)
                    if self.dataSource.lower()=='research':
                        format_instruction = parser_research_explorer.get_format_instructions()
                    else:
                        format_instruction = parser.get_format_instructions()
                    final_response=self.invoke_llm(f'''Verify the JSON Parse or Validation Error {ERROR_latest} 
                                                    # Input:
                                                        {final_response}
                                                    Expected Output
                                                    Corrected json `json.dump()`
                                                    Do NOT modify or delete any value or characters
                                                    ❌ No math in JSON -- If any math needs to done compute the same
                                                    ##response_format_instructions
                                                    {format_instruction}
                                                    JUST RETURN json output DO NOT ADD ANY EXTRA TEXT
                                                    ''',
                                                    stage_name='Output Json Parser')
                    print("JSON..LLM",final_response)
                    try:
                        parsed_json = json.loads(final_response)

                        if "visualization" in parsed_json and parsed_json["visualization"] == {}:
                            parsed_json["visualization"] = None
                        validated = FinalResponseModel(**parsed_json)
                        final_response = validated.dict()
                        return final_response
                    except (json.JSONDecodeError,ValidationError) as er:
                        ERROR_latest = str(er)
                return None

        return None
    def storage_db(self,final_response):
        '''
        Chat history
        '''
        
        final_response = self.response_validator(final_response)
        if not final_response:
            final_response={}
            final_response['visualization']=None
            final_response['sqlCode']=''
            final_response['followups']=[]
            final_response['viewVisualization']=False
        final_response['chatId']=self.chatId        
        final_response['id']=self.sessionId+'-'+str(final_response['chatId'])
        final_response['insertedAt']=str(datetime.now(ZoneInfo("America/New_York")))
        final_response['userId']=self.userId
        final_response['sessionId']=self.sessionId 
        final_response['showSql']=False
        final_response['showVisualization']=final_response['viewVisualization']
        final_response['prompt']=self.userPrompt
        final_response['rephrasedPrompt']=self.rephrased_query
        final_response['response']=self.streamed_response
        final_response['total_input_tokens']=self.total_input_tokens
        final_response['total_output_tokens']=self.total_output_tokens
        final_response['modelname']=self.model_name
        input_cost , output_cost , total_cost = self.calculate_cost()
        final_response['input_cost']=input_cost
        final_response['output_cost']=output_cost
        final_response['total_cost']=total_cost
        final_response['dataSource']=self.dataSource
        final_response['applicationName']=self.application_name
        try:
            resp,status_code = message_client.insertRecord(final_response)
            if status_code==409:
                resp = message_client.updateRecord(final_response['id'],final_response)
            print('record insertion status ! ',resp)
            payload = session_client.fetchRecord('select * from c',[self.userId,self.sessionId])['response'][0]
            payload['lastUpdatedAt']=str(datetime.now(ZoneInfo("America/New_York")))
            session_client.updateRecord(self.userId+'-'+self.sessionId,payload)
        except Exception as e:
            log_str = f"failed at Insertion / Updation of record ! {str(e)}"
            print(log_str)
            logger.error(log_str)
            
        return final_response

    def agent_thoughts(self,agent_response):
        agent_steps=[]
        for step in agent_response:
            # 1. Extract Thought / Action / Action Input
            if "actions" in step:
                for action in step["actions"]:
                    if isinstance(action, AgentAction):
                        txt = "[🧠 Thought]\n" + action.log.split("\n")[0] + "\n"
                        agent_steps.append(txt)
                            
            # 2. Agent Message Content
            if "messages" in step:
                for msg in step["messages"]:
                    if hasattr(msg, "content") and msg.content:
                        txt = "\n[💬 Agent Message]\n"+ msg.content + "\n"
                        agent_steps.append(txt)
            #3. Agent final output
            if "output" in step:
                txt = step['output']
                final_output=txt
                agent_steps.append(txt)
                return final_output,agent_steps
    def agent_executor(self,agent_name,agent_tools):
        return AgentExecutor(
                agent=agent_name, 
                tools=agent_tools, 
                verbose=True, 
                handle_parsing_errors=True,  # handles output formatting errors
                max_iterations=25
                )
    def start_agent(self):

        try:
            yield ''
            #Initial Message Insertion
            self.get_current_chat_id()
            self.storage_db('')
            #chat history
            agent_chat_info = []
            previous_chat_info = self.fetch_previous_chat_info('c.chatId,c.prompt,c.rephrasedPrompt,c.sqlCode,c.response')

            agent_steps_=[]
            agent_steps_.append(
                {"user_question":self.userPrompt}
                )
            sanitized_user_prompt = str(self.userPrompt).replace('\n','').replace('\r','')
            '''
            Initialize variables for System Instructions
            '''
            intent_prompt_template = PromptTemplate.from_template(intent_classifier.CLASSIFIER)
            rephraser_prompt_template = PromptTemplate.from_template(user_prompt_rephraser.USER_PROMPT_REPHRASER)
            year_validation_template = PromptTemplate.from_template(validation_agent.YEAR_Validation_)
            lob_validation_prompt = PromptTemplate.from_template(validation_agent.LOB_Validation_)
            agent_prompt_template_col_retriever = PromptTemplate.from_template(column_retriever.COLUMN_RETRIEVER_PROMPT)
            agent_prompt_template_query_generator = PromptTemplate.from_template(query_response_generator.QUERY_GENERATOR_PROMPT)
            final_response_generator_prompt = PromptTemplate.from_template(final_response_generator.RESPONSE_GENERATOR_)
            structured_response_generator_prompt = PromptTemplate.from_template(final_response_generator.STRUCTURED_RESPONSE_GENERATOR_)

            research_explorer_retriever_prompt = PromptTemplate.from_template(research_explorer.RESEARCH_EXPLORER_RETRIEVER)
            research_explorer_decision_agent_prompt = PromptTemplate.from_template(research_explorer.DECISION_AGENT_PROMPT)
            research_structured_response_generator_prompt = PromptTemplate.from_template(research_explorer.STRUCTURED_RESPONSE_GENERATOR_)
            research_explorer_intent_response_prompt = PromptTemplate.from_template(research_explorer.INTENT_CLASSIFIER)
            sohea_denominator_classifier_prompt_template = PromptTemplate.from_template(sohea_classifier.Denominator_classifier)
            sohea_year_classifier_prompt_template = PromptTemplate.from_template(sohea_classifier.Year_Scope_classifier)
            sohea_json_mapping_agent_prompt = PromptTemplate.from_template(sohea_classifier.hierachy_mapping_agent)

            if self.dataSource.lower()=='ahrf':
                prompt_rephraser_instructions = user_prompt_rephraser.AHRF_USER_PROMPT_REPHRASER
                column_retriever_instructions = column_retriever.AHRF_COLUMN_RETRIEVER_PROMPT   
                query_response_generator_instructions = query_response_generator.AHRF_QUERY_GENERATOR_PROMPT
                followup_suggestions= source_specific_user_prompts['ahrf']
            elif self.dataSource.lower()=='hpsa':
                prompt_rephraser_instructions = user_prompt_rephraser.HPSA_USER_PROMPT_REPHRASER
                column_retriever_instructions = column_retriever.HPSA_COLUMN_RETRIEVER_PROMPT
                query_response_generator_instructions = query_response_generator.HPSA_QUERY_GENERATOR_PROMPT
                followup_suggestions=source_specific_user_prompts['hpsa']
            elif self.dataSource.lower()=='merative':
                prompt_rephraser_instructions = user_prompt_rephraser.MERATIVE_USER_PROMPT_REPHRASER
                column_retriever_instructions = column_retriever.MERATIVE_COLUMN_RETRIEVER_PROMPT
                query_response_generator_instructions = query_response_generator.MERATIVE_QUERY_GENERATOR_PROMPT
                followup_suggestions=source_specific_user_prompts['merative']
            elif self.dataSource.lower()=='sohea':
                prompt_rephraser_instructions = user_prompt_rephraser.SOHEA_USER_PROMPT_REPHRASER
                column_retriever_instructions = column_retriever.SOHEA_COLUMN_RETRIEVER_PROMPT
                query_response_generator_instructions = query_response_generator.SOHEA_QUERY_GENERATOR_PROMPT
                followup_suggestions=source_specific_user_prompts['sohea']
            elif self.dataSource.lower()=='dqddma':
                prompt_rephraser_instructions = user_prompt_rephraser.DQ_DDMA_USER_PROMPT_REPHRASER
                column_retriever_instructions = column_retriever.DQ_DDMA_COLUMN_RETRIEVER_PROMPT
                query_response_generator_instructions = query_response_generator.DQ_DDMA_QUERY_GENERATOR_PROMPT
                followup_suggestions=source_specific_user_prompts.get('dqddma')
            if self.dataSource.lower()=='research':
                prompt_input_intent = research_explorer_intent_response_prompt.format(userPrompt=self.userPrompt+ ' ( Oral health related question ) ',chat_history=previous_chat_info)
            else:
                prompt_input_intent = intent_prompt_template.format(userPrompt=self.userPrompt,chat_history=previous_chat_info,datasource_specific_user_prompts=followup_suggestions)
            intent_response = self.invoke_llm(prompt_input_intent,stage_name='Intent Classifier')
            print('..intent classifier',intent_response)
            json_data = json.loads(intent_response)
            print(json_data)
            rephraser_input=self.userPrompt
            if not json_data['run_downstream_llm'] and json_data['response']:
                self.streamed_response+=json_data['response']
                yield json_data['response']
                self.storage_db('')
                agent_steps_.append(json_data['response'])
                for chat_message in previous_chat_info:
                    if 'chatId' in chat_message and 'chatId' in json_data:
                        if str(chat_message['chatId']) in [str(cid) for cid in json_data['chatId']]:
                            agent_steps_.append( chat_message)
                if self.dataSource.lower()=='research':
                    prompt_input_structured_response_generator = research_structured_response_generator_prompt.format(
                        AGENT_OUTPUTS=agent_steps_,
                        response_format_instructions=parser_research_explorer.get_format_instructions(),
                        datasource_specific_user_prompts = followup_suggestions,
                        user_question=self.userPrompt+ ' ( Oral health related question ) '
                        )
                else:
                    prompt_input_structured_response_generator = structured_response_generator_prompt.format(
                        AGENT_OUTPUTS=agent_steps_,
                        response_format_instructions=parser.get_format_instructions(),
                        datasource_specific_user_prompts = followup_suggestions,
                        user_question=self.userPrompt
                        )
            else:
                
                for chat_message in previous_chat_info:
                    if chat_message['chatId'] in json_data['chatId']:
                        agent_chat_info.append(chat_message)
                rephraser_input=json_data['rephrased_query']
                print('...INTENT Classifier rephrased query',rephraser_input)
                if self.dataSource.lower()=='research':
                    research_explorer_decision_agent_prompt_=research_explorer_decision_agent_prompt.format(
                        user_question = f'Original Question: {self.userPrompt} ',
                    )
                    decision_response = self.invoke_llm(research_explorer_decision_agent_prompt_,stage_name='Research-Explorer-Decision-LLM')
                    print("Decision response" , decision_response)
                    research_explorer_retriever_prompt_1 = research_explorer_retriever_prompt.partial(
                    user_question = f'Original Question: {self.userPrompt}',
                    original_rephrased_question = f'Original Question: {self.userPrompt}  rephrased prompt: {rephraser_input}',
                    decision_response=decision_response,
                    chat_history=agent_chat_info

                    )
                    summary_agent = create_react_agent(
                            self.llm_connector_agent,
                            meta_data_tools_,
                            research_explorer_retriever_prompt_1
                            )
                    research_explorer_agent = self.agent_executor(summary_agent,meta_data_tools_)

                    with get_openai_callback() as cb:
                        research_explorer_agent_response = research_explorer_agent.stream({"input": f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query}'})
                        summary_output,research_explorer_agent_steps = self.agent_thoughts(research_explorer_agent_response)
                        self.total_input_tokens += cb.prompt_tokens
                        self.total_output_tokens += cb.completion_tokens
                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Research-Explorer Agent Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens}"
                        print(log_str)
                        logger.info(log_str)
                        yield summary_output
                        self.streamed_response=summary_output
                        agent_steps_.append(research_explorer_agent_steps)
                    
                    prompt_input_structured_response_generator = research_structured_response_generator_prompt.format(
                        AGENT_OUTPUTS=agent_steps_,
                        response_format_instructions=parser_research_explorer.get_format_instructions(),
                        decision_response = decision_response
                        )
                else:

                    '''
                    Query Rephraser
                    '''
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Rephrasing user prompt:  {sanitized_user_prompt}"
                    print(log_str)
                    logger.info(log_str)

                    prompt_input_rephraser = rephraser_prompt_template.format(
                        datasource_specific_instructions=prompt_rephraser_instructions, 
                        user_question=rephraser_input,
                        chat_history=agent_chat_info
                        )

                    self.rephrased_query=self.invoke_llm(prompt_input_rephraser,stage_name='User Prompt rephraser')

                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource}Rephrased user prompt:  {self.rephrased_query}"
                    print(log_str)
                    logger.info(log_str)
                    
                    print("Rephrased Query : ",self.rephrased_query,type(self.rephrased_query))

                    agent_steps_.append(
                        {"rephrasedQueries":self.rephrased_query}
                        )
                    self.rephrased_query = ast.literal_eval(self.rephrased_query)
                    print(type(self.rephrased_query))

                    # Year Validation Check
                    year_check_configs = get_year_check_configs()
                    current_source = self.dataSource.lower()
                    if current_source in year_check_configs:
                        print(f"---Starting Year validation for {current_source.upper()} ---")
                        year_validation_sql = year_check_configs[current_source]['sql']
                        years_available = sql_query_executor(year_validation_sql)
                        print(f"Years Available {years_available}")
                        year_validation_prompt = year_validation_template.format(userPrompt=self.rephrased_query,years_available=years_available)
                        is_year_present_llm_response = self.invoke_llm(year_validation_prompt,stage_name='Validating required params')
                        print(f'Is Year present? {is_year_present_llm_response}')
                        is_year_present_llm_response = json.loads(is_year_present_llm_response)
                        if not is_year_present_llm_response.get('is_year_present'):
                            # yield 'Please select year from followup-suggestions'
                            # yield json.dumps({'followups': [{'type':'general','label':'2023'},{'type':'general','label':'2022'},{'type':'general','label':'2021-2022'}]})
                            yield is_year_present_llm_response['message']
                            yield json.dumps({'followups':is_year_present_llm_response['followups']})
                            self.streamed_response+=is_year_present_llm_response['message']
                            self.storage_db('')
                            return ''
                    if current_source in ('dqddma', 'merative'):
                        print(f"--- Starting LOB Validation for {current_source.upper()} ---")
                        try:
                            print(f'{self.rephrased_query}')
                            formatted_lob_prompt = lob_validation_prompt.format(
                                userPrompt=self.rephrased_query,
                                datasource=current_source.upper()
                            )
                            lob_response = self.invoke_llm(formatted_lob_prompt, stage_name=f'{current_source.upper()} LOB Validation')
                            lob_json = json.loads(lob_response)
                            print(lob_json)
                            if not lob_json.get('is_lob_present', True):
                                yield lob_json['message']
                                yield json.dumps({'followups': lob_json['followups']})
                                self.streamed_response += lob_json['message']
                                self.storage_db('')
                                return ''
                        except Exception as e:
                            print(f"Error in {current_source.upper()} LOB Validation: {str(e)}")


                    if self.dataSource.lower() == 'sohea':
                        '''Single/multi year Classifier'''
                        sohea_year_classifier_prompt = sohea_year_classifier_prompt_template.format(userPrompt=self.rephrased_query)
                        sohea_year_classifier_response = json.loads(self.invoke_llm(sohea_year_classifier_prompt,stage_name='Sohea Year Classifier'))

                        '''Denominator Classifier'''
                        sohea_denominator_classifier_prompt =  sohea_denominator_classifier_prompt_template.format(userPrompt=self.rephrased_query)
                        sohea_denominator_classifier_response = json.loads(self.invoke_llm(sohea_denominator_classifier_prompt,stage_name='Sohea Denominator Classifier'))
                        if sohea_year_classifier_response['year_scope']=='unknown':
                            latest_year , latest_file = get_latest_sohea_year_file()
                            sohea_year_classifier_response['years']=[latest_year]
                        print(f'Sohea classifier response : {sohea_denominator_classifier_response}')
                        print(f'Sohea year scope classifier response : {sohea_year_classifier_response}')
                    
                        column_retriever_instructions=column_retriever_instructions+f'''
                        YearNumbers {sohea_year_classifier_response['years']}
                        Must Inform Downstream LLM To use these yearnumber
                        # '''
                        # 'when denominator -- true -- Agent -- JSON -- Mapping '
                        # if sohea_denominator_classifier_response['denominator_required']:
                        sohea_mapping_agent_prompt = sohea_json_mapping_agent_prompt.partial(
                        question = f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query} Datasource {self.dataSource} Years_requested : {sohea_year_classifier_response['years']} Denominator Required: {sohea_denominator_classifier_response['denominator_required']}',
                        
                        
                            )
                        heirarchy_agent = create_react_agent(
                            self.llm_connector_agent,
                            sohea_agent_tools_,
                            sohea_mapping_agent_prompt
                        )
                        # Executor
                        heirarchy_mapping_agent =self.agent_executor(heirarchy_agent,sohea_agent_tools_)
                    
                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} executing heirarchy agent to retrieve questions."
                        print(log_str)
                        logger.info(log_str)
                        start_time_column_agent = datetime.now()
                        with get_openai_callback() as cb:
                            heirarchy_mapping_agent_response = heirarchy_mapping_agent.stream({"input": f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query}'})
                            mapping_logic,ai_heirarchy_mapping_agent_steps  = self.agent_thoughts(heirarchy_mapping_agent_response)
                            self.total_input_tokens += cb.prompt_tokens
                            self.total_output_tokens += cb.completion_tokens
                            duration_ms = (datetime.now() - start_time_column_agent).total_seconds() * 1000
                            log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} heirarchy_mapping_agent Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens}  TimeTaken: {duration_ms:.2f} ms"
                            print(log_str)
                            logger.info(log_str)

                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} recieved output response from heirarchy_mapping_agent."
                        print(log_str)
                        logger.info(log_str)
                        
                        column_retriever_instructions=column_retriever_instructions+f"""
                        MUST INSTRUCT DOWNSTREAM LLM TO USE BELOW **Denominator** & **Numerator** logic
                                                    
                        ****CRITICAL RULE**: MUST Select all the columns that required for **Denominator** logic Check **Valid Child question** level description and verify it with the description of the colname
                        Example Question type:  [reason] actual survey question ;  
                        ( WHEN IT IS REQUIRED ) select all those `colname` for denominator logic as well, and ensure they match the actual survey question do not choose colname from other survey question
                        
                        Mapping Logic :
                        {mapping_logic}  
                        Agent steps taken to arrive at the mapping logic :
                        {ai_heirarchy_mapping_agent_steps}

                        Always Choose the **Immediate parent question** Only and corresponding variable name STRICTLY INSTRUCT Downstream LLM to use level codes of the corresponding Include those response_ids in your `reason` mentioned in childquestions while filtering denominator data
                        **Provide the full detailed logic and instructions; colname,level codes and level description must be used for downstream filtering and logic implementation. Do not miss out any details in the mapping logic provided above as it is critical for accurate retrieval of columns and data.**
                        **Also inform that Level codes may differ; always fetch the latest values from the DB.***
                        """
                        agent_steps_.append(
                            {"ai_sohea_mapping_agent":ai_heirarchy_mapping_agent_steps}
                            )
                              
                    '''
                    React Agent - > AI Search & Relevant Columns extractor
                    '''
                    print(f"Session Id {self.sessionId} Datasource {self.dataSource} creating search agent to retrieve columns ")
                    agent_prompt_col_retriever = agent_prompt_template_col_retriever.partial(
                        question = f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query} Datasource {self.dataSource}',
                        data_source_specific_instruction=column_retriever_instructions,
                        chat_history=agent_chat_info
                        )
                    search_agent = create_react_agent(
                        self.llm_connector_agent,
                        meta_data_tools_,
                        agent_prompt_col_retriever
                        )
                    # Executor
                    column_retriever_agent =self.agent_executor(search_agent,meta_data_tools_)
                    
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} executing search agent to retrieve columns."
                    print(log_str)
                    logger.info(log_str)
                    start_time_column_agent = datetime.now()
                    with get_openai_callback() as cb:
                        column_retriever_agent_response = column_retriever_agent.stream({"input": f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query}'})
                        relevant_columns,ai_search_agent_steps = self.agent_thoughts(column_retriever_agent_response)
                        self.total_input_tokens += cb.prompt_tokens
                        self.total_output_tokens += cb.completion_tokens
                        duration_ms = (datetime.now() - start_time_column_agent).total_seconds() * 1000
                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Column RetrieverAgent Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens}  TimeTaken: {duration_ms:.2f} ms"
                        print(log_str)
                        logger.info(log_str)

                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} recieved output response from search agent."
                    print(log_str)
                    logger.info(log_str)

                    agent_steps_.append(
                        {"ai_search_agent":ai_search_agent_steps}
                        )
                    
                    '''
                    React Agent - > SQL Query builder , Documents Retriever & Response Generator
                    '''

                    agent_prompt_query_generator = agent_prompt_template_query_generator.partial(
                        datasource_specific_instructions=query_response_generator_instructions,
                        question=f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query}',
                        parsed=relevant_columns,
                        chat_history=agent_chat_info
                        )
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} creating react agent to retrieve documents "
                    print(log_str)
                    logger.info(log_str)

                    sql_agent = create_react_agent(
                        self.llm_connector_agent, 
                        tools_, 
                        agent_prompt_query_generator)
                    
                    # Executor
                    agent_ex = self.agent_executor(sql_agent,tools_)

                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} executing react agent to retrieve documents "
                    print(log_str)
                    logger.info(log_str)

                    sql_agent_steps=[]
                    start_time_query_agent = datetime.now()
                    with get_openai_callback() as cb:
                        response_stream = agent_ex.stream({"input": f'Original Question: {self.userPrompt} Rephrased Query: {self.rephrased_query}'})
                        relevant_columns,sql_agent_steps = self.agent_thoughts(response_stream)
                        self.total_input_tokens += cb.prompt_tokens
                        self.total_output_tokens += cb.completion_tokens
                        duration_ms = (datetime.now() - start_time_query_agent).total_seconds() * 1000
                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Query Generated Agent Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens} TimeTaken: {duration_ms:.2f} ms"
                        print(log_str)
                        logger.info(log_str)
                    

                    agent_steps_.append(
                        {"sql_agent_steps":sql_agent_steps}
                        )
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} query agent process completed Invoking final LLM for response generator"
                    print(log_str)
                    logger.info(log_str)

                    '''
                    Final Response Generator -> Streaming response 
                    '''
                    prompt_input_response_generator = final_response_generator_prompt.format(
                        AGENT_OUTPUTS=agent_steps_
                        )
                    final_response=''
                    
                    start_time_response_agent = datetime.now()
                    with get_openai_callback() as cb:
                        for chunk in self.llm_connector_agent.stream([{"role": "user", "content": prompt_input_response_generator}]):
                            
                            self.streamed_response+=chunk.content
                            yield chunk.content
                        self.total_input_tokens += cb.prompt_tokens
                        self.total_output_tokens += cb.completion_tokens
                        duration_ms = (datetime.now() - start_time_response_agent).total_seconds() * 1000
                        log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Response Generater Input Tokens {cb.prompt_tokens} Output Tokens {cb.completion_tokens} TimeTaken: {duration_ms:.2f} ms"
                        print(log_str)
                        logger.info(log_str)
                    log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Response generated successfuly"
                    print(log_str)
                    logger.info(log_str)

                    print(final_response)
                    prompt_input_structured_response_generator = structured_response_generator_prompt.format(
                    AGENT_OUTPUTS=agent_steps_,
                    response_format_instructions=parser.get_format_instructions(),
                    datasource_specific_user_prompts = followup_suggestions,
                    user_question=self.userPrompt
                    )
                

            '''
            Structured Response Generator -> JSON response with followup suggestions
            '''
            

            structured_response = self.invoke_llm(prompt_input_structured_response_generator,stage_name='Structured response generator')
            structured_response = self.storage_db(structured_response)
            log_str = f"Session Id {self.sessionId} Datasource {self.dataSource} Structured Response generated successfuly"
            print(log_str)
            logger.info(log_str)
            print("Completed")
            print(structured_response)
            if structured_response:
                yield json.dumps(structured_response)
            
        except Exception as e:
            print(traceback.format_exc())
            log_str = f"Session ID  {self.sessionId} Datasource {self.dataSource} Error occurred while generating assistant response: {str(e)}"
            print(log_str)          
            logger.error(log_str)
            
              # Check for rate-limit in error text
            if '429' in str(e) or 'RateLimitReached' in str(e):
                user_message = ("The system is receiving too many requests right now. "
                                "Please wait a few seconds and try again.")
            else:
                user_message = "An internal error has occurred. Please try again later."
            self.streamed_response+=user_message
            self.storage_db('')
            yield user_message
'''
Metadata extractor 

'''
class Metadata():
    def __init__(self,datasource):
        self.datasource = datasource
        self.tables=[]
        self.datasource_description=""


    def get_merative_table_data(self,table_name, description, db_schema):
        try:
            table_path = f"{db_schema}.sem_merative.{table_name}"
            table_query = f"DESCRIBE {table_path}"
            sql_query = f"SELECT * FROM {table_path} LIMIT 5"

            table_metadata = sql_query_executor(table_query)
            records = sql_query_executor(sql_query)

            return {
                "tableName": table_name,
                "description": description,
                "metadata": [row.asDict() for row in table_metadata],
                "records": [row.asDict() for row in records]
            }

        except Exception as e:
            print(f"Error processing {table_name}: {e}")
            return None

    def fetch_info(self):
        
        if self.datasource.lower()=='ahrf':
            self.datasource_description = (
                "Provides information on health care professions, health facilities, population characteristics, "
                "economics, health professions training, hospital utilization, hospital expenditures, and the environment "
                "at the county, state, and national levels."
            )

            table_level_description = {
                "sem_ahrf_state_national_survey": "The table containing health resources data aggregated at the state and national levels, received from AHRF.",
                "sem_ahrf_county_survey": "The table containing county-level health resources data received from AHRF.",
                            }
            selected_variables={
                "sem_ahrf_state_national_survey":"WHERE source_variable_name IN ('dent', 'dent_asst', 'dent_hygn','dent_fem','dent_mal')",
                "sem_ahrf_county_survey":"WHERE source_variable_name IN ('md_nf_activ','dent_npi', 'dent_npi_fem', 'dent_npi_mal','popn')",
                        }
            filter_query = {
                "sem_ahrf_state_national_survey":"AND state_code = 'CA' AND release_year_number = 2022",
                "sem_ahrf_county_survey":"AND county_name = 'Los Angeles' AND release_year_number = 2022 AND file_year_number=2024",
            }
            for table_name in table_level_description.keys():

                table_query = f"DESCRIBE {settings.db_schema}.sem_survey.{table_name}"
                sql_query = f"SELECT DISTINCT * from {settings.db_schema}.sem_survey.{table_name}  {selected_variables[table_name]} {filter_query[table_name]}  LIMIT 5 "
                table_metadata = sql_query_executor(table_query)
                records = sql_query_executor(sql_query)

                print(table_metadata)
                try:
                    self.tables.append(
                        {"tableName":table_name,
                        "description":table_level_description[table_name],
                        "metadata":[row.asDict() for row in table_metadata],
                        "records":[row.asDict() for row in records]
                        }

                    )
                except:pass

        if self.datasource.lower()=='sohea':
            self.datasource_description = (
                "State of Oral Health Equity in America (SOHEA) includes detailed information on care requests, demographic identifiers, weight groups, response values, "
                "and the original survey questions. The data supports trend analysis, assessment of patient demographics, and "
                "evaluation of care strategies, particularly in the context of oral health equity."            
                )

            table_level_description = {
                "sem_sohea_survey": "The table contains data related to care requests, including various metrics and identifiers associated with each case. It includes information such as weight groups, response values, and the original questions posed. This data can be used for analyzing care request trends, understanding patient demographics, and evaluating the effectiveness of different care strategies over time."
                }
            for table_name in table_level_description.keys():

                table_query = f"DESCRIBE {settings.db_schema}.sem_sohea.{table_name}"
                sql_query = f"SELECT DISTINCT * from {settings.db_schema}.sem_sohea.{table_name}  LIMIT 5 "
                table_metadata = sql_query_executor(table_query)
                records = sql_query_executor(sql_query)

                print(table_metadata)
                try:
                    self.tables.append(
                        {"tableName":table_name,
                        "description":table_level_description[table_name],
                        "metadata":[row.asDict() for row in table_metadata],
                        "records":[row.asDict() for row in records]
                        }

                    )
                except:pass
        if self.datasource.lower()=='hpsa':
            self.datasource_description = (
                "HPSA (Health Professional Shortage Area) data identifies geographic areas, populations, or facilities with shortages of health providers. It is used to allocate resources and support underserved communities in the U.S."
            )

            table_level_description = {
                "sem_hpsa_dental": "The table contains data related to Health Professional Shortage Areas (HPSAs). It includes information such as HPSA IDs, names, designations, and various metrics related to population and shortage ratios.",
                }

            for table_name in table_level_description.keys():

                table_query = f"DESCRIBE {settings.db_schema}.sem_survey.{table_name}"
                sql_query = f"SELECT DISTINCT * from {settings.db_schema}.sem_survey.{table_name} LIMIT 5 "
                table_metadata = sql_query_executor(table_query)
                records = sql_query_executor(sql_query)

                print(table_metadata)
                try:
                    self.tables.append(
                        {"tableName":table_name,
                        "description":table_level_description[table_name],
                        "metadata":[row.asDict() for row in table_metadata],
                        "records":[row.asDict() for row in records]
                        }

                    )
                except:pass
        if self.datasource.lower()=='merative':
            self.datasource_description = (
                "The 'merative' schema houses essential data related to dental and medical services, including patient demographics, provider information, treatment details, and financial breakdowns. This schema plays a crucial role in tracking patient encounters, claims processing, and insurance enrollments for effective healthcare management."
            )

            table_level_description = {
                "vw_sem_merative_claim_summary":"The table contains data related to healthcare claims. It includes information such as claim identifiers, member details, service dates, procedure codes, and payment amounts. This data can be used for analyzing claims processing, understanding service utilization, and assessing payment trends. It may also help in identifying emergency and inpatient services.",
                "vw_sem_merative_encounter_summary":"The table contains data related to healthcare encounters for members, including details about procedures, claims, and payments. It can be used to analyze patient interactions with healthcare providers, track the frequency and types of procedures performed, and assess financial aspects such as claims and payments. Key metrics include inpatient and outpatient claim counts, various payment amounts, and procedure counts, which can help in understanding service utilization and financial performance.",
                "vw_sem_merative_enrollment_summary":"The table contains data related to member enrollments, including details such as enrollment periods, coverage types, and various indicators of enrollment duration. Possible use cases include analyzing enrollment trends, assessing coverage types, and evaluating member retention over time. This data can help in understanding member engagement and the effectiveness of different enrollment strategies."
                }

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(self.get_merative_table_data, table_name, table_level_description[table_name], settings.db_schema)
                    for table_name in table_level_description
                ]

                for future in tqdm(as_completed(futures), total=len(futures), desc="Processing tables"):
                    result = future.result()
                    if result:
                        self.tables.append(result)
            
            
        return {
            "datasource":self.datasource,
            "description":self.datasource_description,
            "tables":self.tables
        }
        
