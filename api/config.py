import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    SCREENSHOT_DIR: str = os.getenv("SCREENSHOT_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "screenshots"))
    SCREENSHOT_TIMEOUT_MS: int = int(os.getenv("SCREENSHOT_TIMEOUT_MS", 8000))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    NMAP_PATH: str = os.getenv("NMAP_PATH", "/usr/bin/nmap")
    MAX_SCAN_CONCURRENCY: int = int(os.getenv("MAX_SCAN_CONCURRENCY", 50))

    # DHCP hostname scraper
    ROUTER_URL: str = os.getenv("ROUTER_URL", "")
    ROUTER_USERNAME: str = os.getenv("ROUTER_USERNAME", "admin")
    ROUTER_PASSWORD: str = os.getenv("ROUTER_PASSWORD", "")
    ROUTER_DHCP_PATH: str = os.getenv("ROUTER_DHCP_PATH", "")
    DHCP_SCRAPE_INTERVAL_MIN: int = int(os.getenv("DHCP_SCRAPE_INTERVAL_MIN", 30))

    # Traffic statistics scraper
    TRAFFIC_SCRAPE_INTERVAL_MIN: int = int(os.getenv("TRAFFIC_SCRAPE_INTERVAL_MIN", 30))

    # Traffic data retention
    INTERFACE_TRAFFIC_RETENTION_DAYS: int = int(os.getenv("INTERFACE_TRAFFIC_RETENTION_DAYS", 730))
    HOST_TRAFFIC_RETENTION_DAYS: int = int(os.getenv("HOST_TRAFFIC_RETENTION_DAYS", 30))

    # Wireless AP scraper
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "")
    WIRELESS_SCRAPE_INTERVAL_MIN: int = int(os.getenv("WIRELESS_SCRAPE_INTERVAL_MIN", 5))


settings = Settings()
