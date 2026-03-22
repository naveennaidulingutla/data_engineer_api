
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosResourceExistsError

from config import settings

# import logging
from app_logger import logger

'''
Application logger
'''
# logger = logging.getLogger("AI DataExplorer")
# logger.setLevel(logging.DEBUG)


'''
Cosmosdb Client
'''
class azureCosmosDb:
    def __init__(self,containerName):
        self.cosmoUrl=settings.storage_dburl
        self.cosmoKey = settings.storage_dbsecretkey
        self.databaseName = settings.storage_dbname
        self.containerName = containerName
        self.client = CosmosClient(self.cosmoUrl, credential=self.cosmoKey)
        self.database = self.client.get_database_client(self.databaseName)
        self.container = self.database.get_container_client(self.containerName)
    def insertRecord(self,payload):
        '''
        Method to insert a record
        '''
        try:
            resp = self.container.create_item(payload)
            return {
                "status": f"Record inserted successfully to {self.containerName}",
                "response": resp
            },200
        except CosmosResourceExistsError:
            return {
                "status": f" Record with id '{payload.get('id')}' already exists in {self.containerName}",
                "error": "ConflictError"
            },409
        except CosmosHttpResponseError as e:
            return {
                "status": "Failed to insert record due to Cosmos error",
                "error": str(e)
            },500
    def upsertRecord(self,payload):
        '''
        Method to upsert a record
        '''
        logger.info("Payload: %s", payload)
        resp = self.container.upsert_item(payload)
        return {"status":f"Record inserted successfully to {self.containerName}","response":resp}
    def updateRecord(self,itemid,payload):
        '''
        Method to update a record
        '''
        resp = self.container.replace_item(item=itemid , body=payload)
        return {"status":f"Record updated successfully to {self.containerName}","response":resp}
    def fetchRecord(self,query,partition_key=False):
        '''
        Method to fetch record
        '''
        if not partition_key:
            messages = list(self.container.query_items(query=query,enable_cross_partition_query=True))
        else:
            messages = list(self.container.query_items(query=query, partition_key=partition_key))
        return {"status":f"Record details fetched successfully from {self.containerName}","response":messages}
'''
Initializing `messages`
'''
message_client = azureCosmosDb('messages')
'''
Initializing `chatSessions` 
'''
session_client = azureCosmosDb('chatSessions')
ahrf_county_user_prompts = [
                    "Which counties have the highest number of dentists per 100,000 population?",
                    "How many dentists per 100,000 population are there in Los Angeles County?",
                    "What is the number of orthopedic surgeons by county in Maryland?",
                    "What is the dentist-to-population ratio by county in Texas?",

                    ]
ahrf_state_user_prompts = [
                        "How many dentists are practicing in California?",
                        "How many female dentists are in Arizona compared to California?",                        
                        "How many dental providers are practicing in California?",
                        "What percentage of families live below the poverty level in Washington State?",
                        "What is the dentist-to-population ratio in New York?",
                        "How has the number of dentists in Texas changed over the last few years?",
                        "How many medical providers are practicing in Arizona?",
                    ]

merative_user_prompts = [
                        "How many people were diagnosed with diabetes in 2023?",
                        "For 2023, how many patients with Medicare received annual wellness visit CPT codes?",
                        "Provide a 2023 breakdown of dental claims categorized by gender and segmented by line of business (Commercial, Medicaid and Medicare).",
                        "What are the 25 most frequently performed dental treatments in 2023?",
                        "Calculate the percentage for 2023 where the numerator is the count of distinct children aged 1–18 who received at least two topical fluoride applications, and the denominator is the count of all distinct children aged 1–18 who received any dental claims, based on Merative Claims Data with distinct claim headers.",
                        "Calculate the percentage for 2023 where the numerator is the count of distinct children aged 1–18 who received at least two topical fluoride applications and at least one oral evaluation (using specific CDT codes), and the denominator is the count of all distinct children aged 1–18 who received dental claims, based on Merative Claims Data with distinct claim headers.",
                        "Calculate the totals for commercial and Medicare patients over age 17 with a Sjogren’s syndrome diagnosis who had any dental claims after their diagnosis in 2023, using distinct claim headers.",
                        "How many distinct inpatient claims were filed by patients who have diabetes mellitus in 2023?",
                        "How many distinct individuals had restorative procedures (CDT/CPT) across all years of data?",
                        "For 2023, how many individuals were diagnosed with diabetes and had a periodontal visit?"
                    ]
