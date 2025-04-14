"""AWS Lambda handler function for the RAG MCP Server."""

import json
import logging
import os
import hashlib
import traceback

from openai import OpenAI, APIError
from botocore.exceptions import ClientError
import boto3

# Import settings and utility functions
from src.config import settings
from src.utils import upload_document_to_s3
from src.opensearch_service import (
    initialize_opensearch_client,
    create_index_if_not_exists,
    index_document,
    search_documents,
    list_all_documents
)

# Configure logging based on environment variable
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)
logger = logging.getLogger("rag-mcp-lambda")

# --- Globals / Initialization ---
# Initialize clients outside the handler for potential reuse across warm invocations
_openai_api_key = None
_app_api_key = None # Cache for the app API key

def _get_openai_secret() -> str:
    """Fetches the OpenAI API Key from AWS Secrets Manager. Caches the key after first fetch."""
    global _openai_api_key
    if _openai_api_key:
        return _openai_api_key

    secret_name = settings.openai_api_key_secret_name
    # Use region from environment directly (provided by Lambda runtime)
    region_name = os.environ.get('AWS_REGION') 
    if not region_name:
        # Fallback for local testing if AWS_REGION env var isn't set
        logger.warning("AWS_REGION environment variable not found, using region from settings.")
        region_name = settings.aws_region 

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        logger.info(f"Fetching secret '{secret_name}' from Secrets Manager")
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        if 'SecretString' in get_secret_value_response:
            secret = json.loads(get_secret_value_response['SecretString'])
            api_key = secret.get('OPENAI_API_KEY') or secret.get('openai_api_key')
            if api_key:
                _openai_api_key = api_key # Cache the key
                logger.info("Successfully fetched and cached OpenAI API Key from Secret.")
                return _openai_api_key
            else:
                 logger.error(f"Could not find key like 'OPENAI_API_KEY' within secret '{secret_name}'. Found keys: {list(secret.keys())}")
                 raise ValueError(f"API Key not found in secret '{secret_name}'")
        else:
            logger.error(f"Secret '{secret_name}' does not contain a SecretString.")
            raise ValueError(f"Secret '{secret_name}' format not supported")

    except ClientError as e:
        logger.error(f"Error fetching secret '{secret_name}': {e}")
        raise e
    except Exception as e:
        logger.error(f"Error parsing secret '{secret_name}': {e}")
        raise e

def _get_app_api_key() -> str:
    """Fetches the Application API Key from AWS Secrets Manager. Caches the key."""
    global _app_api_key
    if _app_api_key:
        return _app_api_key # Return cached key
    
    secret_name = os.environ.get('APP_API_KEY_SECRET_NAME')
    if not secret_name:
        logger.error("APP_API_KEY_SECRET_NAME environment variable not set.")
        raise ValueError("Application API Key secret name configuration is missing.")
        
    region_name = os.environ.get('AWS_REGION', settings.aws_region)
    session = boto3.session.Session()
    client = session.client(service_name='secretsmanager', region_name=region_name)
    
    try:
        logger.info(f"Fetching app API key secret '{secret_name}' from Secrets Manager")
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        
        # Assuming the secret value *is* the API key itself (plain text)
        if 'SecretString' in get_secret_value_response:
            api_key = get_secret_value_response['SecretString']
            _app_api_key = api_key # Cache the key
            logger.info("Successfully fetched and cached App API Key from Secret.")
            return _app_api_key
        else:
            logger.error(f"Secret '{secret_name}' does not contain a SecretString.")
            raise ValueError(f"Secret '{secret_name}' for App API Key not found or in wrong format.")
            
    except ClientError as e:
        logger.error(f"Error fetching secret '{secret_name}' for App API Key: {e}")
        # Handle specific errors like ResourceNotFound separately if needed
        raise e
    except Exception as e:
        logger.error(f"Unexpected error fetching secret '{secret_name}' for App API Key: {e}")
        raise e

def get_openai_client() -> OpenAI:
    """Gets an initialized OpenAI client, fetching the key if needed."""
    api_key = _get_openai_secret() # Ensures key is fetched and cached
    return OpenAI(api_key=api_key)

def initialize_clients():
    """Initializes non-lazy clients (OpenSearch) and caches secrets."""
    try:
        # Initialize OpenSearch
        logger.info("Initializing OpenSearch client...")
        initialize_opensearch_client(
            endpoint=settings.opensearch_collection_endpoint,
            region=os.environ.get('AWS_REGION', settings.aws_region), # Use runtime region
            index=settings.opensearch_index_name
        )
        create_index_if_not_exists() 
        logger.info("OpenSearch client initialization complete.")
        
        # Eagerly fetch/cache secrets during initialization
        logger.info("Fetching initial secrets...")
        _get_openai_secret() # Fetch and cache OpenAI key
        _get_app_api_key() # Fetch and cache App API key
        logger.info("Secret fetching complete.")
            
    except Exception as e:
        logger.exception(f"Failed to initialize clients or fetch initial secrets: {e}")
        raise

