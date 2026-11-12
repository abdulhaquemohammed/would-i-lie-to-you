"""M1: every setting in one place. Values come from environment variables (.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int_or_none(value):
    return int(value) if value not in (None, "") else None


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-only-change-me")

    # Local AI (Ollama, free, runs on this laptop)
    OLLAMA_URL = os.getenv("WILTY_OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("WILTY_OLLAMA_MODEL", "llama3.2:3b")
    OLLAMA_TIMEOUT_SECONDS = 90

    # Game rules
    PLAYERS_PER_TEAM = 3
    STORIES_PER_PLAYER = 2
    REGULAR_ROUNDS = 6
    TIMER_SECONDS = int(os.getenv("WILTY_TIMER_SECONDS", "600"))  # 10 minutes
    EXTRA_LIES = 4  # spare lies generated for sudden death

    # Lie repeats
    NO_REPEAT_GAMES = 10

    # Randomness: set WILTY_SEED for repeatable games (tests use this)
    RANDOM_SEED = _int_or_none(os.getenv("WILTY_SEED"))

    # Files
    LIE_BANK_PATH = BASE_DIR / "data" / "lie_bank.json"
    LIE_HISTORY_PATH = Path(os.getenv("WILTY_HISTORY_PATH", str(BASE_DIR / "data" / "lie_history.json")))
