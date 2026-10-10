from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    google_api_key: str = ""
    model: str = "gemini-3.5-flash-lite"
    embed_model: str = "models/gemini-embedding-001"
    max_revisions: int = 2
    store_path: str = "data/store.json"
    cors_origins: str = "*"


settings = Settings()
llm = ChatGoogleGenerativeAI(model=settings.model, temperature=0, max_retries=3, timeout=90, google_api_key=settings.google_api_key)
embeddings = GoogleGenerativeAIEmbeddings(model=settings.embed_model, google_api_key=settings.google_api_key)
