'''
Entrypoint to Chatbot
'''
from services.rag_agent import Main,Metadata
def chatbot(sessionId,input_text,datasource,userId):
    print("Enabling chatbot")
    return Main(sessionId,input_text,datasource,userId).start_agent()
def metadata_extraction(datasource):
    print("Metdata extraction !")
    return Metadata(datasource).fetch_info()