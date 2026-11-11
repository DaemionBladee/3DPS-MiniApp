"""Export schemas with synthetic configuration, without DB or Telegram access."""

import json
from pathlib import Path

from app.core.config import Settings
from app.main import create_app

settings = Settings(
    _env_file=None,
    app_env="test",
    database_url="postgresql+asyncpg://unused:unused@127.0.0.1/3dps_test_schema_only",
    bot_token="123456789:synthetic-schema-export-token-never-used",
    session_secret="schema-export-only-not-a-runtime-secret-000000000",
    public_base_url="https://schema.test",
)
schema = create_app(settings).openapi()
Path(__file__).resolve().parents[1].joinpath("openapi.json").write_text(
    json.dumps(schema, indent=2, sort_keys=True) + "\n"
)
print("Exported OpenAPI without connecting to a database or Telegram.")
