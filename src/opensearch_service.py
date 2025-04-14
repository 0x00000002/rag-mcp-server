"""Service layer for interacting with AWS OpenSearch Serverless."""

import logging
import boto3
from opensearchpy import (
    OpenSearch, RequestsHttpConnection, AWSV4SignerAuth
)
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)

# Global OpenSearch client instance (initialized later)
_opensearch_client = None
_index_name = None

def _get_aws_credentials():
    """Retrieves AWS credentials using boto3 session."""
    # Boto3 will automatically handle credentials from the Lambda execution environment
    session = boto3.Session()
    return session.get_credentials()

def initialize_opensearch_client(endpoint: str, region: str, index: str):
    """Initializes the OpenSearch client for Serverless."""
    global _opensearch_client, _index_name
    if _opensearch_client is None:
        logger.info(f"Initializing OpenSearch client for endpoint: {endpoint}")
        credentials = _get_aws_credentials()
        auth = AWSV4SignerAuth(credentials, region, 'aoss') # 'aoss' for OpenSearch Serverless

        # Strip https:// from endpoint if present
        host = endpoint.replace("https://", "")

        _opensearch_client = OpenSearch(
            hosts=[{'host': host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
            pool_maxsize=20 # Adjust as needed
        )
        _index_name = index
        logger.info(f"OpenSearch client initialized. Target index: {_index_name}")
    return _opensearch_client

def get_opensearch_client() -> OpenSearch:
    """Returns the initialized OpenSearch client."""
    if _opensearch_client is None:
        raise Exception("OpenSearch client not initialized. Call initialize_opensearch_client first.")
    return _opensearch_client

def create_index_if_not_exists(embedding_dimension: int = 1536): # Default for ada-002
    """Creates the OpenSearch index with k-NN mapping if it doesn't exist."""
    client = get_opensearch_client()
    if not client.indices.exists(index=_index_name):
        logger.info(f"Index '{_index_name}' not found. Creating...")
        settings = {
            "index": {
                "knn": True,
                "knn.algo_param.ef_search": 100 # Tune as needed
            }
        }
        mappings = {
            "properties": {
                "embedding": {
                    "type": "knn_vector",
                    "dimension": embedding_dimension,
                    "method": {
                        "name": "hnsw", # Hierarchical Navigable Small Worlds (common for k-NN)
                        "space_type": "l2", # Euclidean distance (or cosine, innerproduct)
                        "engine": "nmslib", # Or faiss
                        "parameters": {
                            "ef_construction": 256, # Tune as needed
                            "m": 48             # Tune as needed
                        }
                    }
                },
                "text": { # Store the original text
                    "type": "text"
                },
                "s3_key": { # Store S3 key metadata
                    "type": "keyword"
                },
                "original_doc_id": { # Store original ID if needed
                     "type": "keyword"
                }
                # Add other metadata fields as needed
            }
        }
        try:
            response = client.indices.create(
                index=_index_name,
                body={
                    "settings": settings,
                    "mappings": mappings
                }
            )
            logger.info(f"Index '{_index_name}' created successfully: {response}")
        except Exception as e:
            logger.error(f"Failed to create index '{_index_name}': {e}")
            raise
    else:
        logger.info(f"Index '{_index_name}' already exists.")

def index_document(doc_id: str, text: str, embedding: list[float], metadata: dict):
    """Indexes a single document into OpenSearch."""
    client = get_opensearch_client()
    document_body = {
        "embedding": embedding,
        "text": text,
        **metadata # Add other metadata fields directly
    }
    try:
        response = client.index(
            index=_index_name,
            id=doc_id,
            body=document_body,
            refresh=True # Refresh immediately for demo purposes, consider false/wait_for in prod
        )
        logger.info(f"Indexed document ID '{doc_id}': {response['result']}")
        return response
    except Exception as e:
        logger.error(f"Failed to index document ID '{doc_id}': {e}")
        raise

def search_documents(query_embedding: list[float], n_results: int = 3) -> list[dict]:
    """Performs a k-NN vector search in OpenSearch."""
    client = get_opensearch_client()
    search_body = {
        "size": n_results,
        "_source": { "excludes": ["embedding"] }, # Exclude the large embedding vector from results
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_embedding,
                    "k": n_results
                }
            }
        }
    }
    try:
        response = client.search(
            index=_index_name,
            body=search_body
        )
        
        results = []
        for hit in response['hits']['hits']:
            result = {
                "id": hit['_id'],
                "score": hit['_score'], # OpenSearch k-NN score (higher is better, typically 1 / (1 + L2 distance))
                "text": hit['_source'].get('text'),
                "metadata": {
                    k: v for k, v in hit['_source'].items() if k != 'text' # Collect metadata
                }
            }
            results.append(result)
            
        logger.info(f"Found {len(results)} documents for query.")
        return results
    except Exception as e:
        logger.error(f"Failed to search documents: {e}")
        # Handle cases where the index might not exist yet gracefully
        if "index_not_found_exception" in str(e):
             logger.warning(f"Search failed because index '{_index_name}' does not exist.")
             return [] # Return empty list if index doesn't exist
        raise

def list_all_documents(max_results: int = 1000) -> list[dict]:
    """Lists documents from OpenSearch (use cautiously on large indices)."""
    client = get_opensearch_client()
    # Simple match_all query, limited by size. Consider scroll API for very large indices.
    search_body = {
        "size": max_results,
        "_source": { "excludes": ["embedding"] },
        "query": {
            "match_all": {}
        }
    }
    try:
        response = client.search(
            index=_index_name,
            body=search_body
        )
        
        documents = []
        if response['hits']['hits']:
            for hit in response['hits']['hits']:
                text = hit['_source'].get('text', '')
                preview = text[:100] + "..." if len(text) > 100 else text
                documents.append({
                    "id": hit['_id'],
                    "preview": preview,
                    "metadata": {
                         k: v for k, v in hit['_source'].items() if k != 'text'
                     }
                })
        logger.info(f"Retrieved {len(documents)} documents.")
        return documents
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        if "index_not_found_exception" in str(e):
             logger.warning(f"List failed because index '{_index_name}' does not exist.")
             return [] # Return empty list if index doesn't exist
        raise

# Consider adding functions for deleting documents, updating, etc. if needed 