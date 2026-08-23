from datetime import datetime, timezone, timedelta
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

class Employee(Base):
    __tablename__='employees_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    name: Mapped[str]=mapped_column(String(120))
    role: Mapped[str]=mapped_column(String(48),index=True)
    qualification: Mapped[str]=mapped_column(String(64),default='')
    home_hub: Mapped[str]=mapped_column(String(16),default='')
    salary_monthly: Mapped[float]=mapped_column(Float,default=0)
    hiring_fee: Mapped[float]=mapped_column(Float,default=0)
    quality: Mapped[int]=mapped_column(Integer,default=70)
    fatigue: Mapped[float]=mapped_column(Float,default=0)
    hired_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class RouteSettings(Base):
    __tablename__='route_settings_v5'
    route_id: Mapped[int]=mapped_column(ForeignKey('routes_v4.id'),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    economy_price: Mapped[float]=mapped_column(Float,default=0)
    premium_price: Mapped[float]=mapped_column(Float,default=0)
    business_price: Mapped[float]=mapped_column(Float,default=0)
    first_price: Mapped[float]=mapped_column(Float,default=0)
    baggage_fee: Mapped[float]=mapped_column(Float,default=0)
    overbooking_percent: Mapped[int]=mapped_column(Integer,default=3)

class AircraftService(Base):
    __tablename__='aircraft_services_v5'
    aircraft_id: Mapped[int]=mapped_column(ForeignKey('aircraft_v4.id'),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    wifi: Mapped[int]=mapped_column(Integer,default=0)
    meals: Mapped[int]=mapped_column(Integer,default=0)
    entertainment: Mapped[int]=mapped_column(Integer,default=0)
    comfort: Mapped[int]=mapped_column(Integer,default=0)
    cabin_service: Mapped[int]=mapped_column(Integer,default=0)
    cleaning: Mapped[int]=mapped_column(Integer,default=0)

class AircraftLiveryDetail(Base):
    __tablename__='aircraft_livery_details_v5'
    aircraft_id: Mapped[int]=mapped_column(ForeignKey('aircraft_v4.id'),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    tail_color: Mapped[str]=mapped_column(String(16),default='#0b4b78')
    engine_color: Mapped[str]=mapped_column(String(16),default='#0b4b78')
    belly_color: Mapped[str]=mapped_column(String(16),default='#dce5ec')
    nose_color: Mapped[str]=mapped_column(String(16),default='#f3f7fb')
    stripe_style: Mapped[str]=mapped_column(String(32),default='swoosh')
    logo_scale: Mapped[float]=mapped_column(Float,default=1.0)
    logo_position: Mapped[float]=mapped_column(Float,default=0.35)

class FlightRecord(Base):
    __tablename__='flight_records_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    route_id: Mapped[int]=mapped_column(ForeignKey('routes_v4.id'),index=True)
    aircraft_id: Mapped[int]=mapped_column(ForeignKey('aircraft_v4.id'),index=True)
    tail: Mapped[str]=mapped_column(String(24))
    origin: Mapped[str]=mapped_column(String(16))
    destination: Mapped[str]=mapped_column(String(16))
    passengers: Mapped[int]=mapped_column(Integer,default=0)
    load_factor: Mapped[float]=mapped_column(Float,default=0)
    ticket_revenue: Mapped[float]=mapped_column(Float,default=0)
    ancillary_revenue: Mapped[float]=mapped_column(Float,default=0)
    operating_cost: Mapped[float]=mapped_column(Float,default=0)
    profit: Mapped[float]=mapped_column(Float,default=0)
    completed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),index=True)

class RouteProgress(Base):
    __tablename__='route_progress_v5'
    route_id: Mapped[int]=mapped_column(ForeignKey('routes_v4.id'),primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    completed_legs: Mapped[int]=mapped_column(Integer,default=0)

class FinanceTransaction(Base):
    __tablename__='finance_transactions_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    category: Mapped[str]=mapped_column(String(64),index=True)
    label: Mapped[str]=mapped_column(String(180))
    amount: Mapped[float]=mapped_column(Float,default=0)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),index=True)

class Loan(Base):
    __tablename__='loans_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    principal: Mapped[float]=mapped_column(Float)
    outstanding: Mapped[float]=mapped_column(Float)
    apr: Mapped[float]=mapped_column(Float)
    term_months: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    last_accrued_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class MarketingCampaign(Base):
    __tablename__='marketing_campaigns_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    name: Mapped[str]=mapped_column(String(120))
    campaign_type: Mapped[str]=mapped_column(String(64))
    spend: Mapped[float]=mapped_column(Float)
    impact: Mapped[float]=mapped_column(Float,default=0.05)
    starts_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    ends_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))

