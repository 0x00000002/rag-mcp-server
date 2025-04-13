"""RAG MCP Server implementation using ChromaDB, ready for cloud deployment."""
import logging
import hashlib
from typing import Dict, Any, Optional
from fastapi import FastAPI, Body, HTTPException, Depends
import chromadb
from chromadb.utils import embedding_functions
from chromadb.api.models.Collection import Collection
from openai import OpenAI, APIError
from botocore.exceptions import ClientError

# Import settings and utility function
from src.config import Settings, settings as app_settings # Rename for clarity inside functions
from src.utils import upload_document_to_s3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-mcp-server")

app = FastAPI(title="RAG MCP Server - Cloud Ready")

# --- Dependency Injection --- 

def get_settings() -> Settings:
    return app_settings

def get_openai_client(settings: Settings = Depends(get_settings)) -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)

def get_chroma_client(settings: Settings = Depends(get_settings)) -> chromadb.HttpClient:
    # Connect to ChromaDB over the network
    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)

def get_chroma_collection(
    settings: Settings = Depends(get_settings),
    chroma_client: chromadb.HttpClient = Depends(get_chroma_client),
    openai_client: OpenAI = Depends(get_openai_client) # Needed for embedding function API key
) -> Collection:
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=settings.openai_api_key,
        model_name=settings.openai_embedding_model
    )
    # Get or create collection
    return chroma_client.get_or_create_collection(
        name=settings.chroma_collection,
        embedding_function=openai_ef
    )
# --- End Dependency Injection ---

# MCP Discovery endpoint
@app.get("/mcp")
async def mcp_discovery():
    """Standard MCP discovery endpoint that lists available tools."""
    return {
        "tools": [
            {
                "name": "rag_query",
                "description": "Search the knowledge base for information relevant to a query",
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
                "description": "Add a document to the knowledge base (stored in S3 and indexed)",
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
                "description": "List all indexed documents in the knowledge base",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    }

# MCP Execution endpoint
@app.post("/mcp")
async def mcp_execution(
    request: Dict = Body(...),
    collection: Collection = Depends(get_chroma_collection),
    openai_client: OpenAI = Depends(get_openai_client),
    settings: Settings = Depends(get_settings)
):
    """Standard MCP execution endpoint that handles tool calls."""
    tool_name = request.get("name")
    params = request.get("parameters", {})
    
    try:
        if tool_name == "rag_query":
            return await handle_query(params, collection, openai_client, settings)
        elif tool_name == "rag_add_document":
            return await handle_add_document(params, collection, settings)
        elif tool_name == "rag_list_documents":
            return await handle_list_documents(collection)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
    except HTTPException as e:
        # Re-raise HTTPExceptions to let FastAPI handle them
        raise e
    except APIError as e:
        logger.error(f"OpenAI API Error calling tool '{tool_name}': {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI API Error: {str(e)}")
    except ClientError as e:
        logger.error(f"AWS Client Error calling tool '{tool_name}': {e}")
        raise HTTPException(status_code=500, detail=f"AWS Error: {e.response.get('Error', {}).get('Code', 'Unknown')}")
    except chromadb.errors.ChromaError as e:
        logger.error(f"ChromaDB Error calling tool '{tool_name}': {e}")
        raise HTTPException(status_code=500, detail=f"Database Error: {str(e)}")
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception(f"Unexpected error calling tool '{tool_name}': {e}") # Use logger.exception to include stack trace
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

async def handle_query(
    params: Dict[str, Any],
    collection: Collection, 
    openai_client: OpenAI,
    settings: Settings
):
    """Handle RAG query requests."""
    query = params.get("query")
    n_results = params.get("n_results", 3)
    
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required")
    
    # Query ChromaDB
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["metadatas", "documents", "distances"] # Ensure we get documents
    )
    
    # Get relevant documents from ChromaDB results
    documents = []
    if results and results['ids'] and results['ids'][0]:
        for i, doc_id in enumerate(results['ids'][0]):
            documents.append({
                "id": doc_id,
                "text": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "score": results['distances'][0][i] # Lower distance is better
            })
    else:
        # No results found, return empty answer or indicate no context?
        # For now, proceed with empty context
        logger.info(f"No documents found in ChromaDB for query: {query}")

    # Generate answer using OpenAI
    context = "\n\n".join([doc["text"] for doc in documents])
    
    completion = openai_client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that answers questions based on the provided context."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer:"}
        ]
    )
    
    return {
        "result": {
            "answer": completion.choices[0].message.content,
            "sources": documents # Include sources used
        }
    }

async def handle_add_document(
    params: Dict[str, Any],
    collection: Collection,
    settings: Settings
):
    """Handle adding documents to the knowledge base (S3 + ChromaDB)."""
    content = params.get("content")
    metadata = params.get("metadata", {})
    
    if not content:
        raise HTTPException(status_code=400, detail="Content parameter is required")
    
    # Generate a unique ID (using hash for idempotency, consider UUID if collisions are a concern)
    content_hash = hashlib.md5(content.encode()).hexdigest()
    doc_id = f"doc_{content_hash[:10]}" # Slightly longer hash part
    
    # Upload to S3
    s3_key = upload_document_to_s3(content, doc_id)
    
    # Add S3 key to metadata
    metadata["s3_key"] = s3_key
    metadata["original_doc_id"] = doc_id # Store the generated ID as well
    
    # Add to ChromaDB (ID must be unique string)
    # Note: We store the full content in ChromaDB for faster retrieval in handle_query
    # If documents are very large, consider storing only summaries/metadata in ChromaDB
    # and fetching full content from S3 on demand.
    collection.add(
        documents=[content],
        metadatas=[metadata],
        ids=[doc_id]
    )
    
    return {
        "result": {
            "status": "success",
            "document_id": doc_id,
            "s3_key": s3_key,
            "message": "Document uploaded to S3 and indexed successfully"
        }
    }

async def handle_list_documents(collection: Collection):
    """Handle listing all documents indexed in ChromaDB."""
    # Note: collection.get() can be inefficient for very large collections.
    # Consider pagination or filtering if needed.
    all_docs = collection.get(include=["metadatas", "documents"])
    
    documents = []
    if all_docs and all_docs['ids']:
        for i, doc_id in enumerate(all_docs['ids']):
            text = all_docs['documents'][i]
            preview = text[:100] + "..." if len(text) > 100 else text
            
            documents.append({
                "id": doc_id,
                "preview": preview,
                "metadata": all_docs['metadatas'][i]
            })
            
    return {"result": {"documents": documents}}