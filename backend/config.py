"""Settings read from the environment, with defaults for a classroom demo.

A ``.env`` file next to this module is loaded if it exists. Values already
set in the real environment win, so a host such as PythonAnywhere can inject
secrets without a file.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv():
    """Copy KEY=VALUE lines from ``backend/.env`` into the process environment.

    Blank lines and lines starting with ``#`` are ignored. Existing
    environment variables are left unchanged.
    """
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _int(name, default):
    """Return the integer in environment variable ``name``, or ``default``."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str(name, default):
    """Return the string in environment variable ``name``, or ``default``."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


_load_dotenv()

GOOGLE_API_KEY = _str("GOOGLE_API_KEY", "")
GROQ_API_KEY = _str("GROQ_API_KEY", "")
LLM_PROVIDER = _str("LLM_PROVIDER", "gemini").lower()

GEMINI_CHAT_MODEL = _str("GEMINI_CHAT_MODEL", "gemini-3.8-flash")
GEMINI_EMBED_MODEL = _str("GEMINI_EMBED_MODEL", "gemini-embedding-2")
GEMINI_THINKING_LEVEL = _str("GEMINI_THINKING_LEVEL", "low")
GROQ_CHAT_MODEL = _str("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")

EMBED_DIM = _int("EMBED_DIM", 768)
CHUNK_SIZE = _int("CHUNK_SIZE", 800)
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 120)
TOP_K = _int("TOP_K", 4)
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)

CORS_ORIGINS = _str("CORS_ORIGINS", "*")
DATA_DIR = Path(_str("DATA_DIR", str(BASE_DIR / "data")))
SQLITE_PATH = DATA_DIR / "rag.sqlite"

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt"}
EXCERPT_CHARS = 400
REQUEST_TIMEOUT_SECONDS = 90
