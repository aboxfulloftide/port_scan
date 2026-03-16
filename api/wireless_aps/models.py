from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class WirelessAPCreate(BaseModel):
    name: str
    brand: str  # "tplink_deco" | "netgear"
    url: str
    username: Optional[str] = None
    password: str  # plaintext — will be encrypted before storage
    enabled: bool = True
    notes: Optional[str] = None
    scrape_interval_min: int = 5


class WirelessAPUpdate(BaseModel):
    name: Optional[str] = None
    brand: Optional[str] = None
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # plaintext — re-encrypted if provided
    enabled: Optional[bool] = None
    notes: Optional[str] = None
    scrape_interval_min: Optional[int] = None


class WirelessAPOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    brand: str
    url: str
    username: Optional[str] = None
    enabled: bool
    notes: Optional[str] = None
    last_scraped: Optional[datetime] = None
    scrape_interval_min: int
    created_at: datetime
    updated_at: datetime
    password_set: bool = False
