import uuid
from datetime import datetime, timezone
from typing import Optional, List
from flask_alembic import Alembic
from flask_login import UserMixin
from sqlalchemy import String, ForeignKey, DateTime, Integer, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from flask_sqlalchemy_lite import SQLAlchemy

# Initialize extensions (to be attached to app later)
db = SQLAlchemy()

class Base(DeclarativeBase):
    pass

alembic = Alembic(metadatas=Base.metadata)


# --- 1. Organizational Structure ---

class Company(Base):
    """Represents the manufacturing entity (Brand Owner)."""
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gln: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="Global Location Number for the company HQ")
    gcp: Mapped[str] = mapped_column(String(20), nullable=False, comment="GS1 Company Prefix")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    plants: Mapped[List["Plant"]] = relationship(back_populates="company", cascade="all, delete-orphan")
    products: Mapped[List["Product"]] = relationship(back_populates="company")

class Plant(Base):
    """Physical factory locations identified by GLN."""
    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gln: Mapped[str] = mapped_column(String(31), unique=True, nullable=False, comment="GLN for this specific factory location")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    company: Mapped["Company"] = relationship(back_populates="plants")
    devices: Mapped[List["Device"]] = relationship(back_populates="plant")

# --- 2. Security & Access ---

class User(Base, UserMixin):
    """Human operators accessing the dashboard (JWT Auth)."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="operator")  # admin, operator, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    # Flask-Login requires a get_id method that returns a string
    def get_id(self):
        return str(self.id)


class Device(Base):
    """Factory hardware (Line Controllers, Cameras) (API Key Auth)."""
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    device_role: Mapped[str] = mapped_column(String(20), nullable=False)  # line_controller, camera, printer
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    # Store hashed API key for validation. 
    # In 'development', you might store plain text, but production must use hashes.
    api_key_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    
    plant: Mapped["Plant"] = relationship(back_populates="devices")

# --- 3. Product Data ---

class Product(Base):
    """Master data for trade items."""
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    gtin: Mapped[str] = mapped_column(String(31), unique=True, nullable=False, comment="Global Trade Item Number (14 digit)")
    sku: Mapped[str] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    company: Mapped["Company"] = relationship(back_populates="products")
    serial_counters: Mapped[List["SerialCounter"]] = relationship(back_populates="product")

class SerialCounter(Base):
    """Atomic counter for generating sequential parts of SGTINs."""
    __tablename__ = "serial_counters"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    last_serial: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    product: Mapped["Product"] = relationship(back_populates="serial_counters")

# --- 4. Core EPCIS Repository ---

class EPCISEvent(Base):
    """
    The central table for all traceability events.
    Uses JSONB for flexible storage of EPCIS attributes while keeping
    critical query fields as columns for indexing.
    """
    __tablename__ = "epcis_events"

    # We use String for ID to accommodate UUIDs or URNs if strictly required, 
    # but internal UUID is safer for database performance.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Core EPCIS fields needed for fast filtering
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ObjectEvent, AggregationEvent
    action: Mapped[str] = mapped_column(String(20), nullable=False)      # ADD, OBSERVE, DELETE
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    record_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    event_timezone_offset: Mapped[str] = mapped_column(String(6), default="+00:00")
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    # Business Context
    biz_step: Mapped[Optional[str]] = mapped_column(String(100), index=True)   # e.g., urn:epcglobal:cbv:bizstep:commissioning
    disposition: Mapped[Optional[str]] = mapped_column(String(100), index=True) # e.g., urn:epcglobal:cbv:disp:active
    read_point: Mapped[Optional[str]] = mapped_column(String(255))             # e.g., urn:epc:id:sgln:...
    biz_location: Mapped[Optional[str]] = mapped_column(String(255))           # e.g., urn:epc:id:sgln:...
    
    # The Payload
    # Stores epcList, childEPCs, bizTransactionList, sourceList, destinationList, sensorElement
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default={})

    def __repr__(self):
        return f"<EPCISEvent {self.event_type} {self.action} {self.event_time}>"

# --- 5. State Management (Optional but Recommended) ---

class EPCState(Base):
    """
    Lookup table for the *current* state of an individual EPC.
    This prevents needing to replay the entire Event table to find "Where is item X?".
    """
    __tablename__ = "epc_states"

    epc: Mapped[str] = mapped_column(String(255), primary_key=True)
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("products.id"), nullable=True)
    
    current_biz_location: Mapped[Optional[str]] = mapped_column(String(255))
    current_disposition: Mapped[Optional[str]] = mapped_column(String(100))
    last_event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    
    # Hierarchy handling
    parent_epc: Mapped[Optional[str]] = mapped_column(String(255), index=True, comment="Immediate parent (e.g., Case EPC)")
    top_level_epc: Mapped[Optional[str]] = mapped_column(String(255), index=True, comment="Topmost parent (e.g., Pallet EPC)")

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())