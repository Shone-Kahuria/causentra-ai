"""Load the local ignored .env file without executing its contents."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED = {
    "CAUSENTRA_ANALYST_TOKEN", "CAUSENTRA_MANAGER_TOKEN", "CAUSENTRA_DB", "CAUSENTRA_TOKENS_JSON",
    "AMD_CHAT_COMPLETIONS_URL", "AMD_MODEL_ID", "AMD_API_KEY",
    "EVOLUS_API_KEY", "EVOLUS_APPLICATION_ID", "EVOLUS_WORKFLOW_ID", "EVOLUS_AI_TOOL",
    "EVOLUS_SANDBOX_CONFIRMED", "EVOLUS_BASE_URL",
}


def load_local_env(path: Path = ROOT / ".env"):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key not in ALLOWED:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if value:
            os.environ.setdefault(key, value)


load_local_env()
