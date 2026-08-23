import os, math, json, base64, hashlib, hmac, secrets, time, random
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import create_engine, select, delete, func
from sqlalchemy.orm import sessionmaker

from models import (Base, User, CompanyProfile, UserHub, HubUpgrade, Aircraft, Route,
    Employee, RouteSettings, AircraftService, AircraftLiveryDetail, FlightRecord, RouteProgress,
    FinanceTransaction, Loan, MarketingCampaign, Partner, HotelProperty, HubAsset)
from catalog import (
    search_airports, airport_detail, major_airports, search_aircraft, aircraft_detail,
    aircraft_manufacturers, search_airlines, longest_runway_m
)
from logic import (
    UPGRADES, UPGRADE_BY_CODE, SIM_SPEED, upgrade_price, hub_level, destination_point,
    route_simulation, economy_per_leg, economy_detailed, completed_leg_count, haversine_km, now_utc
)

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DATABASE_URL=os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(APP_DIR,'skyline.db')}")
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql://',1)
SECRET_KEY=os.getenv('SECRET_KEY','dev-'+secrets.token_hex(24))
COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1'
connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {}
engine=create_engine(DATABASE_URL,pool_pre_ping=True,connect_args=connect_args)
SessionLocal=sessionmaker(bind=engine,expire_on_commit=False)
Base.metadata.create_all(engine)

app=FastAPI(title='SKYLINE AIRWAYS',version='0.6')
app.mount('/static',StaticFiles(directory=os.path.join(APP_DIR,'static')),name='static')
templates=Jinja2Templates(directory=os.path.join(APP_DIR,'templates'))
signer=URLSafeSerializer(SECRET_KEY,salt='skyline-v4')

# -------- Password/session helpers --------
def pw_hash(password:str)->str:
    salt=secrets.token_bytes(16); rounds=240_000
    dk=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,rounds)
    return f'pbkdf2_sha256${rounds}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}'

def pw_verify(password:str,stored:str)->bool:
    try:
        algo,rounds,salt_b64,dk_b64=stored.split('$',3)
        salt=base64.b64decode(salt_b64); expected=base64.b64decode(dk_b64)
        got=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,int(rounds))
        return hmac.compare_digest(got,expected)
    except Exception:return False

def set_cookie(resp,user_id:int):
    token=signer.dumps({'uid':user_id})
    resp.set_cookie('skyline_session',token,max_age=60*60*24*30,httponly=True,samesite='lax',secure=COOKIE_SECURE)

def current_user(request:Request,db):
    token=request.cookies.get('skyline_session')
    if not token:return None
    try:data=signer.loads(token)
    except BadSignature:return None
    return db.get(User,int(data.get('uid',0)))

def require_user(request:Request,db):
    u=current_user(request,db)
    if not u:raise HTTPException(401,'Non connecté')
    return u

def profile_for(db,u):
    p=db.scalar(select(CompanyProfile).where(CompanyProfile.user_id==u.id))
    if not p:
        p=CompanyProfile(user_id=u.id,logo_text=(u.company_name or 'SKYLINE')[:24].upper())
        db.add(p);db.commit();db.refresh(p)
    return p

def user_hubs(db,u):
    return db.scalars(select(UserHub).where(UserHub.user_id==u.id).order_by(UserHub.is_primary.desc(),UserHub.purchased_at)).all()

def primary_hub(db,u):
    hubs=user_hubs(db,u)
    if not hubs:return None
    return next((h for h in hubs if h.is_primary),hubs[0])

def hub_levels(db,user_id,ident):
    rows=db.scalars(select(HubUpgrade).where(HubUpgrade.user_id==user_id,HubUpgrade.airport_ident==ident)).all()
    return {r.code:r.level for r in rows}

# -------- Migration helpers for users coming from v0.3 --------
def ensure_v4_start_capital(db,u):
    if not user_hubs(db,u) and u.cash < 180_000_000:
        u.cash=180_000_000
        db.commit()

# -------- Route/economy helpers --------
def airport_for_code(code):
    d=airport_detail(code)
    if not d:return None
    return {'ident':d['ident'],'code':d['code'],'name':d['name'],'lat':d['lat'],'lon':d['lon'],'type':d['type'],'country':d['country'],'longest_runway_ft':d['longest_runway_ft']}

def spec_for_aircraft(a):
    return aircraft_detail(a.type_icao)

def route_operational_check(origin_ident,dest_ident,spec):
    o=airport_detail(origin_ident);d=airport_detail(dest_ident)
    if not o or not d:return {'ok':False,'reason':'Aéroport inconnu.'}
    if o['ident']==d['ident']:return {'ok':False,'reason':'Origine et destination identiques.'}
    if not d['purchasable'] and d['type']=='closed':return {'ok':False,'reason':'Aéroport fermé dans le catalogue.'}
    dist=haversine_km(o['lat'],o['lon'],d['lat'],d['lon'])
    if dist > spec['range_km']*0.90:
        return {'ok':False,'reason':f"Autonomie insuffisante : {int(dist)} km pour {spec['range_km']} km de rayon simulé."}
    req=spec['runway_required_m']
    if req>0:
        orwy=int(o['longest_runway_ft']*0.3048); drwy=int(d['longest_runway_ft']*0.3048)
        if orwy and orwy < req:
            return {'ok':False,'reason':f"Piste de départ trop courte ({orwy} m, besoin estimé {req} m)."}
        if drwy and drwy < req:
            return {'ok':False,'reason':f"Piste d’arrivée trop courte ({drwy} m, besoin estimé {req} m)."}
        if not drwy and d['type'] not in ('heliport','seaplane_base'):
            return {'ok':False,'reason':'Aucune piste exploitable connue à destination.'}
    # Operational/geopolitical scenario layer. This is deliberately explicit and replaceable by a licensed live NOTAM feed.
    if d['iata']=='SVO' or d['icao']=='UUEE':
        return {'ok':False,'reason':'Route indisponible dans le scénario géopolitique actuel du jeu.','rule':'geo'}
    if d['iata']=='IKA' or d['icao']=='OIIE':
        ist=airport_detail('IST')
        if ist and o['country'] in ('FR','DE','NL','BE','ES','IT','PT','GB','IE','CH','AT','DK','SE','NO','FI'):
            return {'ok':False,'reason':'Service direct indisponible dans le scénario OPS.','rule':'connection','alternative':{
                'via':ist['ident'],'via_code':ist['code'],'commercial_destination':d['ident'],
                'partner_airline':'Anatolia Connect','partner_aircraft':'Airbus A321',
                'text':f"{o['code']} → {ist['code']} avec ton avion, puis {ist['code']} → {d['code']} avec un partenaire."
            }}
    return {'ok':True,'reason':'Route techniquement et opérationnellement compatible dans le moteur actuel.','distance_km':int(dist)}

def serialize_aircraft(a,route=None):
    spec=spec_for_aircraft(a)
    flight=None
    if route:
        o=airport_for_code(route.origin);d=airport_for_code(route.destination)
        if o and d:flight=route_simulation(route.created_at,o,d,spec)
    return {
        'id':a.id,'tail':a.tail,'type_icao':a.type_icao,'model_variant':a.model_variant,'spec':spec,
        'acquisition':a.acquisition,'condition':a.condition,'home_hub':a.home_hub,
        'livery':{'primary':a.livery_primary,'secondary':a.livery_secondary,'accent':a.livery_accent,'template':a.livery_template,'name':a.livery_name},
        'route_id':route.id if route else None,'flight':flight
    }

def log_tx(db,user_id,category,label,amount):
    db.add(FinanceTransaction(user_id=user_id,category=category,label=label,amount=float(amount)))


def service_for(db,user_id,aircraft_id):
    row=db.get(AircraftService,aircraft_id)
    if not row:
        row=AircraftService(aircraft_id=aircraft_id,user_id=user_id)
        db.add(row);db.flush()
    return row


def settings_for(db,user_id,route,origin=None,destination=None,spec=None):
    row=db.get(RouteSettings,route.id)
    if not row:
        market=0
        if origin and destination and spec:
            market=economy_per_leg(origin,destination,spec,50)['fare']
        row=RouteSettings(route_id=route.id,user_id=user_id,
            economy_price=market or 120,premium_price=(market or 120)*1.55,
            business_price=(market or 120)*2.75,first_price=(market or 120)*4.8,baggage_fee=0,overbooking_percent=3)
        db.add(row);db.flush()
    return row


