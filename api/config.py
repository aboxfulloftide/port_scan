import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    SCREENSHOT_DIR: str = os.getenv("SCREENSHOT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    NMAP_PATH: str = os.getenv("NMAP_PATH", "/usr/bin/nmap")
    MAX_SCAN_CONCURRENCY: int = int(os.getenv("MAX_SCAN_CONCURRENCY", 50))


settings = Settings()
