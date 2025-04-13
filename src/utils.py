"""Utility functions for the RAG MCP server, focused on AWS integration."""
import logging
import boto3
from botocore.exceptions import ClientError
from src.config import settings # Import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-mcp-utils")

# Initialize S3 client once
s3_client = boto3.client("s3", region_name=settings.aws_region)

def upload_document_to_s3(content: str, doc_id: str) -> str:
    """Upload document content to S3 and return the S3 object key."""
    s3_key = f"documents/{doc_id}.txt" # Define a structure within the bucket
    bucket_name = settings.documents_s3_bucket
    
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=content.encode('utf-8') # Encode content to bytes
        )
        logger.info(f"Successfully uploaded {s3_key} to bucket {bucket_name}")
        return s3_key
    except ClientError as e:
        logger.error(f"Failed to upload {s3_key} to {bucket_name}: {e}")
        # Depending on requirements, you might want to raise the exception
        # or return an indicator of failure
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during S3 upload: {e}")
        raise

# Removed ensure_directories, save_document (to file), get_document_preview