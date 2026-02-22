from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
import ipaddress


class SubnetCreate(BaseModel):
    label: str
    cidr: str
    description: Optional[str] = None

    @field_validator("cidr")
    @classmethod
    def validate_cidr(cls, v):
        try:
            network = ipaddress.IPv4Network(v, strict=False)
            return str(network)
        except ValueError:
            raise ValueError(f"Invalid IPv4 CIDR: {v}")


class SubnetUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SubnetOut(BaseModel):
    id: int
    label: str
    cidr: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