def livery_detail_for(db,user_id,aircraft):
    row=db.get(AircraftLiveryDetail,aircraft.id)
    if not row:
        row=AircraftLiveryDetail(aircraft_id=aircraft.id,user_id=user_id,tail_color=aircraft.livery_primary,
            engine_color=aircraft.livery_primary,belly_color='#d9e1e8',nose_color=aircraft.livery_secondary,
            stripe_style=aircraft.livery_template,logo_scale=1.0,logo_position=.35)
        db.add(row);db.flush()
    return row


def active_marketing_boost(db,user_id):
    now=now_utc()
    rows=db.scalars(select(MarketingCampaign).where(MarketingCampaign.user_id==user_id,MarketingCampaign.ends_at>now)).all()
    boost=sum(x.impact for x in rows)
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==user_id,Employee.role=='marketing_director')):
        boost*=1.15
    return min(.25,boost)


def partner_revenue_bonus(db,user_id):
    rows=db.scalars(select(Partner).where(Partner.user_id==user_id)).all()
    return min(.08,sum(x.revenue_bonus for x in rows))


def aircraft_qualification(spec):
    code=(spec.get('icao') or '').upper()
    if code.startswith('A2') or code in ('A318','A319','A320','A321','A19N','A20N','A21N'):return 'A320 FAMILY'
    if code.startswith('A33') or code in ('A332','A333','A338','A339'):return 'A330'
    if code.startswith('A35'):return 'A350'
    if code.startswith('B73') or code.startswith('B3'):return 'B737'
    if code.startswith('B78'):return 'B787'
    if code.startswith('B77'):return 'B777'
    if code.startswith('AT'):return 'ATR'
    if code.startswith('E') or code.startswith('CRJ'):return 'REGIONAL JET'
    if spec.get('category')=='helicopter':return 'HELICOPTER'
    return 'MULTI TYPE'


def crew_status_for(db,user_id,spec,distance_km=0):
    qual=aircraft_qualification(spec)
    pilots=db.scalars(select(Employee).where(Employee.user_id==user_id,Employee.role.in_(['pilot','copilot']))).all()
    compatible=[e for e in pilots if e.qualification in (qual,'MULTI TYPE','')]
    cabin=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==user_id,Employee.role=='cabin_crew')) or 0
    pilots_needed=4 if distance_km>5500 else 2
    cabin_needed=max(2,math.ceil(max(1,spec.get('seats',1))/50))
    contracted=max(0,pilots_needed-len(compatible))+max(0,cabin_needed-cabin)
    factor=1+.13*contracted
    return {'qualification':qual,'pilots_available':len(compatible),'pilots_needed':pilots_needed,'cabin_available':cabin,'cabin_needed':cabin_needed,'contracted':contracted,'cost_factor':factor,'ok':contracted==0}


def accrue_loans(db,u):
    now=now_utc()
    for loan in db.scalars(select(Loan).where(Loan.user_id==u.id,Loan.outstanding>0.01)).all():
        last=loan.last_accrued_at or loan.created_at or now
        if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
        sim_years=max(0,(now-last).total_seconds())*SIM_SPEED/(365.25*24*3600)
        if sim_years>0:
            interest=loan.outstanding*loan.apr*sim_years
            loan.outstanding+=interest
            loan.last_accrued_at=now


def settle_economy(db,u):
    accrue_loans(db,u)
    now=now_utc();last=u.last_settled or now
    if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
    elapsed=max(0,min((now-last).total_seconds(),7*24*3600))
    routes=db.scalars(select(Route).where(Route.user_id==u.id)).all()
    aircraft={a.id:a for a in db.scalars(select(Aircraft).where(Aircraft.user_id==u.id)).all()}
    marketing=active_marketing_boost(db,u.id);partner_bonus=partner_revenue_bonus(db,u.id)
    for r in routes:
        a=aircraft.get(r.aircraft_id)
        if not a:continue
        spec=spec_for_aircraft(a);o=airport_for_code(r.origin);d=airport_for_code(r.destination)
        if not o or not d:continue
        completed=completed_leg_count(r.created_at,o,d,spec)
        prog=db.get(RouteProgress,r.id)
        if not prog:
            prog=RouteProgress(route_id=r.id,user_id=u.id,completed_legs=0);db.add(prog);db.flush()
        if completed>prog.completed_legs:
            settings=settings_for(db,u.id,r,o,d,spec);service=service_for(db,u.id,a.id)
            sdict={k:getattr(service,k) for k in ('wifi','meals','entertainment','comfort','cabin_service','cleaning')}
            st=crew_status_for(db,u.id,spec,haversine_km(o['lat'],o['lon'],d['lat'],d['lon']))
            cfg={k:getattr(settings,k) for k in ('economy_price','premium_price','business_price','first_price','baggage_fee','overbooking_percent')}
            upper=min(completed,prog.completed_legs+50)
            for leg_index in range(prog.completed_legs+1,upper+1):
                outbound=(leg_index%2)==1
                fo,fd=(o,d) if outbound else (d,o)
                econ=economy_detailed(fo,fd,spec,u.reputation,cfg,sdict,marketing,partner_bonus,st['cost_factor'])
                profit=econ['profit'];u.cash+=profit
                db.add(FlightRecord(user_id=u.id,route_id=r.id,aircraft_id=a.id,tail=a.tail,origin=fo['code'],destination=fd['code'],
                    passengers=econ['passengers'],load_factor=econ['load_factor'],ticket_revenue=econ['ticket_revenue'],ancillary_revenue=econ['ancillary_revenue'],operating_cost=econ['cost'],profit=profit))
                log_tx(db,u.id,'flight',f'{a.tail} · {fo["code"]} → {fd["code"]}',profit)
            prog.completed_legs=upper
    if elapsed>0:
        monthly=db.scalar(select(func.sum(Employee.salary_monthly)).where(Employee.user_id==u.id)) or 0
        salary_cost=monthly*(elapsed*SIM_SPEED)/(30*24*3600)
        if salary_cost>0:u.cash-=salary_cost
        hotels=db.scalars(select(HotelProperty).where(HotelProperty.user_id==u.id)).all()
        hotel_rev=sum(h.rooms*(45+12*h.stars)*(0.44+0.03*h.level) for h in hotels)*(elapsed*SIM_SPEED)/(24*3600)
        if hotel_rev:u.cash+=hotel_rev
    u.last_settled=now;db.commit()


STAFF_ROLES={
    'pilot':'Commandant / pilote','copilot':'Copilote','cabin_crew':'Personnel de cabine','mechanic':'Technicien maintenance',
    'ground_agent':'Agent opérations sol','hr_manager':'Responsable RH','marketing_director':'Directeur marketing',
    'operations_manager':'Directeur des opérations','finance_director':'Directeur financier'
}
FIRST_NAMES=['Lucas','Emma','Hugo','Léa','Noah','Chloé','Louis','Inès','Arthur','Camille','Sofia','Nicolas','Maya','Antoine','Sarah','Yanis','Elena','Thomas','Jade','Gabriel','Amina','Victor','Eva','Lina']
LAST_NAMES=['Martin','Bernard','Dubois','Thomas','Robert','Richard','Petit','Durand','Leroy','Moreau','Simon','Laurent','Michel','Garcia','David','Bertrand','Roux','Vincent','Fournier','Morel','Nguyen','Walker','Lopez','Khan']
QUALIFICATIONS=['A320 FAMILY','A330','A350','B737','B787','B777','ATR','REGIONAL JET','MULTI TYPE']

