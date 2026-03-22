'''
API Endpoints
'''
from fastapi import FastAPI,Request,Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,EmailStr
from typing import Optional
from services import chatbot,metadata_extraction
import base64
from urllib.parse import unquote
import os
from services.common.utils import session_client,message_client,logger
from datetime import datetime
from fastapi.responses import JSONResponse
from zoneinfo import ZoneInfo
from fastapi.encoders import jsonable_encoder
from config import settings
from services.common.authDependency import Authorization,DatasourceAuthorization

"""Initializing the FastAPI application"""
app = FastAPI(dependencies=[Depends(Authorization)])

"""Include the CORS middleware"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

allowed_datasources = ['ahrf','hpsa','merative','research']
allowed_datasources.append('sohea')
allowed_datasources.append('dqddma')
class Chatagent(BaseModel):
    sessionId: str
    userPrompt: str
    dataSource:str
    userEmail: EmailStr  # Validated email format

class UpdateFlagsRequest(BaseModel):
    sessionId: str  # Required
    chatId: int     # Required
    userEmail: EmailStr # Required
    showSql: bool = False  # Optional
    showVisualization: bool = False  # Optional

 
'''
API Response Structure
'''
def successResponse(response):
    """Return a Success response"""
    return JSONResponse(status_code=200, content=response)


def errorResponse(response):
    """Return a Error response"""
    return JSONResponse(status_code=500, content=response)

@app.get("/health")
def health_check():
    '''
    Health check endpoint to verify that the application is running.
    ''' 
    return successResponse("Application is running successfully !")
def verify_datasource(datasource):
    if datasource.lower() in allowed_datasources:
        return 'Verified'
@app.post("/api/agent/v1")
def chatAgent(request: Chatagent, request_: Request):

    '''
    Handles chat requests for the agent.  
    Receives user input and returns the agent's response.
    '''
    session_id=str(request.sessionId).replace('\n','').replace('\r','')
    datasource=str(request.dataSource).replace('\n','').replace('\r','')
    userId=str(request.userEmail).replace('\n','').replace('\r','')
    encoded_text = request.userPrompt
    try:

        decoded_base64 = base64.b64decode(encoded_text).decode("utf-8")
        input_text = unquote(decoded_base64)

    except Exception as e:
        log_str = f"Error occurred while generating response for sessionId {session_id}: {str(e)} Proceeding with {encoded_text}"
        print(log_str)
        logger.error(log_str)
        # return errorResponse("An internal error has occurred. Please try again later.")

        input_text=encoded_text
    
    log_str=f"Request received to AI Assistant. SessionId {session_id}"
    print(log_str)
    logger.info(log_str)
    response = verify_datasource(datasource)
    if response is None:
        return errorResponse(f"Invalid datasource: {datasource}")
    datasource_details,datasources_backend = DatasourceAuthorization(request_.headers.get("authorization"),request_.headers.get('Isresearch'))
    if datasource.lower() not in datasources_backend:
        return errorResponse(f"You do not have access to the datasource: {datasource}")


    try:
        db_status,status_code = session_client.insertRecord(
            {
                "id":userId+'-'+session_id,
                "userId" :userId,
                "sessionId" :session_id,
                "sessionName" : input_text,
                "dataSource" : datasource,
                "applicationName":'AI Research Explorer' if datasource.lower()=='research' else 'AI Data Explorer',
                "insertedAt" :str(datetime.now(ZoneInfo("America/New_York"))),
                "lastUpdatedAt" :str(datetime.now(ZoneInfo("America/New_York"))),
                "isFavorite" :'False',
                "isDeleted":'False'
            }
        )
        print(db_status,status_code)
        return StreamingResponse(chatbot(session_id, input_text, datasource, userId), media_type="text/event-stream")
    except Exception as e:
        log_str = f"Error occurred while generating response for sessionId {session_id}: {str(e)}"
        print(log_str)
        logger.error(log_str)
        return errorResponse("An internal error has occurred. Please try again later.")

@app.get('/api/sessions/v1')
def listsessions(request:Request,userEmail: EmailStr):


    '''
    Returns a list of previous chat sessions associated with the specified user email.
    '''
   

    userEmail=str(userEmail).replace('\n','').replace('\r','')
    try:
        isresearch_user = request.headers.get('Isresearch','false')
        '''
        Fetching last 10 interactions per each datasource
        '''
        distinct_datasource_query = f"SELECT DISTINCT c.dataSource from c where c.userId='{userEmail}'"
        distinct_datasources = session_client.fetchRecord(distinct_datasource_query)['response']
        sessions_=[]
        for datasource in distinct_datasources:
            if datasource['dataSource'].lower() not in allowed_datasources:
                continue
            if isresearch_user=='true' and datasource['dataSource'].lower()!='research':
                continue
            elif isresearch_user=='false' and datasource['dataSource'].lower()=='research':
                continue
            
            query = f"SELECT c.sessionId,c.sessionName,c.lastUpdatedAt,c.dataSource from c where c.userId='{userEmail}' and c.dataSource='{datasource['dataSource']}' ORDER BY c.lastUpdatedAt DESC OFFSET 0 LIMIT 10"
            session_data = session_client.fetchRecord(query)['response']
            if session_data:
                sessions_.extend(session_data)

        return successResponse({"userId":userEmail,"sessions":sessions_})
    except Exception as e:
        log_str = f"Error occured while fetching sessions userEmail {userEmail} error: {str(e)}"
        print(log_str)
        logger.error(log_str)
        return errorResponse("An internal error has occurred. Please try again later.")

@app.get('/api/chathistory/v1')
def sessionhistory(sessionId: str,userEmail:EmailStr):

    '''
    Returns a list of chat messages associated with the specified user email and session ID.
    '''

    sessionId=str(sessionId).replace('\n','').replace('\r','')
    userEmail=str(userEmail).replace('\n','').replace('\r','')
    try:
        query = f"select * from c"
        
        session_data = message_client.fetchRecord(query,[userEmail,sessionId])
        return successResponse({"sessionId":sessionId,"messages":session_data['response']})
    except Exception as e:
        log_str = f"Error occured while fetching chatHistory sessionId {sessionId} error: {str(e)}"
        print(log_str)
        logger.error(log_str)
        return errorResponse("An internal error has occurred. Please try again later.")
   

@app.get('/api/metadata/v1')
def datasource_metainfo(datasource: str):

    '''
    Returns metadata for the specified datasource, including schema details and sample records.
    '''
    datasource=str(datasource).replace('\n','').replace('\r','')
    response = verify_datasource(datasource)
    if response is None:
        return errorResponse("Datasource not configured !!")
    try:
        metadata_details = metadata_extraction(datasource)
        return successResponse(jsonable_encoder(metadata_details))
    except Exception as e:
        log_str = f"Error occured while fetching metatda datasource {datasource} error: {str(e)}"
        print(log_str)
        logger.error(log_str)
        return errorResponse("An internal error has occurred. Please try again later.")
    
@app.get('/api/prelogin/v1')
def prelogin_check(request: Request):

    '''
    Pre login verification whether user has access to AI Dataexplorer 
    Returns which datasources he has access to
    '''

    datasource_details , datasource_backend = DatasourceAuthorization(request.headers.get("authorization"),request.headers.get('Isresearch'))
    return datasource_details


@app.post('/api/updateflags/v1')
def update_chat_flags(data: UpdateFlagsRequest):
    """
    Updates flags for a chat record such as showSql and showVisualization.
    """
    
    payload = message_client.fetchRecord(f'select * from c where c.chatId={data.chatId}',[data.userEmail,data.sessionId])['response'][0]
    if data.showSql:
        payload['showSql']=True
    elif data.showVisualization:
        payload['showVisualization']=True
    response = message_client.updateRecord(data.sessionId+'-'+str(data.chatId),payload)
    return response