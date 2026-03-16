from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel


class InterfaceTrafficOut(BaseModel):
    id: int
    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    scraped_at: datetime

    class Config:
        from_attributes = True


class HostTrafficOut(BaseModel):
    id: int
    ip_address: str
    host_id: Optional[int] = None
    hostname: Optional[str] = None
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    scraped_at: datetime

    class Config:
        from_attributes = True


class InterfaceHistoryPoint(BaseModel):
    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    scraped_at: datetime

    class Config:
        from_attributes = True


class HostTrafficHistoryPoint(BaseModel):
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    scraped_at: datetime

    class Config:
        from_attributes = True


class DailyInterfaceTraffic(BaseModel):
    interface: str
    day: date
    bytes_sent: int
    bytes_recv: int


class TrafficSyncResult(BaseModel):
    interfaces: int
    hosts: int