# Call initialization logic eagerly when the Lambda environment loads
initialize_clients()

# --- MCP Tool Handlers ---

def handle_discovery():
    """Handles the MCP discovery request."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "tools": [
                {
                    "name": "rag_query",
                    "description": "Search the knowledge base for information relevant to a query using OpenSearch",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "n_results": {
                                "type": "integer",
                                "description": "Number of documents to retrieve",
                                "default": 3
                            }
                        },
                        "required": ["query"]
                    }
                },
                {
                    "name": "rag_add_document",
                    "description": "Add a document to the knowledge base (stored in S3 and indexed in OpenSearch)",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "Document content"
                            },
                            "metadata": {
                                "type": "object",
                                "description": "Optional metadata for the document (will include s3_key)"
                            }
                        },
                        "required": ["content"]
                    }
                },
                {
                    "name": "rag_list_documents",
                    "description": "List all indexed documents in the OpenSearch knowledge base",
                    "inputSchema": {
                        "type": "object",
                        "properties": {}
                    }
                }
            ]
        })
    }

def handle_execution(event_body: dict):
    """Handles MCP execution requests."""
    tool_name = event_body.get("name")
    params = event_body.get("parameters", {})
    
    result_body = None
    try:
        if tool_name == "rag_query":
            result_body = handle_query(params)
        elif tool_name == "rag_add_document":
            result_body = handle_add_document(params)
        elif tool_name == "rag_list_documents":
            result_body = handle_list_documents(params) # Doesn't need OpenAI client
        else:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": f"Unknown tool: {tool_name}"})
            }
            
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"result": result_body})
        }
        
    # Specific error handling
    except APIError as e:
        logger.error(f"OpenAI API Error calling tool '{tool_name}': {e}")
        return {
            "statusCode": 502, # Bad Gateway - upstream error
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"OpenAI API Error: {str(e)}"})
        }
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        logger.error(f"AWS Client Error calling tool '{tool_name}' ({error_code}): {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"AWS Error: {error_code}"})
        }
    except Exception as e:
        # Catch-all for unexpected errors during tool execution
        logger.exception(f"Unexpected error calling tool '{tool_name}': {e}") 
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": f"Internal Server Error: {str(e)}"})
        }

def handle_query(params: dict):
    """Handles the rag_query tool call."""
    query = params.get("query")
    n_results = params.get("n_results", 3)
    
    if not query:
        raise ValueError("Query parameter is required")

    # Initialize OpenAI client lazily here
    openai_client = get_openai_client()
        
    # 1. Get embedding for the query
    logger.info(f"Generating embedding for query: '{query[:50]}...'")
    embedding_response = openai_client.embeddings.create(
        input=[query],
        model=settings.openai_embedding_model
    )
    query_embedding = embedding_response.data[0].embedding
    logger.info(f"Embedding generated successfully.")
    
    # 2. Search OpenSearch
    logger.info(f"Searching OpenSearch for {n_results} results.")
    search_results = search_documents(
        query_embedding=query_embedding,
        n_results=n_results
    )
    
    # 3. Generate answer using OpenAI based on context
    context = "\n\n".join([doc["text"] for doc in search_results if doc.get("text")])
    
    if not context:
        logger.warning(f"No context found for query: {query}")
        answer = "I could not find relevant information in the knowledge base to answer your question."
    else:
        logger.info(f"Generating chat completion based on {len(search_results)} sources.")
        try:
            # Use the same lazily initialized client
            completion = openai_client.chat.completions.create(
                model=settings.openai_chat_model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that answers questions based *only* on the provided context. If the context doesn't contain the answer, say so."}, 
                    {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"}
                ]
            )
            answer = completion.choices[0].message.content
            logger.info("Chat completion generated successfully.")
        except APIError as e:
            logger.error(f"OpenAI API Error during chat completion: {e}")
            answer = f"Error generating answer: {str(e)}"
            
    return {
        "answer": answer,
        "sources": search_results
    }

def handle_add_document(params: dict):
    """Handles the rag_add_document tool call."""
    content = params.get("content")
    metadata = params.get("metadata", {})
    
    if not content:
        raise ValueError("Content parameter is required")
    
    # Initialize OpenAI client lazily here
    openai_client = get_openai_client()

    # Generate a unique ID 
    content_hash = hashlib.md5(content.encode()).hexdigest()
    doc_id = f"doc_{content_hash[:16]}"
    
    # 1. Upload to S3
    logger.info(f"Uploading document content to S3 (doc_id: {doc_id})")
    s3_key = upload_document_to_s3(content, doc_id)
    logger.info(f"Document uploaded to S3: {s3_key}")
    
    metadata["s3_key"] = s3_key
    metadata["original_doc_id"] = doc_id
    
    # 2. Get embedding for the document content
    logger.info(f"Generating embedding for document content (doc_id: {doc_id})")
    embedding_response = openai_client.embeddings.create(
        input=[content],
        model=settings.openai_embedding_model
    )
    doc_embedding = embedding_response.data[0].embedding
    logger.info(f"Embedding generated for document (doc_id: {doc_id})")
    
    # 3. Index in OpenSearch
    logger.info(f"Indexing document in OpenSearch (doc_id: {doc_id})")
    index_document(
        doc_id=doc_id,
        text=content,
        embedding=doc_embedding,
        metadata=metadata
    )
    logger.info(f"Document indexing complete (doc_id: {doc_id})")
    
    return {
        "status": "success",
        "document_id": doc_id,
        "s3_key": s3_key,
        "message": "Document uploaded to S3 and indexed successfully in OpenSearch"
    }

def handle_list_documents(params: dict):
    """Handles the rag_list_documents tool call."""
    # Add pagination parameters if needed (e.g., from, size)
    max_results = params.get("max_results", 100) # Example limit
    logger.info(f"Listing up to {max_results} documents from OpenSearch.")
    documents = list_all_documents(max_results=max_results)
    logger.info(f"Retrieved {len(documents)} documents.")
    return {"documents": documents}

# --- Main Lambda Handler ---

def main(event, context):
    """Main Lambda handler function invoked by API Gateway."""
    try:
        # --- API Key Authentication --- 
        expected_api_key = _get_app_api_key() # Get cached key
        # API Gateway v2 HTTP API passes headers potentially lowercase
        headers = event.get('headers', {})
        provided_api_key = headers.get('x-api-key') # Look for 'x-api-key' header (lowercase)

        # --- Add Debug Logging --- 
        logger.info(f"API Key Check: Expected key (len={len(expected_api_key) if expected_api_key else 0}): '{expected_api_key.strip() if expected_api_key else 'None'}'")
        logger.info(f"API Key Check: Provided key (len={len(provided_api_key) if provided_api_key else 0}) from header 'x-api-key': '{provided_api_key.strip() if provided_api_key else 'None'}'")
        # ---- End Debug ----

        # Use strip() in comparison just in case
        if not provided_api_key or provided_api_key.strip() != expected_api_key.strip():
            logger.warning("Unauthorized access attempt: Missing or invalid API Key.")
            return {
                "statusCode": 401, # Unauthorized
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Unauthorized"})
            }
        logger.info("API Key validated successfully.")
        # --- End Authentication ---

        # Simple routing based on HTTP method
        http_method = event.get('requestContext', {}).get('http', {}).get('method')
        path = event.get('requestContext', {}).get('http', {}).get('path')
        
        # Ensure clients are initialized (should be done outside, but double-check)
        if not os.environ.get('OPENSEARCH_COLLECTION_ENDPOINT'):
            logger.warning("Clients not initialized, attempting re-initialization...")
            initialize_clients()
        
        if path == "/mcp":
            if http_method == "GET":
                logger.info("Handling GET /mcp (Discovery)")
                return handle_discovery()
            elif http_method == "POST":
                logger.info("Handling POST /mcp (Execution)")
                try:
                    # API Gateway v2 HTTP API might pass body directly as string
                    body_str = event.get('body', '{}')
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    logger.error("Invalid JSON in request body")
                    return {
                        "statusCode": 400,
                        "headers": {"Content-Type": "application/json"},
                        "body": json.dumps({"error": "Invalid JSON body"})
                    }
                return handle_execution(body)
            else:
                logger.warning(f"Unsupported method: {http_method}")
                return {"statusCode": 405, "body": json.dumps({"error": "Method Not Allowed"})}
        else:
            logger.warning(f"Unsupported path: {path}")
            return {"statusCode": 404, "body": json.dumps({"error": "Not Found"})}

    except Exception as e:
        # Top-level error handler for unexpected issues (e.g., during client init)
        logger.exception(f"Unhandled exception in Lambda handler: {e}")
        # Use traceback.format_exc() for detailed stack trace in logs
        error_details = traceback.format_exc()
        logger.error(error_details)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal Server Error", "details": str(e)}) # Avoid sending full trace externally
        } 