def generate_staff_candidates(user_id:int,role:str=''):
    week=int(time.time()//(7*24*3600));rng=random.Random(user_id*100003+week*7919+sum(ord(c) for c in role))
    roles=[role] if role in STAFF_ROLES else list(STAFF_ROLES)
    out=[]
    for i in range(36):
        r=roles[i%len(roles)]
        name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        quality=rng.randint(58,94)
        qual=rng.choice(QUALIFICATIONS) if r in ('pilot','copilot') else ('Cabin' if r=='cabin_crew' else '')
        bases={'pilot':9000,'copilot':6200,'cabin_crew':2800,'mechanic':4200,'ground_agent':3000,'hr_manager':7200,'marketing_director':11000,'operations_manager':12500,'finance_director':12000}
        salary=int(bases[r]*(.82+quality/100*.42))
        fee=int(salary*(1.2+quality/100))
        cid=f'{week}-{r}-{i}-{quality}-{abs(hash((name,qual,week)))%99999}'
        out.append({'id':cid,'name':name,'role':r,'role_label':STAFF_ROLES[r],'qualification':qual,'quality':quality,'salary_monthly':salary,'hiring_fee':fee})
    return out

PARTNER_OFFERS=[
    {'id':'hotel-aurora','type':'hotel','name':'Aurora Hotels','fee':2_500_000,'revenue_bonus':.008,'reputation_bonus':1},
    {'id':'hotel-meridian','type':'hotel','name':'Meridian Grand Hotels','fee':7_000_000,'revenue_bonus':.015,'reputation_bonus':2},
    {'id':'car-nova','type':'car_rental','name':'Nova Rent','fee':1_200_000,'revenue_bonus':.005,'reputation_bonus':0},
    {'id':'card-atlas','type':'credit_card','name':'Atlas Card','fee':4_000_000,'revenue_bonus':.012,'reputation_bonus':1},
    {'id':'tourism-world','type':'tourism','name':'WorldPass Tourism','fee':3_000_000,'revenue_bonus':.009,'reputation_bonus':1},
    {'id':'airline-northstar','type':'airline','name':'NorthStar Airways','fee':8_000_000,'revenue_bonus':.018,'reputation_bonus':2},
]

SERVICE_UPGRADES={
    'wifi':('Wi‑Fi à bord',650_000,10),'meals':('Restauration à bord',480_000,10),'entertainment':('IFE / divertissement',720_000,10),
    'comfort':('Confort cabine',1_100_000,10),'cabin_service':('Formation service cabine',390_000,10),'cleaning':('Standard propreté cabine',260_000,10)
}

# -------- Page routes --------
@app.get('/health')
def health():return {'status':'ok','version':'0.5','catalog':'85k+ airports / 591 aircraft types','sim_speed':SIM_SPEED}

@app.get('/')
def root(request:Request):
    with SessionLocal() as db:
        u=current_user(request,db)
        if not u:return RedirectResponse('/login',303)
        ensure_v4_start_capital(db,u)
        if not user_hubs(db,u):return RedirectResponse('/setup',303)
        return RedirectResponse('/game',303)

@app.get('/login',response_class=HTMLResponse)
def login_page(request:Request):return templates.TemplateResponse(request,'login.html',{'error':None})

@app.post('/login',response_class=HTMLResponse)
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.email==email.strip().lower()))
        if not u or not pw_verify(password,u.password_hash):
            return templates.TemplateResponse(request,'login.html',{'error':'Email ou mot de passe incorrect.'},status_code=400)
        ensure_v4_start_capital(db,u)
        resp=RedirectResponse('/setup' if not user_hubs(db,u) else '/game',303);set_cookie(resp,u.id);return resp

@app.get('/register',response_class=HTMLResponse)
def register_page(request:Request):return templates.TemplateResponse(request,'register.html',{'error':None})

@app.post('/register',response_class=HTMLResponse)
def register(request:Request,email:str=Form(...),username:str=Form(...),company_name:str=Form(...),password:str=Form(...)):
    email=email.strip().lower();username=username.strip();company_name=company_name.strip()
    if len(password)<8:return templates.TemplateResponse(request,'register.html',{'error':'Mot de passe : 8 caractères minimum.'},status_code=400)
    with SessionLocal() as db:
        if db.scalar(select(User).where((User.email==email)|(User.username==username))):
            return templates.TemplateResponse(request,'register.html',{'error':'Email ou pseudo déjà utilisé.'},status_code=400)
        u=User(email=email,username=username,password_hash=pw_hash(password),company_name=company_name or 'Skyline Airways',hub_code='',cash=180_000_000)
        db.add(u);db.commit();db.refresh(u);profile_for(db,u)
        resp=RedirectResponse('/setup',303);set_cookie(resp,u.id);return resp

@app.get('/logout')
def logout():
    resp=RedirectResponse('/login',303);resp.delete_cookie('skyline_session');return resp

@app.get('/setup',response_class=HTMLResponse)
def setup(request:Request):
    with SessionLocal() as db:
        u=current_user(request,db)
        if not u:return RedirectResponse('/login',303)
        ensure_v4_start_capital(db,u)
        if user_hubs(db,u):return RedirectResponse('/game',303)
    return templates.TemplateResponse(request,'setup.html',{})

@app.get('/game',response_class=HTMLResponse)
def game(request:Request):
    with SessionLocal() as db:
        u=current_user(request,db)
        if not u:return RedirectResponse('/login',303)
        ensure_v4_start_capital(db,u)
        if not user_hubs(db,u):return RedirectResponse('/setup',303)
    return templates.TemplateResponse(request,'game.html',{})

# -------- API request models --------
class HubBuyReq(BaseModel):ident:str
class PrimaryHubReq(BaseModel):ident:str
class UpgradeReq(BaseModel):ident:str;code:str
class AircraftBuyReq(BaseModel):type_icao:str;acquisition:str='buy';home_hub:str;model_variant:str=''
class RouteReq(BaseModel):aircraft_id:int;origin:str;destination:str;frequency:int=1;accept_alternative:bool=False
class LiveryReq(BaseModel):primary:str;secondary:str;accent:str;template:str='swoosh';name:str='Standard'
class ProfileReq(BaseModel):primary_color:str;secondary_color:str;accent_color:str;logo_text:str;logo_data:str='';livery_template:str='swoosh'
class RoutePricingReq(BaseModel):economy_price:float;premium_price:float;business_price:float;first_price:float;baggage_fee:float=0;overbooking_percent:int=3
class ServiceUpgradeReq(BaseModel):code:str
class LiveryDetailReq(BaseModel):primary:str;secondary:str;accent:str;tail_color:str='';engine_color:str='';belly_color:str='#d9e1e8';nose_color:str='';stripe_style:str='swoosh';name:str='Standard';logo_scale:float=1.0;logo_position:float=.35
class StaffHireReq(BaseModel):candidate_id:str;home_hub:str=''
class LoanReq(BaseModel):amount:float;term_months:int
class LoanRepayReq(BaseModel):loan_id:int;amount:float
class CampaignReq(BaseModel):campaign_type:str;spend:float;duration_days:int=14
class PartnerReq(BaseModel):offer_id:str
class HotelReq(BaseModel):airport_ident:str;name:str='SKYLINE Hotel';stars:int=3;rooms:int=120
class HotelUpgradeReq(BaseModel):hotel_id:int
class HubAssetBuyReq(BaseModel):ident:str;asset_key:str;kind:str;name:str='';lon:float;lat:float

# -------- Catalog APIs --------
@app.get('/api/airports/search')
def api_airport_search(q:str='',limit:int=30):return search_airports(q,limit=limit)

@app.get('/api/airports/major')
def api_airports_major(limit:int=900):return major_airports(min(limit,1200))

@app.get('/api/airports/{ident}')
def api_airport_detail(ident:str):
    d=airport_detail(ident)
    if not d:raise HTTPException(404,'Aéroport introuvable')
    return d

@app.get('/api/aircraft/catalog')
def api_aircraft_catalog(q:str='',manufacturer:str='',commercial_only:bool=True,limit:int=60,offset:int=0):
    return {'items':search_aircraft(q,manufacturer,commercial_only,limit=limit,offset=offset),'manufacturers':aircraft_manufacturers()}

@app.get('/api/aircraft/catalog/{code}')
def api_aircraft_detail(code:str):
    d=aircraft_detail(code)
    if not d:raise HTTPException(404,'Type avion inconnu')
    return d

@app.get('/api/airlines/search')
def api_airlines(q:str='',limit:int=40):return search_airlines(q,limit)

