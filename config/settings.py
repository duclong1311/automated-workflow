"""
Configuration settings cho ứng dụng
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Jira Configuration
    JIRA_SERVER = os.getenv("JIRA_SERVER", "").strip()
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "").strip()
    JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "").strip()
    
    # Gemini AI Configuration
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    
    # Timeout Configuration
    AI_TIMEOUT = 2.8  # 2.8s cho AI
    WEBHOOK_RESPONSE_TIMEOUT = 4.9  # Tổng <5s
    
    # Bot Configuration
    BOT_MENTION_NAME = "JiraBot"
    
    # Server Configuration
    HOST = "0.0.0.0"
    PORT = 8000
    # Optional Bitbucket API config (used to fetch commit details when refs_changed payload lacks messages)
    BITBUCKET_BASE_URL = os.getenv("BITBUCKET_BASE_URL", "").strip()
    BITBUCKET_USER = os.getenv("BITBUCKET_USER", "").strip()
    BITBUCKET_TOKEN = os.getenv("BITBUCKET_TOKEN", "").strip()

settings = Settings()
