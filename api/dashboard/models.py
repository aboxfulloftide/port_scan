from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class SubnetSummary(BaseModel):
    id: int
    cidr: str
    label: str
    host_count: int
    up_count: int


class RecentScan(BaseModel):
    id: int
    profile_name: Optional[str]
    status: str
    hosts_discovered: Optional[int]
    hosts_up: Optional[int]
    new_hosts_found: Optional[int]
    new_ports_found: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class DashboardStats(BaseModel):
    total_hosts: int
    hosts_up: int
    hosts_down: int
    new_hosts: int
    new_ports: int
    total_subnets: int
    active_scans: int
    subnets: List[SubnetSummary]
    recent_scans: List[RecentScan]
    last_scan_at: Optional[datetime]