# -------- Hub APIs --------
@app.get('/api/hubs')
def api_hubs(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);hubs=user_hubs(db,u)
        out=[]
        for h in hubs:
            a=airport_detail(h.airport_ident)
            if a:out.append({'id':h.id,'ident':h.airport_ident,'is_primary':h.is_primary,'purchase_price':h.purchase_price,'airport':a})
        return out

@app.post('/api/hubs/buy')
def api_buy_hub(req:HubBuyReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=airport_detail(req.ident)
        if not a:raise HTTPException(404,'Aéroport introuvable')
        if not a['purchasable']:raise HTTPException(400,'Cet aéroport n’est pas exploitable comme hub.')
        existing=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==a['ident']))
        if existing:raise HTTPException(400,'Hub déjà possédé')
        price=a['price']
        first=len(user_hubs(db,u))==0
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        if first:
            for h in user_hubs(db,u):h.is_primary=False
        h=UserHub(user_id=u.id,airport_ident=a['ident'],is_primary=first,purchase_price=price)
        u.cash-=price;log_tx(db,u.id,'hub',f'Achat hub {a["code"]}',-price);u.hub_code=a['code']
        db.add(h);db.commit();return {'ok':True,'ident':a['ident'],'price':price}

@app.post('/api/hubs/primary')
def api_primary_hub(req:PrimaryHubReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.ident))
        if not h:raise HTTPException(404,'Hub non possédé')
        for x in user_hubs(db,u):x.is_primary=(x.id==h.id)
        a=airport_detail(h.airport_ident);u.hub_code=a['code'] if a else h.airport_ident
        db.commit();return {'ok':True}

@app.get('/api/hub/{ident}')
def api_hub_state(ident:str,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==ident))
        if not h:raise HTTPException(403,'Hub non possédé')
        a=airport_detail(ident);levels=hub_levels(db,u.id,ident);lvl=hub_level(levels)
        nodes=[]
        for n in UPGRADES:
            current=levels.get(n['code'],0);pre=n.get('prereq');available=(not pre or levels.get(pre,0)>0)
            lat,lon=destination_point(a['lat'],a['lon'],n['bearing'],n['dist'])
            nodes.append({**n,'lat':lat,'lon':lon,'level':current,'available':available,'price':upgrade_price(n,current),'state':'active' if current>0 else ('available' if available else 'locked')})
        own=[]
        routes=db.scalars(select(Route).where(Route.user_id==u.id)).all();acs={x.id:x for x in db.scalars(select(Aircraft).where(Aircraft.user_id==u.id)).all()}
        for r in routes:
            ac=acs.get(r.aircraft_id)
            if not ac:continue
            s=serialize_aircraft(ac,r)
            f=s['flight']
            if f and ((f['direction']=='origin_ground' and r.origin==ident) or (f['direction']=='dest_ground' and r.destination==ident)):
                own.append({'aircraft_id':ac.id,'tail':ac.tail,'type':s['spec']['name'],'phase':f['phase'],'status':f['status'],'livery':s['livery']})
        density={'large_airport':28,'medium_airport':18,'small_airport':9,'heliport':7}.get(a['type'],6)
        density += min(18,levels.get('GATES_CONTACT',0)+levels.get('GATES_REMOTE',0))
        assets=db.scalars(select(HubAsset).where(HubAsset.user_id==u.id,HubAsset.airport_ident==ident)).all()
        return {'airport':a,'hub':{'level':lvl,'is_primary':h.is_primary},'nodes':nodes,'own_ground_aircraft':own,'traffic_density':density,
                'assets':[{'asset_key':x.asset_key,'kind':x.kind,'name':x.name,'lon':x.lon,'lat':x.lat,'purchase_price':x.purchase_price} for x in assets]}

@app.post('/api/hub/upgrade')
def api_hub_upgrade(req:UpgradeReq,request:Request):
    node=UPGRADE_BY_CODE.get(req.code)
    if not node:raise HTTPException(404,'Amélioration inconnue')
    with SessionLocal() as db:
        u=require_user(request,db);h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.ident))
        if not h:raise HTTPException(403,'Hub non possédé')
        levels=hub_levels(db,u.id,req.ident);cur=levels.get(req.code,0)
        if cur>=node['max']:raise HTTPException(400,'Niveau maximum atteint')
        pre=node.get('prereq')
        if pre and levels.get(pre,0)<=0:raise HTTPException(400,f'Prérequis : {UPGRADE_BY_CODE[pre]["name"]}')
        price=upgrade_price(node,cur)
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        row=db.scalar(select(HubUpgrade).where(HubUpgrade.user_id==u.id,HubUpgrade.airport_ident==req.ident,HubUpgrade.code==req.code))
        if not row:row=HubUpgrade(user_id=u.id,airport_ident=req.ident,code=req.code,level=0);db.add(row)
        row.level+=1;u.cash-=price;log_tx(db,u.id,'hub_upgrade',f'{airport_detail(req.ident)["code"]} · {node["name"]} niv. {row.level}',-price)
        if node['cat'] in ('Premium','Terminal','Sécurité'):u.reputation=min(100,u.reputation+1)
        db.commit();return {'ok':True,'level':row.level,'price':price}

# -------- Company identity --------
@app.post('/api/profile')
def api_profile(req:ProfileReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);p=profile_for(db,u)
        p.primary_color=req.primary_color[:16];p.secondary_color=req.secondary_color[:16];p.accent_color=req.accent_color[:16]
        p.logo_text=req.logo_text[:24];p.logo_data=(req.logo_data or '')[:900_000];p.livery_template=req.livery_template[:32]
        db.commit();return {'ok':True}

# -------- Aircraft --------
@app.post('/api/aircraft/buy')
def api_buy_aircraft(req:AircraftBuyReq,request:Request):
    spec=aircraft_detail(req.type_icao)
    if not spec:raise HTTPException(404,'Type avion inconnu')
    if req.acquisition not in ('buy','lease'):raise HTTPException(400,'Mode d’acquisition invalide')
    with SessionLocal() as db:
        u=require_user(request,db);hub=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.home_hub))
        if not hub:raise HTTPException(400,'Base non possédée')
        price=spec['price'] if req.acquisition=='buy' else spec['lease']
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        p=profile_for(db,u);count=db.scalar(select(func.count()).select_from(Aircraft).where(Aircraft.user_id==u.id)) or 0
        prefix='N' if airport_detail(req.home_hub).get('country')=='US' else 'F-SK'
        tail=f'{prefix}{count+1:03d}'
        a=Aircraft(user_id=u.id,type_icao=spec['icao'],model_variant=req.model_variant[:100],tail=tail,acquisition=req.acquisition,home_hub=req.home_hub,
                   livery_primary=p.primary_color,livery_secondary=p.secondary_color,livery_accent=p.accent_color,livery_template=p.livery_template)
        u.cash-=price;db.add(a);db.flush();log_tx(db,u.id,'aircraft',f'{req.acquisition.upper()} {tail} · {spec["name"]}',-price);db.commit();return {'ok':True,'tail':tail,'id':a.id}

