"""Application settings loaded from environment variables.

Provides a simple `settings` object with common configuration values.
"""
import os
from dataclasses import dataclass
try:
    from dotenv import load_dotenv
except Exception:
    def load_dotenv():
        return None

load_dotenv()


@dataclass
class Settings:
    JIRA_SERVER: str = os.getenv("JIRA_SERVER", "").strip()
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "").strip()
    JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "").strip()
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    # Bitbucket auto-comment: "true" để bật, "false" hoặc bất kỳ giá trị nào khác để tắt
    BITBUCKET_AUTO_COMMENT: bool = os.getenv("BITBUCKET_AUTO_COMMENT", "true").lower() == "true"
    # Fallbacks / defaults
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
