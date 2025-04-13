"""Configuration settings for the RAG MCP server using Pydantic BaseSettings."""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    chroma_host: str = "localhost"  # Default for local, override in env
    chroma_port: int = 8000         # Default for local, override in env
    chroma_collection: str = "documents"
    openai_embedding_model: str = "text-embedding-ada-002"
    openai_chat_model: str = "gpt-3.5-turbo"
    documents_s3_bucket: str
    aws_region: str = "us-east-1" # Default, override if needed

    class Config:
        # Load .env file if it exists (useful for local development)
        env_file = '.env'
        env_file_encoding = 'utf-8'

# Create a single instance of the settings to be imported
settings = Settings() 