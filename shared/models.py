from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, Boolean, DateTime, Text, Enum,
    ForeignKey, JSON, SmallInteger, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(Enum("admin", "operator", "viewer"), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User")


class Subnet(Base):
    __tablename__ = "subnets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    cidr: Mapped[str] = mapped_column(String(18), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Host(Base):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    current_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    current_mac: Mapped[Optional[str]] = mapped_column(String(17), nullable=True, index=True)
    subnet_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subnets.id", ondelete="SET NULL"), nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    os_guess: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    wol_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    subnet: Mapped[Optional["Subnet"]] = relationship("Subnet")
    ports: Mapped[list["HostPort"]] = relationship("HostPort", back_populates="host", cascade="all, delete-orphan")
    history: Mapped[list["HostHistory"]] = relationship("HostHistory", back_populates="host", cascade="all, delete-orphan")


class HostHistory(Base):
    __tablename__ = "host_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(Enum("ip_change", "mac_change", "hostname_change", "status_change"), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    scan_job_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    host: Mapped["Host"] = relationship("Host", back_populates="history")


class HostPort(Base):
    __tablename__ = "host_ports"
    __table_args__ = (
        UniqueConstraint("host_id", "port", "protocol", name="uq_host_port_proto"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    port: Mapped[int] = mapped_column(SmallInteger, nullable=False, index=True)
    protocol: Mapped[str] = mapped_column(Enum("tcp", "udp"), nullable=False, default="tcp")
    state: Mapped[str] = mapped_column(Enum("open", "closed", "filtered"), nullable=False)
    service_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    service_ver: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    host: Mapped["Host"] = relationship("Host", back_populates="ports")
    banners: Mapped[list["PortBanner"]] = relationship("PortBanner", back_populates="host_port", cascade="all, delete-orphan")
    screenshots: Mapped[list["PortScreenshot"]] = relationship("PortScreenshot", back_populates="host_port", cascade="all, delete-orphan")


class PortBanner(Base):
    __tablename__ = "port_banners"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_port_id: Mapped[int] = mapped_column(ForeignKey("host_ports.id", ondelete="CASCADE"), nullable=False)
    banner_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    host_port: Mapped["HostPort"] = relationship("HostPort", back_populates="banners")


class PortScreenshot(Base):
    __tablename__ = "port_screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_port_id: Mapped[int] = mapped_column(ForeignKey("host_ports.id", ondelete="CASCADE"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    url_captured: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    host_port: Mapped["HostPort"] = relationship("HostPort", back_populates="screenshots")


class ScanProfile(Base):
    __tablename__ = "scan_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    port_range: Mapped[str] = mapped_column(String(255), nullable=False, default="1-65535")
    enable_icmp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_tcp_syn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_udp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enable_fingerprint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_banner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enable_screenshot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    max_concurrency: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=50)
    rate_limit: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    timeout_sec: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=30)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("scan_profiles.id"), nullable=False)
    subnet_ids: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(Enum("queued", "running", "completed", "failed", "cancelled"), nullable=False, default="queued")
    triggered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hosts_discovered: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    hosts_up: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    new_hosts_found: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    new_ports_found: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    profile: Mapped["ScanProfile"] = relationship("ScanProfile")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    profile_id: Mapped[int] = mapped_column(ForeignKey("scan_profiles.id"), nullable=False)
    subnet_ids: Mapped[dict] = mapped_column(JSON, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class WolSchedule(Base):
    __tablename__ = "wol_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    host: Mapped["Host"] = relationship("Host")


class WolLog(Base):
    __tablename__ = "wol_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False)
    mac_used: Mapped[str] = mapped_column(String(17), nullable=False)
    triggered_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    schedule_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
