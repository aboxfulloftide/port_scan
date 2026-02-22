from pydantic import BaseModel
from typing import Optional, List, Union
from datetime import datetime


class ScanTriggerRequest(BaseModel):
    profile_id: int
    subnet_ids: List[int]


class ScanJobSummaryOut(BaseModel):
    id: int
    profile_id: int
    profile_name: Optional[str] = None
    status: str
    hosts_discovered: Optional[int] = None
    hosts_up: Optional[int] = None
    new_hosts_found: Optional[int] = None
    new_ports_found: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    triggered_by: Optional[Union[str, int]] = None   # int from ORM, enriched to str username
    created_at: datetime

    class Config:
        from_attributes = True


class ScanJobDetailOut(ScanJobSummaryOut):
    subnet_ids: List[int] = []
    progress_percent: Optional[int] = None
    current_tier: Optional[str] = None
    error_message: Optional[str] = None


class PaginatedScans(BaseModel):
    total: int
    scans: List[ScanJobSummaryOut]
