# app/crm/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, BigInteger
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class Lead(Base):
    __tablename__ = "crm_leads"
    
    id = Column(Integer, primary_key=True)
    manager_id = Column(BigInteger, nullable=False, index=True)
    source = Column(String(20), nullable=False)
    source_url = Column(Text, nullable=False)
    status = Column(String(30), default="new")
    priority = Column(Integer, default=3)
    
    # Car info
    car_brand = Column(String(50), nullable=False)
    car_model = Column(String(50), nullable=False)
    car_year = Column(Integer)
    car_price = Column(Integer)
    car_price_currency = Column(String(3), default="USD")
    car_mileage = Column(Integer)
    car_location = Column(String(100))
    car_vin = Column(String(20))
    car_photos = Column(JSON, default=list)
    car_description = Column(Text)
    
    # Owner info
    owner_name = Column(String(100))
    owner_phone = Column(String(20))
    owner_phone_hidden = Column(Boolean, default=False)
    
    # Stats
    call_attempts = Column(Integer, default=0)
    last_call_at = Column(DateTime)
    success_calls = Column(Integer, default=0)
    
    # Meta
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived = Column(Boolean, default=False)
    
    # Relations
    calls = relationship("CallLog", back_populates="lead", order_by="desc(CallLog.created_at)")
    reminders = relationship("Reminder", back_populates="lead", order_by="Reminder.remind_at")

class CallLog(Base):
    __tablename__ = "crm_call_logs"
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("crm_leads.id"), nullable=False)
    manager_id = Column(BigInteger, nullable=False)
    result = Column(String(30), nullable=False)
    notes = Column(Text)
    next_action_type = Column(String(30))
    next_action_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="calls")

class Reminder(Base):
    __tablename__ = "crm_reminders"
    
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("crm_leads.id"), nullable=False)
    manager_id = Column(BigInteger, nullable=False, index=True)
    remind_at = Column(DateTime, nullable=False, index=True)
    reminder_type = Column(String(30), nullable=False)
    message = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    lead = relationship("Lead", back_populates="reminders")

async def init_crm_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
