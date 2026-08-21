from datetime import datetime, timezone
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, Boolean, UniqueConstraint

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    email: Mapped[str]=mapped_column(String(240),unique=True,index=True)
    username: Mapped[str]=mapped_column(String(80),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    company_name: Mapped[str]=mapped_column(String(120))
    hub_code: Mapped[str]=mapped_column(String(8),default='')
    cash: Mapped[float]=mapped_column(Float,default=180_000_000)
    reputation: Mapped[int]=mapped_column(Integer,default=50)
    last_settled: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class CompanyProfile(Base):
    __tablename__='company_profiles_v4'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),unique=True,index=True)
    primary_color: Mapped[str]=mapped_column(String(16),default='#0b4b78')
    secondary_color: Mapped[str]=mapped_column(String(16),default='#f3f7fb')
    accent_color: Mapped[str]=mapped_column(String(16),default='#42d392')
    logo_text: Mapped[str]=mapped_column(String(24),default='SKYLINE')
    logo_data: Mapped[str]=mapped_column(Text,default='')
    livery_template: Mapped[str]=mapped_column(String(32),default='swoosh')

class UserHub(Base):
    __tablename__='user_hubs_v4'
    __table_args__=(UniqueConstraint('user_id','airport_ident',name='uq_v4_user_hub'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    airport_ident: Mapped[str]=mapped_column(String(16),index=True)
    is_primary: Mapped[bool]=mapped_column(Boolean,default=False)
    purchase_price: Mapped[float]=mapped_column(Float,default=0)
    purchased_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class HubUpgrade(Base):
    __tablename__='hub_upgrades_v4'
    __table_args__=(UniqueConstraint('user_id','airport_ident','code',name='uq_v4_hub_upgrade'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    airport_ident: Mapped[str]=mapped_column(String(16),index=True)
    code: Mapped[str]=mapped_column(String(64),index=True)
    level: Mapped[int]=mapped_column(Integer,default=0)

class Aircraft(Base):
    __tablename__='aircraft_v4'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    type_icao: Mapped[str]=mapped_column(String(16),index=True)
    model_variant: Mapped[str]=mapped_column(String(100),default='')
    tail: Mapped[str]=mapped_column(String(24),index=True)
    acquisition: Mapped[str]=mapped_column(String(16),default='buy')
    condition: Mapped[int]=mapped_column(Integer,default=100)
    home_hub: Mapped[str]=mapped_column(String(16),default='')
    livery_primary: Mapped[str]=mapped_column(String(16),default='#0b4b78')
    livery_secondary: Mapped[str]=mapped_column(String(16),default='#f3f7fb')
    livery_accent: Mapped[str]=mapped_column(String(16),default='#42d392')
    livery_template: Mapped[str]=mapped_column(String(32),default='swoosh')
    livery_name: Mapped[str]=mapped_column(String(80),default='Standard')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class Route(Base):
    __tablename__='routes_v4'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    aircraft_id: Mapped[int]=mapped_column(ForeignKey('aircraft_v4.id'),index=True)
    origin: Mapped[str]=mapped_column(String(16),index=True)
    destination: Mapped[str]=mapped_column(String(16),index=True)
    commercial_destination: Mapped[str]=mapped_column(String(16),default='')
    via: Mapped[str]=mapped_column(String(16),default='')
    partner_airline: Mapped[str]=mapped_column(String(80),default='')
    partner_aircraft: Mapped[str]=mapped_column(String(80),default='')
    frequency: Mapped[int]=mapped_column(Integer,default=1)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