@app.post('/api/aircraft/{aircraft_id}/livery')
def api_aircraft_livery(aircraft_id:int,req:LiveryDetailReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        a.livery_primary=req.primary[:16];a.livery_secondary=req.secondary[:16];a.livery_accent=req.accent[:16];a.livery_template=req.stripe_style[:32];a.livery_name=req.name[:80]
        d=livery_detail_for(db,u.id,a)
        d.tail_color=(req.tail_color or req.primary)[:16];d.engine_color=(req.engine_color or req.primary)[:16];d.belly_color=req.belly_color[:16];d.nose_color=(req.nose_color or req.secondary)[:16]
        d.stripe_style=req.stripe_style[:32];d.logo_scale=max(.5,min(2.0,req.logo_scale));d.logo_position=max(.15,min(.75,req.logo_position))
        db.commit();return {'ok':True}

# -------- V0.5 staff, product, commercial & finance --------
@app.get('/api/staff/candidates')
def api_staff_candidates(request:Request,role:str=''):
    with SessionLocal() as db:
        u=require_user(request,db)
        return {'roles':STAFF_ROLES,'items':generate_staff_candidates(u.id,role)}

@app.get('/api/staff')
def api_staff(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db)
        rows=db.scalars(select(Employee).where(Employee.user_id==u.id).order_by(Employee.role,Employee.name)).all()
        counts={}
        for e in rows:counts[e.role]=counts.get(e.role,0)+1
        return {'items':[{'id':e.id,'name':e.name,'role':e.role,'role_label':STAFF_ROLES.get(e.role,e.role),'qualification':e.qualification,'home_hub':e.home_hub,'salary_monthly':e.salary_monthly,'quality':e.quality,'fatigue':round(e.fatigue,1)} for e in rows],'counts':counts}

@app.post('/api/staff/hire')
def api_staff_hire(req:StaffHireReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db)
        candidates=generate_staff_candidates(u.id,'')
        c=next((x for x in candidates if x['id']==req.candidate_id),None)
        if not c:raise HTTPException(404,'Candidat expiré ou introuvable')
        hub=req.home_hub or (primary_hub(db,u).airport_ident if primary_hub(db,u) else '')
        if hub and not db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==hub)):raise HTTPException(400,'Hub non possédé')
        hr=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id,Employee.role=='hr_manager')) or 0
        fee=c['hiring_fee']*(.88 if hr else 1.0)
        if u.cash<fee:raise HTTPException(400,'Fonds insuffisants')
        e=Employee(user_id=u.id,name=c['name'],role=c['role'],qualification=c['qualification'],home_hub=hub,salary_monthly=c['salary_monthly'],hiring_fee=fee,quality=c['quality'])
        u.cash-=fee;db.add(e);log_tx(db,u.id,'staff',f'Recrutement {c["name"]} · {c["role_label"]}',-fee);db.commit();return {'ok':True,'id':e.id}

@app.delete('/api/staff/{employee_id}')
def api_staff_fire(employee_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);e=db.get(Employee,employee_id)
        if not e or e.user_id!=u.id:raise HTTPException(404,'Employé introuvable')
        db.delete(e);db.commit();return {'ok':True}

@app.get('/api/aircraft/{aircraft_id}/service')
def api_aircraft_service_get(aircraft_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        x=service_for(db,u.id,a.id);db.commit()
        return {'aircraft_id':a.id,'tail':a.tail,'upgrades':{k:{'label':v[0],'level':getattr(x,k),'max':v[2],'price':int(v[1]*(1.42**getattr(x,k)))} for k,v in SERVICE_UPGRADES.items()}}

@app.post('/api/aircraft/{aircraft_id}/service/upgrade')
def api_aircraft_service_upgrade(aircraft_id:int,req:ServiceUpgradeReq,request:Request):
    if req.code not in SERVICE_UPGRADES:raise HTTPException(404,'Amélioration inconnue')
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        x=service_for(db,u.id,a.id);label,base,maxlvl=SERVICE_UPGRADES[req.code];lvl=getattr(x,req.code)
        if lvl>=maxlvl:raise HTTPException(400,'Niveau maximum atteint')
        price=int(base*(1.42**lvl))
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        setattr(x,req.code,lvl+1);u.cash-=price;log_tx(db,u.id,'cabin_product',f'{a.tail} · {label} niv. {lvl+1}',-price);db.commit();return {'ok':True,'level':lvl+1,'price':price}

@app.get('/api/routes/{route_id}/pricing')
def api_route_pricing_get(route_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);r=db.get(Route,route_id)
        if not r or r.user_id!=u.id:raise HTTPException(404,'Ligne introuvable')
        a=db.get(Aircraft,r.aircraft_id);o=airport_for_code(r.origin);d=airport_for_code(r.destination);spec=spec_for_aircraft(a)
        st=settings_for(db,u.id,r,o,d,spec);svc=service_for(db,u.id,a.id);db.commit()
        cfg={k:getattr(st,k) for k in ('economy_price','premium_price','business_price','first_price','baggage_fee','overbooking_percent')}
        sdict={k:getattr(svc,k) for k in ('wifi','meals','entertainment','comfort','cabin_service','cleaning')}
        crew=crew_status_for(db,u.id,spec,haversine_km(o['lat'],o['lon'],d['lat'],d['lon']))
        estimate=economy_detailed(o,d,spec,u.reputation,cfg,sdict,active_marketing_boost(db,u.id),partner_revenue_bonus(db,u.id),crew['cost_factor'])
        return {'settings':cfg,'estimate':estimate,'crew':crew}

@app.post('/api/routes/{route_id}/pricing')
def api_route_pricing_set(route_id:int,req:RoutePricingReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);r=db.get(Route,route_id)
        if not r or r.user_id!=u.id:raise HTTPException(404,'Ligne introuvable')
        s=settings_for(db,u.id,r)
        s.economy_price=max(15,min(5000,req.economy_price));s.premium_price=max(s.economy_price,min(9000,req.premium_price));s.business_price=max(s.premium_price,min(15000,req.business_price));s.first_price=max(s.business_price,min(30000,req.first_price));s.baggage_fee=max(0,min(300,req.baggage_fee));s.overbooking_percent=max(0,min(15,req.overbooking_percent));db.commit();return {'ok':True}

@app.get('/api/finance')
def api_finance(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);settle_economy(db,u);db.refresh(u)
        flights=db.scalars(select(FlightRecord).where(FlightRecord.user_id==u.id).order_by(FlightRecord.id.desc()).limit(80)).all()
        tx=db.scalars(select(FinanceTransaction).where(FinanceTransaction.user_id==u.id).order_by(FinanceTransaction.id.desc()).limit(80)).all()
        loans=db.scalars(select(Loan).where(Loan.user_id==u.id).order_by(Loan.id.desc())).all()
        monthly=db.scalar(select(func.sum(Employee.salary_monthly)).where(Employee.user_id==u.id)) or 0
        return {'cash':u.cash,'monthly_payroll':monthly,'flights':[{'id':f.id,'tail':f.tail,'origin':f.origin,'destination':f.destination,'passengers':f.passengers,'load_factor':f.load_factor,'ticket_revenue':f.ticket_revenue,'ancillary_revenue':f.ancillary_revenue,'operating_cost':f.operating_cost,'profit':f.profit,'completed_at':f.completed_at.isoformat()} for f in flights],
                'transactions':[{'id':x.id,'category':x.category,'label':x.label,'amount':x.amount,'created_at':x.created_at.isoformat()} for x in tx],
                'loans':[{'id':l.id,'principal':l.principal,'outstanding':l.outstanding,'apr':l.apr,'term_months':l.term_months} for l in loans]}

@app.post('/api/finance/loan')
def api_take_loan(req:LoanReq,request:Request):
    amount=max(1_000_000,min(750_000_000,req.amount));term=req.term_months
    if term not in (12,24,36,48,60):raise HTTPException(400,'Durée invalide')
    apr=.052 + (amount/750_000_000)*.025 + (12/term)*.012
    with SessionLocal() as db:
        u=require_user(request,db);existing=db.scalar(select(func.sum(Loan.outstanding)).where(Loan.user_id==u.id)) or 0
        if existing>u.cash*3+250_000_000:raise HTTPException(400,'Endettement maximum atteint')
        l=Loan(user_id=u.id,principal=amount,outstanding=amount,apr=apr,term_months=term);u.cash+=amount;db.add(l);log_tx(db,u.id,'bank',f'Emprunt bancaire {term} mois',amount);db.commit();return {'ok':True,'apr':apr,'amount':amount}

@app.post('/api/finance/loan/repay')
def api_repay_loan(req:LoanRepayReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);l=db.get(Loan,req.loan_id)
        if not l or l.user_id!=u.id:raise HTTPException(404,'Emprunt introuvable')
        amount=max(1,min(req.amount,l.outstanding,u.cash))
        if amount<=0:raise HTTPException(400,'Montant invalide')
        l.outstanding-=amount;u.cash-=amount;log_tx(db,u.id,'bank','Remboursement emprunt',-amount);db.commit();return {'ok':True,'remaining':l.outstanding}

@app.get('/api/marketing')
def api_marketing(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);now=now_utc();rows=db.scalars(select(MarketingCampaign).where(MarketingCampaign.user_id==u.id).order_by(MarketingCampaign.id.desc())).all()
        has_dir=bool(db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id,Employee.role=='marketing_director')))
        return {'has_director':has_dir,'boost':active_marketing_boost(db,u.id),'campaigns':[{'id':x.id,'name':x.name,'type':x.campaign_type,'spend':x.spend,'impact':x.impact,'active':((x.ends_at.replace(tzinfo=timezone.utc) if x.ends_at.tzinfo is None else x.ends_at)>now),'ends_at':x.ends_at.isoformat()} for x in rows]}