hpsa_user_prompts = [
                        "What two HPSA counties are farthest away from reaching their HPSA goal?",
                        "Which are the top 5 counties with the highest population-to-provider ratio in HPSA designated regions for dental care?",
                        "Which state had the highest number of HPSA-designated cities after January 31, 2020?",
                        "How many dental HPSAs were there in 2022?",
                        "What are the five states with the highest number of HPSA-designated counties?",
                        "Which counties designated as HPSAs have the highest provider-to-population ratios, and what is their rural or urban status?"
                    ]
sohea_user_prompts =  [
    "Calculate the percentage of population who have lost all their teeth among those who have lost any permanent teeth in 2025 survey year",
    "Calculate the percentage of respondents who use a Waterpik among all respondents who report cleaning between their teeth at any frequency in 2025 survey year",
    "Among respondents who selected any valid reason for planning a dental visit in the next year for routine or preventive care in the 2025 survey, what percentage of those respondents selected avoiding painful oral health problems as a reason",
    "Among respondents who reported having dental insurance in 2024, what percentage specifically have private dental insurance?",
    "Provide the count of respondents who do not plan to visit a dentist next year due to anxiety or fear of dental treatment in 2025 year",
    "How many adults reported ‘Never’ for their last dental visit in 2023 and reported a dental visit in 2024? Provide unweighted results",
    "Among respondents who reported any oral symptom in the past twelve months in 2025 survey year, what percentage experienced swollen gums or toothache?",
    "Calculate the percentage of population who have lost all their teeth among those who have lost any permanent teeth breakdown by year 2025 and 2024",
    "Among respondents who reached their annual dental benefits maximum in 2025 year, what percentage consulted a dental provider via teledentistry instead of visiting the office?",
    "Percentage of the population who do not have health insurance, broken down by race in 2025 year",
    "Among respondents who responded that most severe symptom in last twelve months is swollen gums or bleeding gums in 2025 year, what percentage visited provider (dentist or oral health provider or went to the emergency department) and had a procedure or treatment that helped fix the problem? Provide weighted and unweighted percentages",
    "Among respondents who selected a valid symptom as their most severe symptom, what percentage of those reported not seeing a healthcare provider in 2025 because they could not afford care?",
    "Among individuals who chose any option for what they did when their annual benefit limit was exceeded, what percentage in 2025: 1. Delayed or avoided treatment due to cost? 2. Paid full price for ongoing treatment?",
    "Among respondents who reported having any valid primary dental insurance type in 2024, what percentage have an unlimited annual dental insurance plan, regardless of whether they provided a substantive response for maximum annual coverage?",
    "Among respondents who reported any oral symptom in the past twelve months in 2025 survey year, what percentage used a home remedy saltwater gargle?",
    "How many participants responded to the survey in 2025? Provide unweighted response",
    "How many unique respondents repeatedly participated in the survey in all three years (2023, 2024, and 2025)? Provide unweighted response",
    "How many unique survey questions in 2025 year? Provide unweighted response",
    "How many respondents in the 2025 survey selected any option (excluding 77, 98, 99 codes) for both: 'How often do you clean between your teeth?' and planning to see an oral health provider in the next year for routine or preventive care?",
    "For the year 2025, how many respondents do not have a valid primary dental insurance type and reported a most severe symptom in the last twelve months?"
    ]
