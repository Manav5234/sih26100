"""Settings — one place every consumer (app, alembic, scripts) reads env from.

backend/.env is located relative to THIS file, never relative to the current
working directory, so a fresh terminal with no env vars set still gets the
local-dev values. Real environment variables always win over the file
(`override=False` here, and dotenv < env in pydantic-settings' own precedence),
so docker-compose and CI keep working unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env (config.py lives in backend/app/)
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Side effect for anything that reads os.environ directly (alembic, ad-hoc
# scripts): same file, same precedence — env vars still win (override=False).
load_dotenv(ENV_FILE, override=False)

# UPLOAD_ROOT is allowed to be written relative ("./uploads") — pin it beside
# backend/.env so uploads land in one place whatever directory started the
# process. Absolute values (docker's /data/uploads) are left alone.
if os.environ.get("UPLOAD_ROOT") and not Path(os.environ["UPLOAD_ROOT"]).is_absolute():
    os.environ["UPLOAD_ROOT"] = str((ENV_FILE.parent / os.environ["UPLOAD_ROOT"]).resolve())


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@postgres:5432/sih26100"
    jwt_secret: str = "demo-secret-key-sih26100-verifypal"
    allowed_origins: str = "http://localhost:3000"
    # LLM used for tender/bidder requirement extraction (schema-strict JSON).
    # Points at a local Ollama server by default — no external API key.
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "gemma4"
    # seconds before the Ollama call is abandoned -> template_fallback
    llm_timeout: float = 300.0

    # consumed by app.storage (declared here so .env keys are typed, not
    # rejected as unknown by BaseSettings' extra="forbid")
    upload_root: str = "/tmp/uploads" if os.environ.get("VERCEL") else "/data/uploads"
    max_image_dimension: int = 2000

    model_config = SettingsConfigDict(env_file=ENV_FILE)

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()
