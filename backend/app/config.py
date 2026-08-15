import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    temporal_host: str = os.getenv("TEMPORAL_HOST", "localhost:7233")
    temporal_namespace: str = os.getenv("TEMPORAL_NAMESPACE", "default")
    temporal_task_queue: str = os.getenv(
        "TEMPORAL_TASK_QUEUE", "order-supervisor-queue"
    )

    supabase_db_url: str = os.getenv("SUPABASE_DB_URL", "")

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    # Test-only switches retained from Phase 2. Keep disabled normally.
    phase2_force_bad_gemini_json: bool = _as_bool(
        os.getenv("PHASE2_FORCE_BAD_GEMINI_JSON"), False
    )
    phase2_test_force_disallowed_tool: str = os.getenv(
        "PHASE2_TEST_FORCE_DISALLOWED_TOOL", ""
    ).strip()


settings = Settings()
