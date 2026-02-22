from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime
from croniter import croniter


class ScheduleCreate(BaseModel):
    name: str
    profile_id: int
    subnet_ids: List[int]
    cron_expression: str

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v):
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v

    @field_validator("subnet_ids")
    @classmethod
    def validate_subnets(cls, v):
        if not v:
            raise ValueError("At least one subnet_id is required")
        return v


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    profile_id: Optional[int] = None
    subnet_ids: Optional[List[int]] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None


class ScheduleOut(BaseModel):
    id: int
    name: str
    profile_id: int
    profile_name: Optional[str] = None
    subnet_ids: List[int]
    cron_expression: str
    is_active: bool
    created_at: datetime
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]

    class Config:
        from_attributes = True
