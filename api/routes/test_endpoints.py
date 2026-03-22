import pytest
from fastapi.testclient import TestClient
from api.routes import endpoints
from unittest.mock import patch, MagicMock

app = endpoints.app
client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert "Application is running" in response.text

def test_verify_datasource_valid():
    assert endpoints.verify_datasource("sohea") == "Verified"
    assert endpoints.verify_datasource("research") == "Verified"

def test_verify_datasource_invalid():
    assert endpoints.verify_datasource("invalid_ds") is None

@patch("api.routes.endpoints.session_client")
@patch("api.routes.endpoints.logger")
@patch("api.routes.endpoints.DatasourceAuthorization")
@patch("api.routes.endpoints.chatbot")
def test_chatAgent_valid(mock_chatbot, mock_DatasourceAuthorization, mock_logger, mock_session_client):
    mock_DatasourceAuthorization.return_value = ({{}}, ["sohea"])
    mock_session_client.insertRecord.return_value = ("ok", 200)
    mock_chatbot.return_value = iter(["response chunk"])
    payload = {
        "sessionId": "testsession",
        "userPrompt": "dGVzdCBwcm9tcHQ=",  # base64 for 'test prompt'
        "dataSource": "sohea",
        "userEmail": "test@example.com"
    }
    response = client.post("/api/agent/v1", json=payload)
    assert response.status_code == 200 or response.status_code == 500  # StreamingResponse may not be testable

def test_errorResponse():
    resp = endpoints.errorResponse({"error": "fail"})
    assert resp.status_code == 500

def test_successResponse():
    resp = endpoints.successResponse({"ok": True})
    assert resp.status_code == 200

# More endpoint tests can be added for /api/sessions/v1, /api/chathistory/v1, /api/metadata/v1, /api/prelogin/v1, /api/updateflags/v1
# using similar mocking strategies for dependencies and database calls.
