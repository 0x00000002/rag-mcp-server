import pytest
from fastapi.testclient import TestClient
from src.server import app  # Import your FastAPI app instance

# Using TestClient for testing
client = TestClient(app)

# Remove @pytest.mark.asyncio and async def
def test_mcp_discovery():
    """Test the MCP discovery endpoint."""
    # Remove async with and await
    response = client.get("/mcp")
    
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert isinstance(data["tools"], list)
    # Check for the presence of expected tools
    tool_names = [tool["name"] for tool in data["tools"]]
    assert "rag_query" in tool_names
    assert "rag_add_document" in tool_names
    assert "rag_list_documents" in tool_names

# Add more tests below for other endpoints (rag_query, rag_add_document, rag_list_documents)
# Remember to handle setup/teardown if tests interact with ChromaDB or files
# For example, using pytest fixtures to manage a test ChromaDB instance or temporary files. 