@app.post('/api/marketing')
def api_marketing_start(req:CampaignReq,request:Request):
    types={'brand':('Notoriété mondiale',.035),'digital':('Acquisition digitale',.045),'route':('Lancement de ligne',.055),'premium':('Campagne Premium',.04),'loyalty':('Programme fidélité',.05)}
    if req.campaign_type not in types:raise HTTPException(400,'Campagne inconnue')
    spend=max(100_000,min(25_000_000,req.spend));days=max(3,min(60,req.duration_days));name,base=types[req.campaign_type]
    with SessionLocal() as db:
        u=require_user(request,db)
        if u.cash<spend:raise HTTPException(400,'Fonds insuffisants')
        impact=min(.12,base*math.sqrt(spend/1_000_000));c=MarketingCampaign(user_id=u.id,name=name,campaign_type=req.campaign_type,spend=spend,impact=impact,ends_at=now_utc()+timedelta(days=days));u.cash-=spend;db.add(c);log_tx(db,u.id,'marketing',name,-spend);db.commit();return {'ok':True,'impact':impact}

@app.get('/api/partners')
def api_partners(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);rows=db.scalars(select(Partner).where(Partner.user_id==u.id)).all();owned={x.name for x in rows}
        return {'offers':[{**x,'owned':x['name'] in owned} for x in PARTNER_OFFERS],'owned':[{'id':x.id,'type':x.partner_type,'name':x.name,'revenue_bonus':x.revenue_bonus,'reputation_bonus':x.reputation_bonus} for x in rows]}

@app.post('/api/partners')
def api_partner_sign(req:PartnerReq,request:Request):
    offer=next((x for x in PARTNER_OFFERS if x['id']==req.offer_id),None)
    if not offer:raise HTTPException(404,'Offre inconnue')
    with SessionLocal() as db:
        u=require_user(request,db)
        if db.scalar(select(Partner).where(Partner.user_id==u.id,Partner.name==offer['name'])):raise HTTPException(400,'Partenaire déjà signé')
        if u.cash<offer['fee']:raise HTTPException(400,'Fonds insuffisants')
        p=Partner(user_id=u.id,partner_type=offer['type'],name=offer['name'],sign_fee=offer['fee'],revenue_bonus=offer['revenue_bonus'],reputation_bonus=offer['reputation_bonus']);u.cash-=offer['fee'];u.reputation=min(100,u.reputation+offer['reputation_bonus']);db.add(p);log_tx(db,u.id,'partner',f'Partenariat {offer["name"]}',-offer['fee']);db.commit();return {'ok':True}

@app.get('/api/hotels')
def api_hotels(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);rows=db.scalars(select(HotelProperty).where(HotelProperty.user_id==u.id).order_by(HotelProperty.id)).all()
        return {'items':[{'id':h.id,'airport_ident':h.airport_ident,'name':h.name,'rooms':h.rooms,'stars':h.stars,'level':h.level} for h in rows]}

@app.post('/api/hotels')
def api_build_hotel(req:HotelReq,request:Request):
    stars=max(2,min(5,req.stars));rooms=max(60,min(900,req.rooms));cost=12_000_000+rooms*55_000+stars*3_000_000
    with SessionLocal() as db:
        u=require_user(request,db)
        if not db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.airport_ident)):raise HTTPException(400,'Hub non possédé')
        if u.cash<cost:raise HTTPException(400,'Fonds insuffisants')
        h=HotelProperty(user_id=u.id,airport_ident=req.airport_ident,name=req.name[:120],rooms=rooms,stars=stars,level=1);u.cash-=cost;db.add(h);log_tx(db,u.id,'hotel',f'Construction {h.name}',-cost);db.commit();return {'ok':True,'cost':cost}

@app.post('/api/hotels/upgrade')
def api_upgrade_hotel(req:HotelUpgradeReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);h=db.get(HotelProperty,req.hotel_id)
        if not h or h.user_id!=u.id:raise HTTPException(404,'Hôtel introuvable')
        if h.level>=10:raise HTTPException(400,'Niveau maximum atteint')
        cost=int((4_000_000+h.rooms*8_000)*(1.4**(h.level-1)))
        if u.cash<cost:raise HTTPException(400,'Fonds insuffisants')
        h.level+=1;h.rooms+=40;u.cash-=cost;log_tx(db,u.id,'hotel',f'{h.name} niv. {h.level}',-cost);db.commit();return {'ok':True,'cost':cost,'level':h.level}

@app.post('/api/hub/asset/buy')
def api_hub_asset_buy(req:HubAssetBuyReq,request:Request):
    if req.kind not in ('gate','parking_position','runway'):raise HTTPException(400,'Type d’infrastructure invalide')
    with SessionLocal() as db:
        u=require_user(request,db);hub=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.ident))
        if not hub:raise HTTPException(403,'Hub non possédé')
        a=airport_detail(req.ident);dist=haversine_km(a['lat'],a['lon'],req.lat,req.lon)
        if dist>12:raise HTTPException(400,'Infrastructure trop éloignée de l’aéroport')
        if db.scalar(select(HubAsset).where(HubAsset.user_id==u.id,HubAsset.airport_ident==req.ident,HubAsset.asset_key==req.asset_key)):raise HTTPException(400,'Infrastructure déjà acquise')
        price={'gate':3_200_000,'parking_position':1_750_000,'runway':18_000_000}[req.kind]
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        x=HubAsset(user_id=u.id,airport_ident=req.ident,asset_key=req.asset_key[:120],kind=req.kind,name=req.name[:80],lon=req.lon,lat=req.lat,purchase_price=price);u.cash-=price;db.add(x);log_tx(db,u.id,'hub_asset',f'{a["code"]} · {req.kind} {req.name}',-price);db.commit();return {'ok':True,'price':price}

# -------- Routes --------
@app.get('/api/route-check')
def api_route_check(origin:str,destination:str,aircraft_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        return route_operational_check(origin,destination,spec_for_aircraft(a))

@app.post('/api/routes')
def api_create_route(req:RouteReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,req.aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        if db.scalar(select(Route).where(Route.aircraft_id==a.id)):raise HTTPException(400,'Cet avion est déjà affecté à une rotation')
        hub=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.origin))
        if not hub:raise HTTPException(400,'L’origine doit être un de tes hubs')
        check=route_operational_check(req.origin,req.destination,spec_for_aircraft(a))
        dest=req.destination;commercial='';via='';partner_airline='';partner_aircraft=''
        if not check['ok']:
            alt=check.get('alternative')
            if not alt or not req.accept_alternative:return JSONResponse({'ok':False,'check':check},status_code=409)
            dest=alt['via'];commercial=alt['commercial_destination'];via=alt['via'];partner_airline=alt['partner_airline'];partner_aircraft=alt['partner_aircraft']
            # The user's aircraft must also be able to fly the operated first segment.
            first=route_operational_check(req.origin,dest,spec_for_aircraft(a))
            if not first['ok']:return JSONResponse({'ok':False,'check':first},status_code=409)
        r=Route(user_id=u.id,aircraft_id=a.id,origin=req.origin,destination=dest,commercial_destination=commercial,via=via,partner_airline=partner_airline,partner_aircraft=partner_aircraft,frequency=max(1,min(7,req.frequency)))
        db.add(r);db.commit();return {'ok':True,'route_id':r.id,'alternative':bool(commercial)}

@app.delete('/api/routes/{route_id}')
def api_delete_route(route_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);r=db.get(Route,route_id)
        if not r or r.user_id!=u.id:raise HTTPException(404,'Ligne inconnue')
        db.delete(r);db.commit();return {'ok':True}