class Partner(Base):
    __tablename__='partners_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    partner_type: Mapped[str]=mapped_column(String(48))
    name: Mapped[str]=mapped_column(String(120))
    sign_fee: Mapped[float]=mapped_column(Float,default=0)
    revenue_bonus: Mapped[float]=mapped_column(Float,default=0)
    reputation_bonus: Mapped[float]=mapped_column(Float,default=0)
    signed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class HotelProperty(Base):
    __tablename__='hotel_properties_v5'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    airport_ident: Mapped[str]=mapped_column(String(16),index=True)
    name: Mapped[str]=mapped_column(String(120))
    rooms: Mapped[int]=mapped_column(Integer,default=120)
    stars: Mapped[int]=mapped_column(Integer,default=3)
    level: Mapped[int]=mapped_column(Integer,default=1)
    built_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class HubAsset(Base):
    __tablename__='hub_assets_v5'
    __table_args__=(UniqueConstraint('user_id','airport_ident','asset_key',name='uq_v5_hub_asset'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    airport_ident: Mapped[str]=mapped_column(String(16),index=True)
    asset_key: Mapped[str]=mapped_column(String(120),index=True)
    kind: Mapped[str]=mapped_column(String(32))
    name: Mapped[str]=mapped_column(String(80),default='')
    lon: Mapped[float]=mapped_column(Float)
    lat: Mapped[float]=mapped_column(Float)
    purchase_price: Mapped[float]=mapped_column(Float,default=0)
    purchased_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class DailyQuestClaim(Base):
    __tablename__='daily_quest_claims_v6'
    __table_args__=(UniqueConstraint('user_id','quest_date','quest_code',name='uq_v6_daily_quest_claim'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    quest_date: Mapped[str]=mapped_column(String(16),index=True)
    quest_code: Mapped[str]=mapped_column(String(64),index=True)
    cash_reward: Mapped[float]=mapped_column(Float,default=0)
    xp_reward: Mapped[int]=mapped_column(Integer,default=0)
    claimed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class BankLoanV6(Base):
    __tablename__='bank_loans_v6'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    bank_id: Mapped[str]=mapped_column(String(64),index=True)
    bank_name: Mapped[str]=mapped_column(String(120))
    principal: Mapped[float]=mapped_column(Float)
    outstanding: Mapped[float]=mapped_column(Float)
    apr: Mapped[float]=mapped_column(Float)
    term_months: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    last_accrued_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))


class SpecialBase(Base):
    __tablename__='special_bases_v8'
    __table_args__=(UniqueConstraint('user_id','airport_ident','branch',name='uq_v8_special_base'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    airport_ident: Mapped[str]=mapped_column(String(16),index=True)
    branch: Mapped[str]=mapped_column(String(48),index=True)
    name: Mapped[str]=mapped_column(String(120),default='')
    level: Mapped[int]=mapped_column(Integer,default=1)
    purchase_price: Mapped[float]=mapped_column(Float,default=0)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class SpecialContract(Base):
    __tablename__='special_contracts_v8'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    base_id: Mapped[int]=mapped_column(ForeignKey('special_bases_v8.id'),index=True)
    contract_code: Mapped[str]=mapped_column(String(80),index=True)
    branch: Mapped[str]=mapped_column(String(48),index=True)
    title: Mapped[str]=mapped_column(String(180))
    country: Mapped[str]=mapped_column(String(80),default='')
    reward: Mapped[float]=mapped_column(Float,default=0)
    status: Mapped[str]=mapped_column(String(24),default='active')
    starts_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    ends_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc)+timedelta(days=14))

# -------- v1.1 functional premium systems --------
class GameWallet(Base):
    __tablename__='game_wallets_v11'
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    tokens: Mapped[int]=mapped_column(Integer,default=500)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class ShopEntitlement(Base):
    __tablename__='shop_entitlements_v11'
    __table_args__=(UniqueConstraint('user_id','item_code',name='uq_v11_shop_entitlement'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    item_code: Mapped[str]=mapped_column(String(80),index=True)
    item_type: Mapped[str]=mapped_column(String(40),default='item')
    acquired_with: Mapped[str]=mapped_column(String(24),default='tokens')
    acquired_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class AirlineAllianceMembership(Base):
    __tablename__='airline_alliance_memberships_v11'
    __table_args__=(UniqueConstraint('user_id',name='uq_v11_airline_alliance_user'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    alliance_code: Mapped[str]=mapped_column(String(40),index=True)
    joined_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class PlayerAlliance(Base):
    __tablename__='player_alliances_v11'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    name: Mapped[str]=mapped_column(String(80),unique=True,index=True)
    tag: Mapped[str]=mapped_column(String(8),unique=True,index=True)
    founder_user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    treasury: Mapped[float]=mapped_column(Float,default=0)
    xp: Mapped[int]=mapped_column(Integer,default=0)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class PlayerAllianceMember(Base):
    __tablename__='player_alliance_members_v11'
    __table_args__=(UniqueConstraint('user_id',name='uq_v11_player_alliance_user'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    alliance_id: Mapped[int]=mapped_column(ForeignKey('player_alliances_v11.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    role: Mapped[str]=mapped_column(String(24),default='member')
    contribution: Mapped[float]=mapped_column(Float,default=0)
    joined_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class AllianceMessage(Base):
    __tablename__='alliance_messages_v11'
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    alliance_id: Mapped[int]=mapped_column(ForeignKey('player_alliances_v11.id'),index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    message: Mapped[str]=mapped_column(String(500))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),index=True)


class HRPolicy(Base):
    __tablename__='hr_policies_v11'
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    enabled: Mapped[bool]=mapped_column(Boolean,default=True)
    monthly_budget: Mapped[float]=mapped_column(Float,default=9_000_000)
    target_buffer_percent: Mapped[int]=mapped_column(Integer,default=15)
    last_autohire_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class IPOState(Base):
    __tablename__='ipo_states_v11'
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),primary_key=True)
    is_public: Mapped[bool]=mapped_column(Boolean,default=False)
    ticker: Mapped[str]=mapped_column(String(12),default='SKY')
    equity_sold_percent: Mapped[float]=mapped_column(Float,default=0)
    cash_raised: Mapped[float]=mapped_column(Float,default=0)
    share_price: Mapped[float]=mapped_column(Float,default=0)
    market_confidence: Mapped[float]=mapped_column(Float,default=65)
    launched_at: Mapped[datetime | None]=mapped_column(DateTime(timezone=True),nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class CompanyResearch(Base):
    __tablename__='company_research_v11'
    __table_args__=(UniqueConstraint('user_id','code',name='uq_v11_company_research'),)
    id: Mapped[int]=mapped_column(Integer,primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    code: Mapped[str]=mapped_column(String(64),index=True)
    level: Mapped[int]=mapped_column(Integer,default=0)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
