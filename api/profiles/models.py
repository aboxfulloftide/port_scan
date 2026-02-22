from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import re

PORT_RANGE_PATTERN = re.compile(r'^(\d+(-\d+)?)(,\d+(-\d+)?)*$')

DEFAULT_PROFILE_NAMES = {"Quick Ping", "Standard", "Full Deep Scan"}


class ProfileCreate(BaseModel):
    name: str
    description: Optional[str] = None
    port_range: str = "1-65535"
    enable_icmp: bool = True
    enable_tcp_syn: bool = True
    enable_udp: bool = False
    enable_fingerprint: bool = True
    enable_banner: bool = True
    enable_screenshot: bool = True
    max_concurrency: int = 50
    rate_limit: Optional[int] = None
    timeout_sec: int = 30

    @field_validator("port_range")
    @classmethod
    def validate_port_range(cls, v):
        if not PORT_RANGE_PATTERN.match(v):
            raise ValueError("Invalid port range format. Use e.g. '1-1024,8080,8443'")
        for part in v.split(","):
            if "-" in part:
                start, end = part.split("-")
                if not (1 <= int(start) <= 65535 and 1 <= int(end) <= 65535 and int(start) <= int(end)):
                    raise ValueError(f"Port range {part} is invalid")
            else:
                if not (1 <= int(part) <= 65535):
                    raise ValueError(f"Port {part} is out of range")
        return v

    @field_validator("max_concurrency")
    @classmethod
    def validate_concurrency(cls, v):
        if not (1 <= v <= 200):
            raise ValueError("max_concurrency must be between 1 and 200")
        return v


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    port_range: Optional[str] = None
    enable_icmp: Optional[bool] = None
    enable_tcp_syn: Optional[bool] = None
    enable_udp: Optional[bool] = None
    enable_fingerprint: Optional[bool] = None
    enable_banner: Optional[bool] = None
    enable_screenshot: Optional[bool] = None
    max_concurrency: Optional[int] = None
    rate_limit: Optional[int] = None
    timeout_sec: Optional[int] = None


class ProfileOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    port_range: str
    enable_icmp: bool
    enable_tcp_syn: bool
    enable_udp: bool
    enable_fingerprint: bool
    enable_banner: bool
    enable_screenshot: bool
    max_concurrency: int
    rate_limit: Optional[int] = None
    timeout_sec: int
    created_at: datetime

    class Config:
        from_attributes = True