# -------- Live world state --------
@app.get('/api/state')
def api_state(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);settle_economy(db,u);db.refresh(u);p=profile_for(db,u)
        hubs=user_hubs(db,u);hub_out=[]
        for h in hubs:
            a=airport_detail(h.airport_ident)
            if a:
                levels=hub_levels(db,u.id,h.airport_ident)
                assets=db.scalar(select(func.count()).select_from(HubAsset).where(HubAsset.user_id==u.id,HubAsset.airport_ident==h.airport_ident)) or 0
                hub_out.append({'ident':h.airport_ident,'is_primary':h.is_primary,'level':hub_level(levels),'asset_count':assets,'airport':{'ident':a['ident'],'code':a['code'],'name':a['name'],'lat':a['lat'],'lon':a['lon'],'type':a['type'],'country':a['country'],'municipality':a['municipality']}})
        acs=db.scalars(select(Aircraft).where(Aircraft.user_id==u.id).order_by(Aircraft.id)).all()
        routes=db.scalars(select(Route).where(Route.user_id==u.id).order_by(Route.id)).all();route_by_ac={r.aircraft_id:r for r in routes}
        aircraft=[]
        for a in acs:
            item=serialize_aircraft(a,route_by_ac.get(a.id));svc=service_for(db,u.id,a.id);liv=livery_detail_for(db,u.id,a)
            item['service']={k:getattr(svc,k) for k in ('wifi','meals','entertainment','comfort','cabin_service','cleaning')}
            item['livery_detail']={'tail_color':liv.tail_color,'engine_color':liv.engine_color,'belly_color':liv.belly_color,'nose_color':liv.nose_color,'stripe_style':liv.stripe_style,'logo_scale':liv.logo_scale,'logo_position':liv.logo_position}
            aircraft.append(item)
        marketing=active_marketing_boost(db,u.id);pbonus=partner_revenue_bonus(db,u.id)
        route_out=[]
        for r in routes:
            a=next((x for x in acs if x.id==r.aircraft_id),None)
            if not a:continue
            s=serialize_aircraft(a,r);o=airport_for_code(r.origin);d=airport_for_code(r.destination)
            settings=settings_for(db,u.id,r,o,d,s['spec']);svc=service_for(db,u.id,a.id)
            cfg={k:getattr(settings,k) for k in ('economy_price','premium_price','business_price','first_price','baggage_fee','overbooking_percent')}
            sdict={k:getattr(svc,k) for k in ('wifi','meals','entertainment','comfort','cabin_service','cleaning')}
            crew=crew_status_for(db,u.id,s['spec'],haversine_km(o['lat'],o['lon'],d['lat'],d['lon'])) if o and d else {}
            econ=economy_detailed(o,d,s['spec'],u.reputation,cfg,sdict,marketing,pbonus,crew.get('cost_factor',1.0)) if o and d else None
            partner=None
            if r.commercial_destination:
                cd=airport_detail(r.commercial_destination)
                if cd:partner={'from':d['code'],'to':cd['code'],'from_lat':d['lat'],'from_lon':d['lon'],'to_lat':cd['lat'],'to_lon':cd['lon'],'airline':r.partner_airline,'aircraft':r.partner_aircraft}
            route_out.append({'id':r.id,'aircraft_id':a.id,'tail':a.tail,'model':s['spec']['name'],'origin':r.origin,'destination':r.destination,'commercial_destination':r.commercial_destination,'via':r.via,'frequency':r.frequency,'flight':s['flight'],'economy':econ,'pricing':cfg,'crew':crew,'partner':partner,
                              'origin_airport':o,'destination_airport':d})
        employees=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id)) or 0
        active_campaigns=db.scalar(select(func.count()).select_from(MarketingCampaign).where(MarketingCampaign.user_id==u.id,MarketingCampaign.ends_at>now_utc())) or 0
        db.commit()
        return {'user':{'username':u.username,'company_name':u.company_name,'cash':round(u.cash,2),'reputation':u.reputation},
                'profile':{'primary_color':p.primary_color,'secondary_color':p.secondary_color,'accent_color':p.accent_color,'logo_text':p.logo_text,'logo_data':p.logo_data,'livery_template':p.livery_template},
                'hubs':hub_out,'aircraft':aircraft,'routes':route_out,'sim_speed':SIM_SPEED,
                'company':{'employees':employees,'marketing_boost':marketing,'active_campaigns':active_campaigns,'partner_bonus':pbonus}}

# -------- Weather / live traffic --------
class BoundedCache(OrderedDict):
    """Small LRU cache to keep the Render free instance inside its RAM budget."""
    def __init__(self, maxsize):
        super().__init__(); self.maxsize=max(1,int(maxsize))
    def get(self,key,default=None):
        if key not in self:return default
        value=super().get(key)
        self.move_to_end(key)
        return value
    def __setitem__(self,key,value):
        if key in self:super().__delitem__(key)
        super().__setitem__(key,value)
        while len(self)>self.maxsize:self.popitem(last=False)

_weather_cache=BoundedCache(96)
_traffic_cache=BoundedCache(32)

@app.get('/api/weather/current')
def api_weather(lat:float,lon:float):
    key=(round(lat,1),round(lon,1));now=time.time();cached=_weather_cache.get(key)
    if cached and now-cached[0]<90:return cached[1]
    url='https://api.open-meteo.com/v1/forecast'
    params={'latitude':lat,'longitude':lon,'current':'temperature_2m,precipitation,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m,wind_gusts_10m','wind_speed_unit':'kn','timezone':'UTC'}
    try:
        with httpx.Client(timeout=5.5) as client:r=client.get(url,params=params);r.raise_for_status();data=r.json()
        out={'ok':True,'current':data.get('current',{}),'source':'Open-Meteo'}
    except Exception:
        out={'ok':False,'current':{},'source':'unavailable'}
    _weather_cache[key]=(now,out);return out

@app.get('/api/live-traffic')
def api_live_traffic(ident:str):
    a=airport_detail(ident)
    if not a:raise HTTPException(404,'Aéroport introuvable')
    key=a['ident'];now=time.time();cached=_traffic_cache.get(key)
    if cached and now-cached[0]<18:return cached[1]
    span=.45 if a['type']=='large_airport' else .32
    params={'lamin':a['lat']-span,'lomin':a['lon']-span,'lamax':a['lat']+span,'lomax':a['lon']+span}
    out={'source':'simulated','states':[]}
    try:
        with httpx.Client(timeout=6.0,headers={'User-Agent':'SKYLINE-Airways-Prototype/0.4'}) as client:
            r=client.get('https://opensky-network.org/api/states/all',params=params)
            if r.status_code==200:
                raw=r.json().get('states') or []
                states=[]
                for s in raw[:140]:
                    if len(s)<11 or s[5] is None or s[6] is None:continue
                    states.append({'icao24':s[0],'callsign':(s[1] or '').strip(),'country':s[2],'lon':s[5],'lat':s[6],'baro_altitude':s[7],'on_ground':bool(s[8]),'velocity':s[9],'heading':s[10]})
                out={'source':'OpenSky','states':states}
    except Exception:pass
    _traffic_cache[key]=(now,out);return out


