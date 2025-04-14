"""Configuration settings for the RAG MCP server using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings
from pydantic import Field, ConfigDict # Import ConfigDict

class Settings(BaseSettings):
    # OpenAI Settings
    openai_api_key_secret_name: str = Field(..., alias='OPENAI_API_KEY_SECRET_NAME') # Use alias to match env var exactly
    openai_embedding_model: str = Field("text-embedding-ada-002", alias='OPENAI_EMBEDDING_MODEL')
    openai_chat_model: str = Field("gpt-3.5-turbo", alias='OPENAI_CHAT_MODEL')

    # AWS Settings
    aws_region: str = Field(..., alias='AWS_REGION')
    documents_s3_bucket: str = Field(..., alias='DOCUMENTS_S3_BUCKET')

    # OpenSearch Settings
    opensearch_collection_endpoint: str = Field(..., alias='OPENSEARCH_COLLECTION_ENDPOINT')
    opensearch_index_name: str = Field("documents", alias='OPENSEARCH_INDEX_NAME')

    # Logging Settings (Optional)
    log_level: str = Field("INFO", alias='LOG_LEVEL')

    # Removed ChromaDB settings: chroma_host, chroma_port, chroma_collection
    # Note: openai_api_key is now fetched within the Lambda using the secret name

    model_config = ConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore' # Good practice to ignore extra env vars not defined in Settings
    )

# Create a single instance of the settings to be imported
settings = Settings() 