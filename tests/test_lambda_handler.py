"""Tests for the Lambda handler function."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

# --- Set Dummy Env Vars BEFORE importing modules that use settings ---
# Use patch.dict to temporarily set required environment variables for tests
_DUMMY_ENV_VARS = {
    'OPENAI_API_KEY_SECRET_NAME': 'dummy-secret-name',
    'AWS_REGION': 'us-east-1',
    'DOCUMENTS_S3_BUCKET': 'dummy-bucket-name',
    'OPENSEARCH_COLLECTION_ENDPOINT': 'dummy-endpoint.aoss.us-east-1.amazonaws.com',
    'OPENSEARCH_INDEX_NAME': 'test-index',
    'LOG_LEVEL': 'DEBUG'
}

# Global variable to hold the imported module
lambda_handler = None

# Use patch.dict as a context manager within setup_module
def setup_module(module):
    """Set environment variables and mock client initializations before any tests run in this module."""
    global lambda_handler
    with patch.dict(os.environ, _DUMMY_ENV_VARS):
        # Patch OpenSearch class, OS init funcs, and OpenAI secret getter
        # No need to mock OpenAI client init directly anymore
        with patch('src.opensearch_service.OpenSearch') as mock_opensearch_class, \
             patch('src.lambda_handler.initialize_opensearch_client') as mock_os_init, \
             patch('src.lambda_handler.create_index_if_not_exists') as mock_create_index, \
             patch('src.lambda_handler._get_openai_secret') as mock_get_secret: # Keep mocking secret fetch
            
            mock_opensearch_class.return_value = MagicMock()
            mock_os_init.return_value = None 
            mock_create_index.return_value = None
            mock_get_secret.return_value = "dummy-openai-key" 

            from src import lambda_handler as handler_module
            lambda_handler = handler_module

# No longer need to import lambda_handler at top level

# --- Test MCP Discovery ---

# Keep decorator on individual tests for standalone execution compatibility
@patch.dict(os.environ, _DUMMY_ENV_VARS)
def test_mcp_discovery_handler():
    """Test the main handler routing for MCP discovery (GET /mcp)."""
    
    # Mock the event object that API Gateway would send for a GET /mcp request
    mock_event = {
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/mcp"
            }
        },
        "body": None # GET requests typically have no body
    }
    mock_context = MagicMock() # Mock the context object (usually not needed for basic tests)

    # Call the main handler function
    response = lambda_handler.main(mock_event, mock_context)

    # Assert the expected response structure from the handler
    assert response["statusCode"] == 200
    assert "Content-Type" in response["headers"]
    assert response["headers"]["Content-Type"] == "application/json"
    
    body = json.loads(response["body"])
    assert "tools" in body
    assert isinstance(body["tools"], list)
    tool_names = [tool["name"] for tool in body["tools"]]
    assert "rag_query" in tool_names
    assert "rag_add_document" in tool_names
    assert "rag_list_documents" in tool_names

# --- Test MCP Execution (Example: rag_add_document) ---

@patch('src.lambda_handler.handle_add_document') # Patch the specific tool handler
def test_mcp_execution_add_document_routing(mock_handle_add_doc):
    """Test the main handler routing for MCP execution (POST /mcp - add_document)."""
    
    # Define the expected result from the mocked handler
    mock_tool_result = {
        "status": "success",
        "document_id": "doc_1234",
        "s3_key": "documents/doc_1234.txt",
        "message": "Mocked success"
    }
    mock_handle_add_doc.return_value = mock_tool_result
    
    # Define the incoming MCP request body
    mcp_request_body = {
        "name": "rag_add_document",
        "parameters": {
            "content": "This is test content."
        }
    }
    
    # Mock the event object for a POST /mcp request
    mock_event = {
        "requestContext": {
            "http": {
                "method": "POST",
                "path": "/mcp"
            }
        },
        "body": json.dumps(mcp_request_body) # Body is a JSON string
    }
    mock_context = MagicMock()

    # Call the main handler
    response = lambda_handler.main(mock_event, mock_context)
    
    # Assert the response from the main handler
    assert response["statusCode"] == 200
    assert "Content-Type" in response["headers"]
    assert response["headers"]["Content-Type"] == "application/json"
    
    response_body = json.loads(response["body"])
    # Check that the main handler wrapped the tool result correctly
    assert response_body == {"result": mock_tool_result} 
    
    # Assert that the correct tool handler was called with the right parameters
    mock_handle_add_doc.assert_called_once_with(mcp_request_body["parameters"])

# --- Test Specific Tool Handlers (Example: handle_add_document) ---

# Patch get_openai_client instead of the global client
@patch('src.lambda_handler.upload_document_to_s3')
@patch('src.lambda_handler.index_document')
@patch('src.lambda_handler.get_openai_client') # Patch the function that returns the client
def test_handle_add_document_success(mock_get_openai_client, mock_index_doc, mock_upload_s3):
    """Test the handle_add_document function with mocked dependencies."""
    
    # Configure mocks
    mock_upload_s3.return_value = "documents/mock_doc_id.txt"
    
    # Mock the OpenAI client instance returned by the getter
    mock_openai_instance = MagicMock()
    mock_embedding = [0.1] * 1536 
    mock_openai_instance.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=mock_embedding)]
    )
    mock_get_openai_client.return_value = mock_openai_instance # Make the getter return our mock instance
    
    mock_index_doc.return_value = {'result': 'created'}

    test_content = "Sample document content for testing."
    test_metadata = {"source": "test"}
    params = {
        "content": test_content,
        "metadata": test_metadata
    }
    
    result = lambda_handler.handle_add_document(params)
    
    # Assertions
    assert result["status"] == "success"
    assert result["s3_key"] == "documents/mock_doc_id.txt"
    assert "document_id" in result
    doc_id = result["document_id"]
    
    # Verify mocks were called
    mock_upload_s3.assert_called_once_with(test_content, doc_id)
    # Check that the mock OpenAI client instance was used correctly
    mock_openai_instance.embeddings.create.assert_called_once_with(
        input=[test_content],
        model=lambda_handler.settings.openai_embedding_model
    )
    expected_metadata = {**test_metadata, "s3_key": result["s3_key"], "original_doc_id": doc_id}
    mock_index_doc.assert_called_once_with(
        doc_id=doc_id,
        text=test_content,
        embedding=mock_embedding,
        metadata=expected_metadata
    )

# TODO:
# - Add tests for handle_query (mocking embedding generation and OpenSearch search)
# - Add tests for handle_list_documents (mocking OpenSearch list)
# - Add tests for error handling paths in main handler (e.g., invalid JSON, unknown tool)
# - Add tests for error handling within tool handlers (e.g., OpenAI API errors, S3 errors, OpenSearch errors)
# - Consider testing the initialization logic (e.g., secret fetching, client setup) - might require patching boto3/opensearchpy clients.
# - Add tests for src/opensearch_service.py functions with mocked opensearch-py client.
# - Add tests for src/utils.py with mocked boto3 S3 client. 