@app.get('/api/live-traffic/box')
def api_live_traffic_box(lamin:float,lomin:float,lamax:float,lomax:float,limit:int=300):
    # Prefer the official Flightradar24 API when the owner supplies a licensed API token.
    # Otherwise use OpenSky in the same display layer. No FR24 website scraping or map copying is performed.
    lamin=max(-85,min(85,lamin));lamax=max(-85,min(85,lamax));lomin=max(-180,min(180,lomin));lomax=max(-180,min(180,lomax));limit=max(20,min(180,limit))
    bucket=(round(lamin,1),round(lomin,1),round(lamax,1),round(lomax,1),limit);now=time.time();cached=_traffic_cache.get(('box',)+bucket)
    if cached and now-cached[0]<20:return cached[1]
    token=os.getenv('FR24_API_TOKEN','').strip()
    if token:
        try:
            bounds=f'{lamax},{lamin},{lomin},{lomax}'
            headers={'Authorization':f'Bearer {token}','Accept-Version':'v1','Accept':'application/json','User-Agent':'SKYLINE-Airways/0.5'}
            with httpx.Client(timeout=7.5,headers=headers) as client:
                r=client.get('https://fr24api.flightradar24.com/api/live/flight-positions/full',params={'bounds':bounds,'limit':limit});r.raise_for_status();raw=r.json().get('data') or []
            states=[{'id':x.get('fr24_id'),'callsign':x.get('callsign') or x.get('flight') or '', 'flight':x.get('flight') or '', 'country':'', 'lon':x.get('lon'),'lat':x.get('lat'),'altitude_ft':x.get('alt'),'velocity_kts':x.get('gspeed'),'heading':x.get('track'),'type':x.get('type') or '', 'reg':x.get('reg') or '', 'origin':x.get('orig_iata') or x.get('orig_icao') or '', 'destination':x.get('dest_iata') or x.get('dest_icao') or '', 'airline':x.get('painted_as') or x.get('operating_as') or '', 'on_ground':(x.get('alt') or 0)<200} for x in raw if x.get('lat') is not None and x.get('lon') is not None]
            out={'source':'Flightradar24 API','states':states,'licensed':True};_traffic_cache[('box',)+bucket]=(now,out);return out
        except Exception:
            pass
    try:
        params={'lamin':lamin,'lomin':lomin,'lamax':lamax,'lomax':lomax}
        with httpx.Client(timeout=7.0,headers={'User-Agent':'SKYLINE-Airways/0.5'}) as client:
            r=client.get('https://opensky-network.org/api/states/all',params=params);r.raise_for_status();raw=r.json().get('states') or []
        states=[]
        for x in raw[:limit]:
            if len(x)<11 or x[5] is None or x[6] is None:continue
            states.append({'id':x[0],'callsign':(x[1] or '').strip(),'flight':(x[1] or '').strip(),'country':x[2] or '', 'lon':x[5],'lat':x[6],'altitude_ft':int((x[7] or 0)*3.28084),'velocity_kts':round((x[9] or 0)*1.94384,1),'heading':x[10] or 0,'type':'','reg':'','origin':'','destination':'','airline':'','on_ground':bool(x[8])})
        out={'source':'OpenSky','states':states,'licensed':False}
    except Exception:
        out={'source':'unavailable','states':[],'licensed':False}
    _traffic_cache[('box',)+bucket]=(now,out);return out

_surface_cache=BoundedCache(2)

def _fallback_surface_network(a):
    features=[]
    for r in a.get('runways',[]):
        if r.get('le_lon') is None or r.get('he_lon') is None:
            continue
        features.append({
            'type':'Feature',
            'geometry':{'type':'LineString','coordinates':[[r['le_lon'],r['le_lat']],[r['he_lon'],r['he_lat']]]},
            'properties':{'kind':'runway','name':(r.get('le_ident') or '')+' / '+(r.get('he_ident') or ''),'source':'OurAirports','asset_key':'runway:'+str(r.get('id') or (r.get('le_ident') or '')+'-'+(r.get('he_ident') or ''))}
        })
    return {'type':'FeatureCollection','features':features,'source':'OurAirports fallback'}

@app.get('/api/hub/{ident}/surface-network')
def api_surface_network(ident:str,request:Request):
    """Aeroway geometry from OSM/Overpass when available, with runway fallback."""
    with SessionLocal() as db:
        u=require_user(request,db)
        h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==ident))
        if not h:raise HTTPException(403,'Hub non possédé')
    a=airport_detail(ident)
    if not a:raise HTTPException(404,'Aéroport introuvable')
    now=time.time();cached=_surface_cache.get(a['ident'])
    if cached and now-cached[0] < 6*3600:return cached[1]
    span={'large_airport':.050,'medium_airport':.040,'small_airport':.026,'heliport':.018}.get(a['type'],.03)
    south,west,north,east=a['lat']-span,a['lon']-span,a['lat']+span,a['lon']+span
    q=(
        '[out:json][timeout:8];('
        f'way["aeroway"="taxiway"]({south},{west},{north},{east});'
        f'way["aeroway"="runway"]({south},{west},{north},{east});'
        f'way["aeroway"="apron"]({south},{west},{north},{east});'
        f'node["aeroway"="gate"]({south},{west},{north},{east});'
        f'node["aeroway"="parking_position"]({south},{west},{north},{east});'
        ');out body;>;out skel qt;'
    )
    out=None
    try:
        with httpx.Client(timeout=10,headers={'User-Agent':'SKYLINE-Airways-Realism/0.4'}) as client:
            r=client.post('https://overpass-api.de/api/interpreter',data={'data':q})
            r.raise_for_status();raw=r.json()
        nodes={e['id']:(e.get('lon'),e.get('lat')) for e in raw.get('elements',[]) if e.get('type')=='node' and e.get('lon') is not None and e.get('lat') is not None}
        features=[]
        for e in raw.get('elements',[]):
            if e.get('type')=='way':
                tags=e.get('tags') or {};kind=tags.get('aeroway')
                coords=[nodes.get(nid) for nid in e.get('nodes',[])]
                coords=[list(c) for c in coords if c and c[0] is not None]
                if len(coords)<2:continue
                if kind=='apron' and len(coords)>=3:
                    ring=coords + ([coords[0]] if coords[-1]!=coords[0] else [])
                    geom={'type':'Polygon','coordinates':[ring]}
                else:
                    geom={'type':'LineString','coordinates':coords}
                features.append({'type':'Feature','geometry':geom,'properties':{'kind':kind or 'aeroway','name':tags.get('ref') or tags.get('name') or '', 'surface':tags.get('surface') or '', 'source':'OpenStreetMap','asset_key':f'{kind or "aeroway"}:{e.get("id")}' }})
            elif e.get('type')=='node':
                tags=e.get('tags') or {};kind=tags.get('aeroway')
                if kind in ('gate','parking_position') and e.get('lon') is not None:
                    features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[e['lon'],e['lat']]},'properties':{'kind':kind,'name':tags.get('ref') or tags.get('name') or '', 'source':'OpenStreetMap','asset_key':f'{kind}:{e.get("id")}' }})
        # Large airports can contain tens of thousands of OSM objects. Keep only
        # the operational geometry needed by the game to avoid OOM on 512 MB instances.
        if features:
            priority={'runway':0,'taxiway':1,'gate':2,'parking_position':3,'apron':4}
            features.sort(key=lambda f: priority.get((f.get('properties') or {}).get('kind'),9))
            features=features[:1400]
            out={'type':'FeatureCollection','features':features,'source':'OpenStreetMap / Overpass'}
    except Exception:
        out=None
    if not out:out=_fallback_surface_network(a)
    _surface_cache[a['ident']]=(now,out)
    return out

@app.post('/api/reset-career')
def api_reset(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db)
        route_ids=[x for (x,) in db.execute(select(Route.id).where(Route.user_id==u.id)).all()]
        aircraft_ids=[x for (x,) in db.execute(select(Aircraft.id).where(Aircraft.user_id==u.id)).all()]
        if route_ids:
            db.execute(delete(FlightRecord).where(FlightRecord.route_id.in_(route_ids)));db.execute(delete(RouteProgress).where(RouteProgress.route_id.in_(route_ids)));db.execute(delete(RouteSettings).where(RouteSettings.route_id.in_(route_ids)))
        if aircraft_ids:
            db.execute(delete(AircraftService).where(AircraftService.aircraft_id.in_(aircraft_ids)));db.execute(delete(AircraftLiveryDetail).where(AircraftLiveryDetail.aircraft_id.in_(aircraft_ids)))
        db.execute(delete(Route).where(Route.user_id==u.id));db.execute(delete(Aircraft).where(Aircraft.user_id==u.id));db.execute(delete(HubAsset).where(HubAsset.user_id==u.id));db.execute(delete(HubUpgrade).where(HubUpgrade.user_id==u.id));db.execute(delete(HotelProperty).where(HotelProperty.user_id==u.id));db.execute(delete(Partner).where(Partner.user_id==u.id));db.execute(delete(MarketingCampaign).where(MarketingCampaign.user_id==u.id));db.execute(delete(Employee).where(Employee.user_id==u.id));db.execute(delete(Loan).where(Loan.user_id==u.id));db.execute(delete(FinanceTransaction).where(FinanceTransaction.user_id==u.id));db.execute(delete(UserHub).where(UserHub.user_id==u.id))
        u.cash=180_000_000;u.reputation=50;u.hub_code='';u.last_settled=now_utc();db.commit();return {'ok':True}
