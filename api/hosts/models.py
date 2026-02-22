from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class PortBannerOut(BaseModel):
    id: int
    banner_text: Optional[str]
    captured_at: datetime

    class Config:
        from_attributes = True


class PortScreenshotOut(BaseModel):
    id: int
    url_captured: Optional[str]
    captured_at: datetime
    screenshot_url: Optional[str] = None

    class Config:
        from_attributes = True


class HostPortOut(BaseModel):
    id: int
    port: int
    protocol: str
    state: str
    service_name: Optional[str]
    service_ver: Optional[str]
    is_new: bool
    first_seen: datetime
    last_seen: Optional[datetime]
    banner: Optional[str] = None
    screenshot_url: Optional[str] = None

    class Config:
        from_attributes = True


class HostHistoryOut(BaseModel):
    id: int
    event_type: str
    old_value: Optional[str]
    new_value: Optional[str]
    recorded_at: datetime

    class Config:
        from_attributes = True


class HostSummaryOut(BaseModel):
    id: int
    hostname: Optional[str]
    current_ip: str
    current_mac: Optional[str]
    vendor: Optional[str]
    os_guess: Optional[str]
    is_up: bool
    is_new: bool
    wol_enabled: bool
    first_seen: datetime
    last_seen: Optional[datetime]
    open_port_count: int = 0

    class Config:
        from_attributes = True


class HostDetailOut(BaseModel):
    id: int
    hostname: Optional[str]
    current_ip: str
    current_mac: Optional[str]
    vendor: Optional[str]
    os_guess: Optional[str]
    is_up: bool
    is_new: bool
    wol_enabled: bool
    notes: Optional[str]
    first_seen: datetime
    last_seen: Optional[datetime]
    ports: List[HostPortOut] = []
    history: List[HostHistoryOut] = []

    class Config:
        from_attributes = True


class HostUpdate(BaseModel):
    notes: Optional[str] = None
    wol_enabled: Optional[bool] = None
    is_new: Optional[bool] = None


class PaginatedHosts(BaseModel):
    total: int
    page: int
    per_page: int
    hosts: List[HostSummaryOut]
