#!/usr/bin/env python3
"""Example script to interact with the deployed RAG MCP Server API."""

import os
import json
import requests
import sys

# --- Configuration ---
# Read API endpoint URL and API Key from environment variables
API_URL = os.environ.get("API_URL")
API_KEY = os.environ.get("API_KEY")

# --- Helper Functions ---

def make_request(method: str, endpoint: str, payload: dict = None):
    """Helper function to make requests to the API."""
    if not API_URL or not API_KEY:
        print("Error: Please set the API_URL and API_KEY environment variables.")
        print("  export API_URL='https://....'")
        print("  export API_KEY='your-secret-api-key'")
        sys.exit(1)

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    full_url = API_URL.rstrip('/') + endpoint
    
    try:
        if method.upper() == "GET":
            response = requests.get(full_url, headers=headers)
        elif method.upper() == "POST":
            response = requests.post(full_url, headers=headers, json=payload)
        else:
            print(f"Error: Unsupported method '{method}'")
            return None

        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Error making request to {full_url}: {e}")
        if e.response is not None:
            print(f"Response status: {e.response.status_code}")
            try:
                print(f"Response body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response body: {e.response.text}")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {full_url}")
        print(f"Response text: {response.text}")
        return None


# --- API Call Functions ---

def get_discovery():
    """Call the MCP discovery endpoint."""
    print("--- Calling Discovery (GET /mcp) ---")
    result = make_request("GET", "/mcp")
    if result:
        print(json.dumps(result, indent=2))
    print("-"*30)

def add_document(content: str, metadata: dict = None):
    """Call the rag_add_document tool."""
    print(f"--- Calling Add Document (POST /mcp) ---")
    payload = {
        "name": "rag_add_document",
        "parameters": {
            "content": content,
            "metadata": metadata or {}
        }
    }
    print(f"Payload: {json.dumps(payload)}")
    result = make_request("POST", "/mcp", payload=payload)
    if result:
        print(f"Response: {json.dumps(result, indent=2)}")
    print("-"*30)
    return result

def list_documents():
    """Call the rag_list_documents tool."""
    print(f"--- Calling List Documents (POST /mcp) ---")
    payload = {
        "name": "rag_list_documents",
        "parameters": {}
    }
    result = make_request("POST", "/mcp", payload=payload)
    if result:
        print(f"Response: {json.dumps(result, indent=2)}")
    print("-"*30)
    return result

def query_documents(query: str, n_results: int = 3):
    """Call the rag_query tool."""
    print(f"--- Calling Query (POST /mcp) ---")
    payload = {
        "name": "rag_query",
        "parameters": {
            "query": query,
            "n_results": n_results
        }
    }
    print(f"Payload: {json.dumps(payload)}")
    result = make_request("POST", "/mcp", payload=payload)
    if result:
        print(f"Response: {json.dumps(result, indent=2)}")
    print("-"*30)
    return result


# --- Main Execution --- 

if __name__ == "__main__":
    print("Running RAG MCP Server API Example...")
    
    # 1. Check Discovery
    get_discovery()
    
    # 2. Add a document
    add_resp = add_document(
        content="The first rule of Fight Club is: You do not talk about Fight Club.", 
        metadata={"source": "movie_quote", "year": 1999}
    )
    
    # 3. Add another document
    add_resp_2 = add_document(
        content="The second rule of Fight Club is: You DO NOT talk about Fight Club!", 
        metadata={"source": "movie_quote", "year": 1999, "emphasis": True}
    )
    
    # Wait a moment for indexing (OpenSearch refresh might take a second)
    print("\n(Waiting a few seconds for indexing...)\n")
    import time
    time.sleep(5)
    
    # 4. List documents
    list_documents()
    
    # 5. Query documents
    query_documents(query="What are the rules of Fight Club?", n_results=2)
    
    print("Example script finished.") 