research_user_prompt = [
    "How many children and adults go to an emergency department for dental care?",
    "What systemic health conditions are linked with poor oral health?",
    "What research has CareQuest Institute published on links between oral health and overall health?",
    "How many adults saw a dentist in the past year? How does this utilization rate differ by income/dental education status, etc.?",
    "Summarize the findings from each article that discusses differences in dental care access between urban and rural areas."
]
dqddma_user_prompts = [
    "How many members who were enrolled in 2024 & had an emergency department visit in 2024 that was billed by an Orthodontist (primary speciality only) in New York?",
    "How many remote dental consultations claims were made in Massachusetts (service location) in 2024 by members enrolled for less than an year?",
    "Count the number of female patients who have undergone oral & maxillofacial surgery on the permanent & supernumerary maxillary right third molar(Exclude position and region codes ).",
    "How many adult patients (aged 18 years and older)  underwent preventive procedures & on the permanent lower right second molar involving the occlusal surface?",
    "How many topical fluoride varnish applications were performed on patients by pediatric dentists in 2024, break down by state code?",
    "How many patients under 18 years old received two or more topical fluoride applications during the reporting year on different dates of service?",
    "What percentage of visits for adults over 18 years old were caries treatment visits (CDT codes D2000 to D3999 and D7140)?",
    "How many  patients were continuously enrolled at least 180 days and had claims for 2024 and 2025 with the same provider?",
    "Which state had the most silver diamine fluoride claims for patients under 18 years old at the time of treatment?",
    "Calculate the number of female individuals, enrolled date in 2024, who are aged 40 and are primary policyholders in Massachusetts?",
    "How many distinct members under 18 in Texas (patient location) who received no original payment at the claim header level and the claim header & member_id combination comprises multiple distinct procedures in 2024(same or different service dates)?",
    "How many Female members in California (patient location) had no claims after being enrolled for more than an year?",
	"Calculate the total number of individuals enrolled in 2023 who are aged 40 and above"   
]


source_specific_user_prompts_guide_book={
            "ahrf":{
                "county": {
                    "title": "County-Level Questions (Local Focus)",
                    "questions": ahrf_county_user_prompts
                    },
                "state": {
                    "title": "State-Level Questions (Local Focus)",
                    "questions": ahrf_state_user_prompts
                },
                "general":{
                    "title":"",
                    "questions":[

                    ]
                }
            },
             "sohea":{
                "county": {
                    "title": "",
                    "questions": [
                    

                    ]
                    },
                "state": {
                    "title": "",
                    "questions": [
                    
                    ]
                },
                "general":{
                    "title":"",
                    "questions":sohea_user_prompts
                }
            },
            "hpsa":{
                "county": {
                    "title": "",
                    "questions": [
                    

                    ]
                    },
                "state": {
                    "title": "",
                    "questions": [
                    
                    ]
                },
                "general":{
                    "title":"",
                    "questions":hpsa_user_prompts
                }
            },
            "merative":{
                "county": {
                    "title": "",
                    "questions": [
                    

                    ]
                    },
                "state": {
                    "title": "",
                    "questions": [
                    
                    ]
                },
                "general":{
                    "title":"",
                    "questions":merative_user_prompts
                }
            },
            "dqddma":{
                "county": {
                    "title": "",
                    "questions": [
                    

                    ]
                    },
                "state": {
                    "title": "",
                    "questions": [
                    
                    ]
                },
                "general":{
                    "title":"",
                    "questions": dqddma_user_prompts
                }
            },
            
           "research":{
                "county": {
                    "title": "",
                    "questions": [
                    

                    ]
                    },
                "state": {
                    "title": "",
                    "questions": [
                    
                    ]
                },
                "general":{
                    "title":"",
                    "questions":research_user_prompt
                }
            }
        }

source_specific_user_prompts = {

    "ahrf":{
        "state":ahrf_state_user_prompts,
        "county":ahrf_county_user_prompts
    },
    "merative":merative_user_prompts,
    "hpsa":hpsa_user_prompts,
    "sohea":sohea_user_prompts,
    "dqddma": dqddma_user_prompts
}