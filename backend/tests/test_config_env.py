"""backend/.env is loaded from a path relative to app/config.py, and real
environment variables always win over the file — so a fresh terminal with no
env vars set still boots, and docker-compose/CI overrides are never swallowed.
"""
from pathlib import Path

from app.config import ENV_FILE, Settings


def test_env_file_sits_beside_backend_and_exists():
    backend = Path(__file__).resolve().parent.parent
    assert ENV_FILE == backend / ".env"
    assert ENV_FILE.exists() or (backend / ".env.example").exists(), "backend/.env or .env.example ships with the repo for local dev"


def test_real_env_var_beats_dotenv_file(monkeypatch, tmp_path):
    file_env = tmp_path / ".env"
    file_env.write_text("JWT_SECRET=from-file\n")
    monkeypatch.setenv("JWT_SECRET", "from-shell")

    assert Settings(_env_file=file_env).jwt_secret == "from-shell"  # noqa: S105


def test_dotenv_file_is_used_when_env_absent(monkeypatch, tmp_path):
    file_env = tmp_path / ".env"
    file_env.write_text("JWT_SECRET=from-file\n")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    assert Settings(_env_file=file_env).jwt_secret == "from-file"  # noqa: S105


def test_local_defaults_are_usable_without_shell_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    s = Settings()
    assert "localhost" in s.database_url          # not the docker hostname
    assert Path(s.upload_root).is_absolute()      # ready for Path(...)
    assert s.allowed_origins_list == ["http://localhost:3000"]
