from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/sih26100"
    jwt_secret: str
    allowed_origins: str = "http://localhost:3000"
    # LLM used for tender requirement extraction (schema-strict JSON).
    # Points at a local Ollama server by default — no external API key.
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "gemma4"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
