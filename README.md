# 🚀 AI Data Explorer - > smart health data assistant.

AI Data Explorer is a FastAPI-based web application designed to serve as an intelligent assistant for exploring health-related data. It offers modular APIs for:
- Chat-based interaction
- Data source introspection
- Session management
---

## 📁 Repository Structure

```bash
.
├── app.py                          # Application entry point (runs with Uvicorn)
├── api/                  
│   ├── routes/ 
│   │   └── endpoints.py            # API route definitions
├── services/ 
│   ├── __init__.py                 # Entry point for ChatAgent and schema extraction               
│   ├── agent_tools.py              # Agent tool executors
│   ├── rag_agent.py                # Core agent logic
│   ├── prompts/                    # LLM system instructions
│   └── common/                     # Shared utilities: auth logic and dependency injection
│       ├── utils.py                # General-purpose helper functions
│       ├── auth.py                 # Authentication logic
│       └── authDependencies.py     # Auth-related dependencies for FastAPI
├── requirements.txt                # Python dependencies
└── .env                            # Environment variables

```

---

## 📚 Available APIs

All API endpoints are documented with Swagger UI.

🔗 Access them here: **[http://localhost:8000/docs](http://localhost:8000/docs)**


## 🛠️ Setup Instructions

## 🛠️ Prerequisites
- [Python 3.12.0](https://www.python.org/downloads/)

### ✅ Step 1: Create `.env` File

Create a `.env` file in the root directory with the following variables:

```env
# Azure AD Auth
AI_SEARCH_API_KEY=FETCH_FROM_AKV
AI_SEARCH_ENDPOINT=FETCH_FROM_AKV
DATABRICKS_HOSTNAME=FETCH_FROM_AKV
SQL_WAREHOUSE_LINK=FETCH_FROM_AKV
DATABRICKS_TOKEN=FETCH_FROM_AKV
COSMOS_DB_URI=FETCH_FROM_AKV
COSMOS_DB_KEY=FETCH_FROM_AKV
COSMOS_DB_NAME=backend-ai-data-explorer
LLM_Config=FETCH_FROM_AKV
DATABRICKS_CATALOG_NAME=FETCH_FROM_AKV
SEMANTIC_AI_SEARCH_INDEX=source-catalog-ai-data-explorer
AD_TENANT_ID=FETCH_FROM_AKV
AD_CLIENT_ID=FETCH_FROM_AKV
AD_CLIENT_SECRET=FETCH_FROM_AKV
DE-AIDataExplorer-User=FETCH_FROM_AKV
DE-Internal-User=FETCH_FROM_AKV
DE_Approvers=FETCH_FROM_AKV
DE-External-User=FETCH_FROM_AKV
DE-Admin-User=FETCH_FROM_AKV
Databricks-Merative-Reader=FETCH_FROM_AKV
Databricks-Merative-Writer=FETCH_FROM_AKV
DataLake-Merative-Ingestor=FETCH_FROM_AKV
Databricks-HCN-Reader=FETCH_FROM_AKV
Databricks-HCN-Writer=FETCH_FROM_AKV
DataLake-HCN-Ingestor=FETCH_FROM_AKV
DataLake-Survey-Reader=FETCH_FROM_AKV
DataLake-Survey-Writer=FETCH_FROM_AKV
DataLake-Survey-Ingestor=FETCH_FROM_AKV
Databricks-Survey-Reader=FETCH_FROM_AKV
Databricks-Survey-Writer=FETCH_FROM_AKV
Databricks-CQIP-Merative-Reader=FETCH_FROM_AKV
Databricks-CQIP-HCN-Reader=FETCH_FROM_AKV
Databricks-CQIP-Surveys-Reader=FETCH_FROM_AKV
Databricks_SOHEA_Survey_Reader=FETCH_FROM_AKV
Databricks_SOHEA_Survey_Writer=FETCH_FROM_AKV
DataLake-External-User-Merative-Reader=FETCH_FROM_AKV
DataLake-External-User-HCN-Reader=FETCH_FROM_AKV
DataLake-External-User-Surveys-Reader=FETCH_FROM_AKV
DataLake_External_User_SOHEA_Survey_Reader=FETCH_FROM_AKV
Databricks_DDMA_Reader=FETCH_FROM_AKV
Databricks_DDMA_Writer=FETCH_FROM_AKV
DataLake_DDMA_Ingestor=FETCH_FROM_AKV
Databricks_CQIP_DDMA_Reader=FETCH_FROM_AKV
DataLake_External_User_DDMA_Reader=FETCH_FROM_AKV
APPLICATION_INSIGHTS_INSTRUMENTATION_KEY=FETCH_FROM_AKV


```

> 💡  it's recommended to **fetch secrets from Azure Key Vault** and inject them via environment variables .
- `dev` environment  
    - kv-de-dp-dev-eus-01
---
### ✅ Step 2: Create virtual environment

```bash
python -m venv .venv
```
---
### ✅ Step 3: Activate virtual environment

Windows
```bash
.\.venv\Scripts\activate
```

Unix
```bash
source .venv/bin/activate
```

---

### ✅ Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

---

### ✅ Step 5: Start the Application

Run the app using:

```bash
python app.py
```

The server will start at: **[http://localhost:8000](http://localhost:8000)**


You can then visit:

- 🔍 **Swagger UI**: http://localhost:8000/docs  

---

## 🧰 Developer Notes

- Authorization is required for all API endpoints and is implemented using dependency injection.
- Shared utilities and auth logic are centralized under `common/`.

---
## 📬 Support

For issues, enhancements, or access requests, contact the backend team.

## Steps to create docker image and run it locally

```bash
docker build --tag <IMAGE_NAME>:<TAG> .
docker run -d -p 8000:8000 <IMAGE_NAME>:<TAG>
```

## Steps to push docker image to ACR

```bash
docker login <ACR_URL>
docker push <IMAGE_NAME>:<TAG>
```

During docker login it will prompt you to enter username and password, which you can fetch from ACR Keys.
Make sure to add the ACR DOMAIN to the image name, for example ACR_DOMAIN/IMAGE_NAME

## 📦 Deployment

This project uses a **CI/CD pipeline** that automatically deploys based on Git branch merges. Each environment is connected to its corresponding branch, triggering builds and deployments accordingly.

### 🔁 Auto Deployment via CI/CD

| Environment | Trigger Branch     | Description                                                                      |
| ----------- | ------------------ | -------------------------------------------------------------------------------- |
| **Dev**     | `develop`          | Merging into `develop` triggers automatic deployment to the **Dev** environment. |
| **Test**    | `test`             | Merging into `test` triggers deployment to the **Test** environment.             |
| **UAT**     | `uat`              | Merging into `uat` deploys the app to **User Acceptance Testing (UAT)**.         |
| **Prod**    | `main` or `master` | Merging into `main` or `master` triggers deployment to **Production**.           |

> ✅ No manual steps are needed if the pipeline is correctly configured and credentials are in place.
---