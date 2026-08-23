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
    FinanceTransaction, Loan, MarketingCampaign, Partner, HotelProperty, HubAsset, DailyQuestClaim, BankLoanV6, SpecialBase, SpecialContract,
    GameWallet, ShopEntitlement, AirlineAllianceMembership, PlayerAlliance, PlayerAllianceMember, AllianceMessage, CompanyResearch, HRPolicy, IPOState)
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

app=FastAPI(title='SKYLINE AIRWAYS',version='1.1.0')

@app.middleware('http')
async def skyline_no_stale_code(request:Request, call_next):
    response=await call_next(request)
    path=request.url.path
    if path=='/game' or path.endswith('.js') or path.endswith('.css') or path.endswith('.html'):
        response.headers['Cache-Control']='no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma']='no-cache'
        response.headers['Expires']='0'
    return response

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


def crew_status_for(db,user_id,spec,distance_km=0,home_hub=''):
    """Automatic crew-pool model.

    The player recruits a pool; OPS performs the assignment. A normal sector needs two
    pilots on the flight, while very long sectors use a reinforced four-pilot cockpit.
    For fatigue resilience the recommended pool is two complete cockpit/cabin crews.
    """
    qual=aircraft_qualification(spec)
    q=select(Employee).where(Employee.user_id==user_id,Employee.role.in_(['pilot','copilot']))
    pilots=db.scalars(q).all()
    compatible=[e for e in pilots if e.qualification in (qual,'MULTI TYPE','') and (not home_hub or not e.home_hub or e.home_hub==home_hub)]
    cq=select(func.count()).select_from(Employee).where(Employee.user_id==user_id,Employee.role=='cabin_crew')
    if home_hub:cq=cq.where((Employee.home_hub==home_hub)|(Employee.home_hub==''))
    cabin=db.scalar(cq) or 0
    long_duty=distance_km>5500
    pilots_needed=4 if long_duty else 2
    cabin_needed=max(2,math.ceil(max(1,spec.get('seats',1))/50))
    pilots_recommended=pilots_needed*2
    cabin_recommended=cabin_needed*2
    contracted=max(0,pilots_needed-len(compatible))+max(0,cabin_needed-cabin)
    factor=1+.13*contracted
    pilot_coverage=min(1.5,len(compatible)/max(1,pilots_recommended))
    cabin_coverage=min(1.5,cabin/max(1,cabin_recommended))
    coverage=round(min(pilot_coverage,cabin_coverage)*100)
    risk='Excellent' if coverage>=100 else 'Correct' if coverage>=75 else 'Fragile' if coverage>=50 else 'Critique'
    return {'qualification':qual,'pilots_available':len(compatible),'pilots_needed':pilots_needed,'pilots_recommended':pilots_recommended,
            'cabin_available':cabin,'cabin_needed':cabin_needed,'cabin_recommended':cabin_recommended,'contracted':contracted,
            'cost_factor':factor,'ok':contracted==0,'coverage_percent':coverage,'fatigue_risk':risk,'reinforced':long_duty,'auto_assignment':True}


RESEARCH_PROJECTS={
    'fuel_efficiency':{'name':'Efficacité carburant','desc':'Optimisation des profils de vol et procédures de consommation.','base_cost':2_500_000,'max':5,'min_level':8,'effect':'-2% coût carburant / niveau'},
    'propeller_efficiency':{'name':'Optimisation hélices & turbopropulseurs','desc':'Hélices, régulation et rendement propulsif des ATR / turbopropulseurs.','base_cost':1_800_000,'max':5,'min_level':10,'effect':'-3% carburant turboprop / niveau'},
    'maintenance':{'name':'Maintenance prédictive','desc':'Planification, stocks et fiabilité technique.','base_cost':2_200_000,'max':5,'min_level':12,'effect':'Réduction des coûts techniques (progression)'},
    'service':{'name':'Expérience passager','desc':'Processus cabine, service et personnalisation.','base_cost':1_600_000,'max':5,'min_level':10,'effect':'Bonus de produit et de satisfaction'},
    'digital_ops':{'name':'Opérations digitales & IA','desc':'Automatisation OPS, recovery et allocation des ressources.','base_cost':3_000_000,'max':5,'min_level':18,'effect':'Efficacité opérationnelle accrue'},
    'sustainable':{'name':'Carburants & durabilité','desc':'SAF, énergie sol et réduction d’empreinte.','base_cost':2_800_000,'max':5,'min_level':20,'effect':'Coûts énergie et prestige'},
}

def research_levels(db,user_id):
    return {x.code:x.level for x in db.scalars(select(CompanyResearch).where(CompanyResearch.user_id==user_id)).all()}

def research_cost_factor(db,user_id,spec):
    lv=research_levels(db,user_id);factor=1.0-(lv.get('fuel_efficiency',0)*.02)
    desc=(spec or {}).get('description','')
    if 'T' in str(desc) or 'turboprop' in str((spec or {}).get('category','')).lower():factor-=lv.get('propeller_efficiency',0)*.03
    return max(.72,factor)

def accrue_loans(db,u):
    now=now_utc()
    rows=list(db.scalars(select(Loan).where(Loan.user_id==u.id,Loan.outstanding>0.01)).all())
    rows+=list(db.scalars(select(BankLoanV6).where(BankLoanV6.user_id==u.id,BankLoanV6.outstanding>0.01)).all())
    for loan in rows:
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
            st=crew_status_for(db,u.id,spec,haversine_km(o['lat'],o['lon'],d['lat'],d['lon']),r.origin)
            cfg={k:getattr(settings,k) for k in ('economy_price','premium_price','business_price','first_price','baggage_fee','overbooking_percent')}
            upper=min(completed,prog.completed_legs+50)
            for leg_index in range(prog.completed_legs+1,upper+1):
                outbound=(leg_index%2)==1
                fo,fd=(o,d) if outbound else (d,o)
                econ=economy_detailed(fo,fd,spec,u.reputation,cfg,sdict,marketing,partner_bonus,st['cost_factor'],research_cost_factor(db,u.id,spec))
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
    u.last_settled=now
    # HR automation is conservative: at most a small batch every six hours and always within the player's monthly budget.
    if 'auto_balance_hr' in globals():
        try:auto_balance_hr(db,u,force=False,max_hires=12)
        except Exception:pass
    db.commit()


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



def hr_policy_for(db,user_id):
    row=db.get(HRPolicy,user_id)
    if not row:
        row=HRPolicy(user_id=user_id,enabled=True,monthly_budget=9_000_000,target_buffer_percent=15)
        db.add(row);db.flush()
    return row


def hr_targets(db,user_id):
    """Recommended staffing by hub. The player manages capacity; OPS assigns individuals."""
    hubs=db.scalars(select(UserHub).where(UserHub.user_id==user_id)).all()
    aircraft=db.scalars(select(Aircraft).where(Aircraft.user_id==user_id)).all()
    routes={r.aircraft_id:r for r in db.scalars(select(Route).where(Route.user_id==user_id)).all()}
    employees=db.scalars(select(Employee).where(Employee.user_id==user_id)).all()
    out=[]
    for h in hubs:
        acs=[a for a in aircraft if (a.home_hub or h.airport_ident)==h.airport_ident]
        pilot_target=cabin_target=0
        quals={}
        for a in acs:
            spec=spec_for_aircraft(a);r=routes.get(a.id);dist=0
            if r:
                o=airport_for_code(r.origin);d=airport_for_code(r.destination)
                if o and d:dist=haversine_km(o['lat'],o['lon'],d['lat'],d['lon'])
            pilots=8 if dist>5500 else 4
            cabin=max(2,math.ceil(max(1,spec.get('seats',1))/50))*2
            pilot_target+=pilots;cabin_target+=cabin
            q=aircraft_qualification(spec);quals[q]=quals.get(q,0)+pilots
        pilot_current=sum(1 for e in employees if e.role in ('pilot','copilot') and (not e.home_hub or e.home_hub==h.airport_ident))
        cabin_current=sum(1 for e in employees if e.role=='cabin_crew' and (not e.home_hub or e.home_hub==h.airport_ident))
        mech_target=max(1,math.ceil(len(acs)/4)) if acs else 0
        ground_target=max(2,len(acs)*2) if acs else 0
        mech_current=sum(1 for e in employees if e.role=='mechanic' and (not e.home_hub or e.home_hub==h.airport_ident))
        ground_current=sum(1 for e in employees if e.role=='ground_agent' and (not e.home_hub or e.home_hub==h.airport_ident))
        total_target=pilot_target+cabin_target+mech_target+ground_target
        total_current=pilot_current+cabin_current+mech_current+ground_current
        coverage=100 if total_target==0 else round(min(1.5,total_current/max(1,total_target))*100)
        out.append({'ident':h.airport_ident,'code':(airport_detail(h.airport_ident) or {}).get('code',h.airport_ident),
                    'aircraft':len(acs),'pilots':{'current':pilot_current,'target':pilot_target,'qualifications':quals},
                    'cabin':{'current':cabin_current,'target':cabin_target},'mechanics':{'current':mech_current,'target':mech_target},
                    'ground':{'current':ground_current,'target':ground_target},'current':total_current,'target':total_target,
                    'coverage_percent':coverage,'status':'Optimal' if coverage>=100 else 'Sous-effectif' if coverage>=70 else 'Critique'})
    return out


def _auto_employee(db,user_id,role,hub,qualification='',idx=0):
    rng=random.Random(user_id*6101+int(time.time()//86400)*71+idx*997+sum(ord(c) for c in role+hub+qualification))
    name=f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
    quality=rng.randint(68,88)
    base={'pilot':9000,'copilot':6200,'cabin_crew':2800,'mechanic':4200,'ground_agent':3000}.get(role,3500)
    salary=int(base*(.92+quality/100*.28));fee=int(salary*(1.25+quality/130))
    e=Employee(user_id=user_id,name=name,role=role,qualification=qualification,home_hub=hub,salary_monthly=salary,hiring_fee=fee,quality=quality)
    db.add(e);return e,fee


def auto_balance_hr(db,u,force=False,max_hires=28):
    policy=hr_policy_for(db,u.id)
    now=now_utc()
    if not policy.enabled:return {'enabled':False,'hired':0,'reason':'Auto-embauche désactivée'}
    if not force and policy.last_autohire_at and (now-policy.last_autohire_at).total_seconds()<6*3600:
        return {'enabled':True,'hired':0,'reason':'Prochain équilibrage automatique dans quelques heures'}
    payroll=db.scalar(select(func.sum(Employee.salary_monthly)).where(Employee.user_id==u.id)) or 0
    hired=[];spent=0
    for row in hr_targets(db,u.id):
        if len(hired)>=max_hires:break
        hub=row['ident']
        # Pilots: preserve qualification pools, alternating captain/copilot roles.
        for qual,target in row['pilots']['qualifications'].items():
            current=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id,Employee.role.in_(['pilot','copilot']),Employee.home_hub==hub,Employee.qualification==qual)) or 0
            for i in range(max(0,target-current)):
                if len(hired)>=max_hires:break
                role='pilot' if i%2==0 else 'copilot';e,fee=_auto_employee(db,u.id,role,hub,qual,len(hired))
                if payroll+e.salary_monthly>policy.monthly_budget or u.cash<fee:
                    db.expunge(e);break
                payroll+=e.salary_monthly;u.cash-=fee;spent+=fee;hired.append(e)
        needs=[('cabin_crew',max(0,row['cabin']['target']-row['cabin']['current']),''),('mechanic',max(0,row['mechanics']['target']-row['mechanics']['current']),''),('ground_agent',max(0,row['ground']['target']-row['ground']['current']),'')]
        for role,count,qual in needs:
            for _ in range(count):
                if len(hired)>=max_hires:break
                e,fee=_auto_employee(db,u.id,role,hub,qual,len(hired))
                if payroll+e.salary_monthly>policy.monthly_budget or u.cash<fee:
                    db.expunge(e);break
                payroll+=e.salary_monthly;u.cash-=fee;spent+=fee;hired.append(e)
    policy.last_autohire_at=now;policy.updated_at=now
    if spent:log_tx(db,u.id,'staff_auto',f'Auto-embauche OPS · {len(hired)} recrutement(s)',-spent)
    db.flush()
    return {'enabled':True,'hired':len(hired),'spent':round(spent,2),'payroll':round(payroll,2),'monthly_budget':policy.monthly_budget}

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


# -------- v0.6 Premium Realism: progression, satisfaction and geographic partners --------
# Brand names below are used as a private-game catalogue. No logo assets are embedded.
BANKS_BY_COUNTRY={
    'FR':[
        {'id':'bnp-fr','name':'BNP Paribas','base_apr':.044,'max_amount':450_000_000,'min_level':1,'advantage':'Conditions équilibrées et réseau international.'},
        {'id':'ca-fr','name':'Crédit Agricole','base_apr':.042,'max_amount':350_000_000,'min_level':1,'advantage':'Taux compétitif pour une croissance prudente.'},
        {'id':'sg-fr','name':'Société Générale','base_apr':.046,'max_amount':600_000_000,'min_level':8,'advantage':'Capacité élevée pour flotte et infrastructures.'},
        {'id':'ce-fr','name':"Caisse d’Épargne",'base_apr':.041,'max_amount':220_000_000,'min_level':1,'advantage':'Financement progressif des hubs régionaux.'},
        {'id':'hsbc-fr','name':'HSBC Continental Europe','base_apr':.045,'max_amount':750_000_000,'min_level':14,'advantage':'Très adaptée à l’expansion internationale.'},
    ],
    'GB':[
        {'id':'hsbc-gb','name':'HSBC UK','base_apr':.044,'max_amount':800_000_000,'min_level':8,'advantage':'Financement international et multi-devises.'},
        {'id':'barclays-gb','name':'Barclays','base_apr':.045,'max_amount':650_000_000,'min_level':5,'advantage':'Bonne capacité de financement corporate.'},
        {'id':'lloyds-gb','name':'Lloyds Bank','base_apr':.041,'max_amount':300_000_000,'min_level':1,'advantage':'Conditions stables pour opérateurs établis au Royaume-Uni.'},
    ],
    'US':[
        {'id':'jpm-us','name':'JPMorgan Chase','base_apr':.046,'max_amount':1_000_000_000,'min_level':18,'advantage':'Très grande capacité pour groupes mondiaux.'},
        {'id':'bofa-us','name':'Bank of America','base_apr':.045,'max_amount':750_000_000,'min_level':10,'advantage':'Financement flotte et développement réseau.'},
        {'id':'citi-us','name':'Citi','base_apr':.047,'max_amount':900_000_000,'min_level':15,'advantage':'Réseau mondial et opérations internationales.'},
    ],
    'AE':[
        {'id':'enbd-ae','name':'Emirates NBD','base_apr':.043,'max_amount':800_000_000,'min_level':10,'advantage':'Très forte exposition au Golfe et à l’aviation premium.'},
        {'id':'fab-ae','name':'First Abu Dhabi Bank','base_apr':.042,'max_amount':900_000_000,'min_level':14,'advantage':'Capacité élevée pour grands projets.'},
    ],
    'JP':[
        {'id':'mufg-jp','name':'MUFG Bank','base_apr':.038,'max_amount':850_000_000,'min_level':12,'advantage':'Coût du capital attractif et financement long terme.'},
        {'id':'smbc-jp','name':'SMBC','base_apr':.039,'max_amount':800_000_000,'min_level':12,'advantage':'Très bon financement d’actifs aéronautiques.'},
    ],
    'SG':[
        {'id':'dbs-sg','name':'DBS Bank','base_apr':.041,'max_amount':700_000_000,'min_level':10,'advantage':'Solide pour l’expansion Asie-Pacifique.'},
        {'id':'ocbc-sg','name':'OCBC','base_apr':.042,'max_amount':550_000_000,'min_level':8,'advantage':'Financement régional flexible.'},
    ],
    'DE':[
        {'id':'db-de','name':'Deutsche Bank','base_apr':.044,'max_amount':750_000_000,'min_level':10,'advantage':'Corporate et marchés internationaux.'},
        {'id':'cb-de','name':'Commerzbank','base_apr':.042,'max_amount':450_000_000,'min_level':5,'advantage':'Bonne offre pour entreprises européennes.'},
    ],
    'ES':[
        {'id':'san-es','name':'Santander','base_apr':.043,'max_amount':650_000_000,'min_level':6,'advantage':'Réseau très fort en Europe et Amérique latine.'},
        {'id':'bbva-es','name':'BBVA','base_apr':.042,'max_amount':600_000_000,'min_level':6,'advantage':'Bonne implantation internationale.'},
        {'id':'caixa-es','name':'CaixaBank','base_apr':.041,'max_amount':350_000_000,'min_level':2,'advantage':'Conditions intéressantes pour hubs espagnols.'},
    ],
    'MX':[
        {'id':'bbva-mx','name':'BBVA México','base_apr':.049,'max_amount':500_000_000,'min_level':5,'advantage':'Couverture nationale importante.'},
        {'id':'banorte-mx','name':'Banorte','base_apr':.048,'max_amount':400_000_000,'min_level':4,'advantage':'Partenaire local solide.'},
        {'id':'hsbc-mx','name':'HSBC México','base_apr':.050,'max_amount':600_000_000,'min_level':10,'advantage':'Expansion internationale facilitée.'},
    ],
}
DEFAULT_BANKS=[
    {'id':'hsbc-int','name':'HSBC','base_apr':.048,'max_amount':600_000_000,'min_level':8,'advantage':'Réseau international.'},
    {'id':'citi-int','name':'Citi','base_apr':.049,'max_amount':650_000_000,'min_level':12,'advantage':'Financement multi-marchés.'},
]

HUB_REALITY_PROFILES={
    'LFPG':{'character':'Grand hub intercontinental','access':['RER B','TGV','RoissyBus / bus','Taxi & VTC','Location de voitures'],
            'hotel_brands':['Sheraton','Novotel','ibis','Pullman','citizenM'],'signature':'Correspondances internationales, premium, cargo et forte densité opérationnelle.'},
    'LFMN':{'character':'Hub premium Méditerranée','access':['Tram L2 / L3','Bus','Taxi & VTC','Location de voitures'],
            'hotel_brands':['Sheraton','Novotel Suites','ibis Styles','OKKO Hotels'],'signature':'Tourisme, clientèle premium, aviation d’affaires et forte saisonnalité estivale.'},
    'LFBL':{'character':'Aéroport régional','access':['Bus / navette','Taxi','Location de voitures','Accès routier'],
            'hotel_brands':['ibis','Campanile','Kyriad'],'signature':'Réseau régional, coûts maîtrisés et développement progressif.'},
    'KJFK':{'character':'Grand hub intercontinental','access':['AirTrain JFK','LIRR via Jamaica','Métro A / E via connexion','Taxi & VTC'],
            'hotel_brands':['TWA Hotel','Marriott','Hilton','Hampton by Hilton'],'signature':'Très forte demande internationale et marché premium/business.'},
    'OMDB':{'character':'Mega-hub international','access':['Dubai Metro','Taxi','Careem / VTC','Bus','Location de voitures'],
            'hotel_brands':['Premier Inn','Le Méridien','Aloft','Millennium'],'signature':'Correspondances globales, luxe, long-courrier et très forte activité 24/7.'},
}


def bank_catalog_for_country(country):
    return BANKS_BY_COUNTRY.get((country or '').upper(),DEFAULT_BANKS)


def hub_reality_profile(airport):
    if not airport:return {'character':'Aéroport','access':['Taxi','Bus / navette','Location de voitures'],'hotel_brands':['Accor','Marriott','Hilton'],'signature':'Développement adapté au trafic local.'}
    if airport.get('ident') in HUB_REALITY_PROFILES:return HUB_REALITY_PROFILES[airport['ident']]
    typ=airport.get('type')
    if typ=='large_airport':return {'character':'Hub international','access':['Rail / métro si disponible','Bus','Taxi & VTC','Location de voitures'],'hotel_brands':['Accor','Marriott','Hilton','IHG'],'signature':'Fort potentiel de correspondance, premium et long-courrier.'}
    if typ=='medium_airport':return {'character':'Aéroport régional majeur','access':['Bus / navette','Taxi & VTC','Location de voitures'],'hotel_brands':['ibis','Novotel','Courtyard by Marriott'],'signature':'Équilibre entre trafic régional, loisirs et affaires.'}
    return {'character':'Aéroport régional','access':['Bus / navette','Taxi','Location de voitures'],'hotel_brands':['ibis','Campanile','Best Western'],'signature':'Croissance graduelle et services adaptés au marché local.'}


def career_progress(db,u):
    flights=db.scalar(select(func.count()).select_from(FlightRecord).where(FlightRecord.user_id==u.id)) or 0
    claims=db.scalar(select(func.count()).select_from(DailyQuestClaim).where(DailyQuestClaim.user_id==u.id)) or 0
    hubs=db.scalar(select(func.count()).select_from(UserHub).where(UserHub.user_id==u.id)) or 0
    aircraft=db.scalar(select(func.count()).select_from(Aircraft).where(Aircraft.user_id==u.id)) or 0
    routes=db.scalar(select(func.count()).select_from(Route).where(Route.user_id==u.id)) or 0
    staff=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id)) or 0
    upgrade_levels=db.scalar(select(func.sum(HubUpgrade.level)).where(HubUpgrade.user_id==u.id)) or 0
    xp=int(flights*45 + claims*180 + hubs*220 + aircraft*85 + routes*70 + staff*8 + upgrade_levels*22 + max(0,u.reputation-50)*25)
    level=1;spent=0
    while level<100:
        need=int(700 + level*165 + (level**1.38)*26)
        if xp-spent < need:break
        spent+=need;level+=1
    need=int(700 + level*165 + (level**1.38)*26) if level<100 else 1
    current=max(0,xp-spent)
    pct=100 if level>=100 else min(100,round(current/need*100,1))
    era=('Fondateur' if level<10 else 'Compagnie internationale' if level<30 else 'Groupe aérien' if level<60 else 'Opérateur mondial')
    return {'level':level,'xp_total':xp,'xp_current':current,'xp_next':need,'progress_pct':pct,'era':era,'flights_completed':flights,'quests_claimed':claims}


def hub_satisfaction(db,u,ident,airport=None):
    airport=airport or airport_detail(ident)
    levels=hub_levels(db,u.id,ident)
    base={'large_airport':62,'medium_airport':66,'small_airport':69,'heliport':68}.get((airport or {}).get('type'),65)
    def avg(codes,scale=4):
        vals=[levels.get(c,0) for c in codes]
        return min(24, sum(vals)*scale/max(1,len(vals)))
    terminal=avg(['TERMINAL','CHECKIN','SELFSERVICE','BOARDING','ARRIVALS'],4.0)
    baggage=avg(['BAGGAGE','GROUND_FLEET'],5.0)
    security=avg(['SECURITY','BORDER','CUSTOMS','FIRE','MEDICAL'],3.5)
    comfort=avg(['TOILETS','WIFI','SIGNAGE','LOUNGE_BUS','LOUNGE_FIRST','FOOD'],3.2)
    access=avg(['TRANSIT','PARK_SHORT','PARK_LONG','PARK_PREM'],4.0)
    operations=avg(['TAXI','PUSHBACK','FUEL','OPS','LINE_MAINT'],3.2)
    assets=db.scalar(select(func.count()).select_from(HubAsset).where(HubAsset.user_id==u.id,HubAsset.airport_ident==ident)) or 0
    staff=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id,Employee.home_hub==ident)) or 0
    routes=db.scalar(select(func.count()).select_from(Route).where(Route.user_id==u.id,Route.origin==ident)) or 0
    infrastructure=min(17,(terminal+baggage+security+comfort+access+operations)/12 + min(5,assets*.45))
    staffing=min(5,staff/5)
    congestion=max(0,(routes-(5+assets//2))*0.8)
    score=round(max(45,min(98,base+infrastructure+staffing-congestion)))
    # Subscores are designed to be explanatory rather than additional simulations.
    subs={
        'Ponctualité':round(max(45,min(99,base+operations+staffing-congestion))),
        'Embarquement':round(max(45,min(99,base+terminal*.9))),
        'Sécurité':round(max(50,min(99,70+security))),
        'Bagages':round(max(45,min(99,base+baggage))),
        'Confort':round(max(45,min(99,base+comfort))),
        'Accès':round(max(45,min(99,base+access))),
    }
    return {'score':score,'label':'Excellent' if score>=90 else 'Très bon' if score>=82 else 'Bon' if score>=74 else 'Correct' if score>=65 else 'À améliorer','subscores':subs}


def daily_quests(db,u):
    today=now_utc().date().isoformat();start=datetime.combine(now_utc().date(),datetime.min.time(),tzinfo=timezone.utc)
    flights=db.scalar(select(func.count()).select_from(FlightRecord).where(FlightRecord.user_id==u.id,FlightRecord.completed_at>=start)) or 0
    pax=db.scalar(select(func.sum(FlightRecord.passengers)).where(FlightRecord.user_id==u.id,FlightRecord.completed_at>=start)) or 0
    progress=career_progress(db,u);level=progress['level']
    primary=primary_hub(db,u);sat=hub_satisfaction(db,u,primary.airport_ident)['score'] if primary else 0
    rot_target=min(20,3+(level//10)*2);pax_target=max(750,rot_target*180);sat_target=min(92,78+(level//15)*2)
    claimed={x.quest_code for x in db.scalars(select(DailyQuestClaim).where(DailyQuestClaim.user_id==u.id,DailyQuestClaim.quest_date==today)).all()}
    scale=1+min(3,level/30)
    defs=[
        ('rotations','Effectuer des rotations',flights,rot_target,int(180_000*scale),120,25),
        ('passengers','Transporter des passagers',pax,pax_target,int(140_000*scale),100,20),
        ('satisfaction','Maintenir la satisfaction du hub',sat,sat_target,int(100_000*scale),80,15),
    ]
    items=[]
    for code,label,value,target,cash,xp,tokens in defs:
        items.append({'code':code,'label':label,'value':int(value),'target':int(target),'cash_reward':cash,'xp_reward':xp,'token_reward':tokens,'complete':value>=target,'claimed':code in claimed})
    return {'date':today,'items':items}

# -------- Page routes --------
@app.get('/health')
def health():return {'status':'ok','version':'1.1.0','catalog':'85k+ airports / 591+ aircraft types','sim_speed':SIM_SPEED,'fr24_configured':bool(_fr24_token()) if '_fr24_token' in globals() else False}

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
class LoanReq(BaseModel):amount:float;term_months:int;bank_id:str=''
class QuestClaimReq(BaseModel):quest_code:str
class LoanRepayReq(BaseModel):loan_id:int;amount:float
class CampaignReq(BaseModel):campaign_type:str;spend:float;duration_days:int=14
class PartnerReq(BaseModel):offer_id:str
class HotelReq(BaseModel):airport_ident:str;name:str='SKYLINE Hotel';stars:int=3;rooms:int=120
class HotelUpgradeReq(BaseModel):hotel_id:int
class HotelPartnerReq(BaseModel):offer_key:str
class HubAssetBuyReq(BaseModel):ident:str;asset_key:str;kind:str;name:str='';lon:float;lat:float
class SpecialBaseReq(BaseModel):airport_ident:str;branch:str
class SpecialContractReq(BaseModel):contract_code:str;base_id:int

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
def api_aircraft_catalog(q:str='',manufacturer:str='',commercial_only:bool=False,limit:int=60,offset:int=0):
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
        sat=hub_satisfaction(db,u,ident,a);reality=hub_reality_profile(a)
        today=datetime.combine(now_utc().date(),datetime.min.time(),tzinfo=timezone.utc);code=a['code']
        recs=db.scalars(select(FlightRecord).where(FlightRecord.user_id==u.id,FlightRecord.completed_at>=today,((FlightRecord.origin==code)|(FlightRecord.destination==code)))).all()
        pax=sum(x.passengers for x in recs);revenue=sum(x.ticket_revenue+x.ancillary_revenue for x in recs);profit=sum(x.profit for x in recs)
        route_count=db.scalar(select(func.count()).select_from(Route).where(Route.user_id==u.id,Route.origin==ident)) or 0
        prestige=max(1,min(5,round((sat['score']/100)*2.2+lvl*.45+u.reputation/100*1.2)))
        return {'airport':a,'hub':{'level':lvl,'is_primary':h.is_primary,'satisfaction':sat,'prestige':prestige,
                'daily_passengers':pax,'daily_flights':len(recs),'daily_revenue':round(revenue,2),'daily_profit':round(profit,2),'active_routes':route_count},
                'reality':reality,'nodes':nodes,'own_ground_aircraft':own,'traffic_density':density,
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
        u=require_user(request,db);pr=career_progress(db,u)
        min_level=int(spec.get('min_level') or 1)
        if pr['level']<min_level:raise HTTPException(400,f"Niveau {min_level} requis pour cet appareil spécialisé (niveau actuel {pr['level']}).")
        hub=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.home_hub))
        if not hub:raise HTTPException(400,'Base non possédée')
        price=spec['price'] if req.acquisition=='buy' else spec['lease']
        # Premium shop entitlements accelerate progression without making the aircraft inaccessible to free players.
        ent={x.item_code for x in db.scalars(select(ShopEntitlement).where(ShopEntitlement.user_id==u.id)).all()}
        if spec['icao'].startswith('A35') and 'premium_a350' in ent:price*=.92
        if spec['icao'] in ('B38M','B37M','B39M','B3JM') and 'premium_b38m' in ent:price*=.92
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
        crew=crew_status_for(db,u.id,spec,haversine_km(o['lat'],o['lon'],d['lat'],d['lon']),r.origin)
        estimate=economy_detailed(o,d,spec,u.reputation,cfg,sdict,active_marketing_boost(db,u.id),partner_revenue_bonus(db,u.id),crew['cost_factor'],research_cost_factor(db,u.id,spec))
        return {'settings':cfg,'estimate':estimate,'crew':crew}

@app.post('/api/routes/{route_id}/pricing')
def api_route_pricing_set(route_id:int,req:RoutePricingReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);r=db.get(Route,route_id)
        if not r or r.user_id!=u.id:raise HTTPException(404,'Ligne introuvable')
        s=settings_for(db,u.id,r)
        s.economy_price=max(15,min(5000,req.economy_price));s.premium_price=max(s.economy_price,min(9000,req.premium_price));s.business_price=max(s.premium_price,min(15000,req.business_price));s.first_price=max(s.business_price,min(30000,req.first_price));s.baggage_fee=max(0,min(300,req.baggage_fee));s.overbooking_percent=max(0,min(15,req.overbooking_percent));db.commit();return {'ok':True}

@app.get('/api/quests')
def api_quests(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);settle_economy(db,u)
        return daily_quests(db,u)

@app.post('/api/quests/claim')
def api_quest_claim(req:QuestClaimReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);settle_economy(db,u);data=daily_quests(db,u)
        q=next((x for x in data['items'] if x['code']==req.quest_code),None)
        if not q:raise HTTPException(404,'Quête inconnue')
        if not q['complete']:raise HTTPException(400,'Objectif pas encore terminé')
        if q['claimed']:raise HTTPException(400,'Récompense déjà récupérée')
        row=DailyQuestClaim(user_id=u.id,quest_date=data['date'],quest_code=q['code'],cash_reward=q['cash_reward'],xp_reward=q['xp_reward'])
        u.cash+=q['cash_reward'];w=wallet_for(db,u.id);w.tokens+=int(q.get('token_reward') or 0)
        db.add(row);log_tx(db,u.id,'quest',f"Quête quotidienne · {q['label']}",q['cash_reward']);db.commit()
        return {'ok':True,'cash_reward':q['cash_reward'],'xp_reward':q['xp_reward'],'token_reward':int(q.get('token_reward') or 0),'tokens':w.tokens}

@app.get('/api/banks')
def api_banks(request:Request,ident:str=''):
    with SessionLocal() as db:
        u=require_user(request,db);progress=career_progress(db,u)
        h=None
        if ident:h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==ident))
        if not h:h=primary_hub(db,u)
        a=airport_detail(h.airport_ident) if h else None
        country=(a or {}).get('country','')
        offers=[]
        for b in bank_catalog_for_country(country):
            offers.append({**b,'available':progress['level']>=b['min_level'],'country':country})
        return {'country':country,'hub':(a or {}).get('code',''),'level':progress['level'],'offers':offers}

@app.post('/api/finance/bank-loan')
def api_take_bank_loan(req:LoanReq,request:Request):
    amount=max(1_000_000,min(1_000_000_000,req.amount));term=req.term_months
    if term not in (12,24,36,48,60,84,120):raise HTTPException(400,'Durée invalide')
    with SessionLocal() as db:
        u=require_user(request,db);progress=career_progress(db,u);h=primary_hub(db,u);a=airport_detail(h.airport_ident) if h else None
        catalogue=bank_catalog_for_country((a or {}).get('country',''));bank=next((x for x in catalogue if x['id']==req.bank_id),None)
        if not bank:raise HTTPException(404,'Banque indisponible pour ce marché')
        if progress['level']<bank['min_level']:raise HTTPException(400,f"Niveau {bank['min_level']} requis")
        if amount>bank['max_amount']:raise HTTPException(400,'Montant supérieur au plafond de cette banque')
        existing=(db.scalar(select(func.sum(Loan.outstanding)).where(Loan.user_id==u.id)) or 0)+(db.scalar(select(func.sum(BankLoanV6.outstanding)).where(BankLoanV6.user_id==u.id)) or 0)
        if existing>u.cash*3+350_000_000:raise HTTPException(400,'Endettement maximum atteint')
        apr=bank['base_apr'] + (amount/bank['max_amount'])*.012 + (12/term)*.006 - min(.009,max(0,u.reputation-50)/5000)
        l=BankLoanV6(user_id=u.id,bank_id=bank['id'],bank_name=bank['name'],principal=amount,outstanding=amount,apr=apr,term_months=term)
        u.cash+=amount;db.add(l);log_tx(db,u.id,'bank',f"{bank['name']} · financement {term} mois",amount);db.commit()
        return {'ok':True,'bank_name':bank['name'],'apr':apr,'amount':amount}

@app.post('/api/finance/bank-loan/{loan_id}/repay')
def api_repay_bank_loan(loan_id:int,req:LoanRepayReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);l=db.get(BankLoanV6,loan_id)
        if not l or l.user_id!=u.id:raise HTTPException(404,'Emprunt introuvable')
        amount=max(1,min(req.amount,l.outstanding,u.cash))
        if amount<=0:raise HTTPException(400,'Montant invalide')
        l.outstanding-=amount;u.cash-=amount;log_tx(db,u.id,'bank',f"Remboursement {l.bank_name}",-amount);db.commit();return {'ok':True,'remaining':l.outstanding}

@app.get('/api/finance')
def api_finance(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);settle_economy(db,u);db.refresh(u)
        flights=db.scalars(select(FlightRecord).where(FlightRecord.user_id==u.id).order_by(FlightRecord.id.desc()).limit(80)).all()
        tx=db.scalars(select(FinanceTransaction).where(FinanceTransaction.user_id==u.id).order_by(FinanceTransaction.id.desc()).limit(80)).all()
        loans=db.scalars(select(Loan).where(Loan.user_id==u.id).order_by(Loan.id.desc())).all()
        bank_loans=db.scalars(select(BankLoanV6).where(BankLoanV6.user_id==u.id).order_by(BankLoanV6.id.desc())).all()
        monthly=db.scalar(select(func.sum(Employee.salary_monthly)).where(Employee.user_id==u.id)) or 0
        return {'cash':u.cash,'monthly_payroll':monthly,'flights':[{'id':f.id,'tail':f.tail,'origin':f.origin,'destination':f.destination,'passengers':f.passengers,'load_factor':f.load_factor,'ticket_revenue':f.ticket_revenue,'ancillary_revenue':f.ancillary_revenue,'operating_cost':f.operating_cost,'profit':f.profit,'completed_at':f.completed_at.isoformat()} for f in flights],
                'transactions':[{'id':x.id,'category':x.category,'label':x.label,'amount':x.amount,'created_at':x.created_at.isoformat()} for x in tx],
                'loans':[{'id':l.id,'principal':l.principal,'outstanding':l.outstanding,'apr':l.apr,'term_months':l.term_months,'bank_name':'Financement historique','legacy':True} for l in loans],
                'bank_loans':[{'id':l.id,'principal':l.principal,'outstanding':l.outstanding,'apr':l.apr,'term_months':l.term_months,'bank_id':l.bank_id,'bank_name':l.bank_name,'legacy':False} for l in bank_loans]}

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
        hubs=user_hubs(db,u);offers=[]
        progress=career_progress(db,u)
        for h in hubs:
            a=airport_detail(h.airport_ident)
            if not a:continue
            prof=hub_reality_profile(a);sat=hub_satisfaction(db,u,h.airport_ident,a)['score']
            for i,name in enumerate(prof['hotel_brands']):
                min_level=8+i*2 if a['type']=='large_airport' else 5+i*2 if a['type']=='medium_airport' else 3+i*2
                offers.append({'key':f"{h.airport_ident}:{name}",'airport_ident':h.airport_ident,'airport_code':a['code'],'name':name,'character':prof['character'],
                               'min_level':min_level,'available':progress['level']>=min_level and sat>=65,'satisfaction_required':65,'hub_satisfaction':sat,
                               'partnership_fee':int((1_200_000+i*650_000)*(1.8 if a['type']=='large_airport' else 1.0))})
        return {'items':[{'id':h.id,'airport_ident':h.airport_ident,'name':h.name,'rooms':h.rooms,'stars':h.stars,'level':h.level} for h in rows],
                'partner_offers':offers,'player_level':progress['level']}

@app.post('/api/hotels/partner')
def api_hotel_partner(req:HotelPartnerReq,request:Request):
    try:ident,name=req.offer_key.split(':',1)
    except ValueError:raise HTTPException(400,'Offre invalide')
    with SessionLocal() as db:
        u=require_user(request,db);h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==ident))
        if not h:raise HTTPException(400,'Hub non possédé')
        a=airport_detail(ident);prof=hub_reality_profile(a);progress=career_progress(db,u);sat=hub_satisfaction(db,u,ident,a)['score']
        if name not in prof['hotel_brands']:raise HTTPException(404,'Partenaire non disponible sur ce marché')
        idx=prof['hotel_brands'].index(name);min_level=8+idx*2 if a['type']=='large_airport' else 5+idx*2 if a['type']=='medium_airport' else 3+idx*2
        if progress['level']<min_level:raise HTTPException(400,f'Niveau joueur {min_level} requis')
        if sat<65:raise HTTPException(400,'Satisfaction du hub de 65% minimum requise')
        partner_name=f'{name} · {a["code"]}'
        if db.scalar(select(Partner).where(Partner.user_id==u.id,Partner.name==partner_name)):raise HTTPException(400,'Partenariat déjà actif')
        fee=int((1_200_000+idx*650_000)*(1.8 if a['type']=='large_airport' else 1.0))
        if u.cash<fee:raise HTTPException(400,'Fonds insuffisants')
        row=Partner(user_id=u.id,partner_type='hotel',name=partner_name,sign_fee=fee,revenue_bonus=.004+.0015*idx,reputation_bonus=1)
        u.cash-=fee;u.reputation=min(100,u.reputation+1);db.add(row);log_tx(db,u.id,'partner',f'Partenariat hôtelier {partner_name}',-fee);db.commit()
        return {'ok':True,'name':partner_name,'fee':fee}

@app.post('/api/hotels')
def api_build_hotel(req:HotelReq,request:Request):
    stars=max(2,min(5,req.stars));rooms=max(60,min(900,req.rooms));cost=12_000_000+rooms*55_000+stars*3_000_000
    with SessionLocal() as db:
        u=require_user(request,db)
        if not db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.airport_ident)):raise HTTPException(400,'Hub non possédé')
        progress=career_progress(db,u);sat=hub_satisfaction(db,u,req.airport_ident)['score']
        if progress['level']<20:raise HTTPException(400,'La construction de vos propres hôtels se débloque au niveau joueur 20')
        if sat<70:raise HTTPException(400,'Satisfaction du hub de 70% minimum requise')
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
                sat=hub_satisfaction(db,u,h.airport_ident,a);reality=hub_reality_profile(a)
                hub_out.append({'ident':h.airport_ident,'is_primary':h.is_primary,'level':hub_level(levels),'asset_count':assets,'satisfaction':sat,'reality':reality,
                                'airport':{'ident':a['ident'],'code':a['code'],'name':a['name'],'lat':a['lat'],'lon':a['lon'],'type':a['type'],'country':a['country'],'municipality':a['municipality']}})
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
            crew=crew_status_for(db,u.id,s['spec'],haversine_km(o['lat'],o['lon'],d['lat'],d['lon']),r.origin) if o and d else {}
            econ=economy_detailed(o,d,s['spec'],u.reputation,cfg,sdict,marketing,pbonus,crew.get('cost_factor',1.0),research_cost_factor(db,u.id,s['spec'])) if o and d else None
            partner=None
            if r.commercial_destination:
                cd=airport_detail(r.commercial_destination)
                if cd:partner={'from':d['code'],'to':cd['code'],'from_lat':d['lat'],'from_lon':d['lon'],'to_lat':cd['lat'],'to_lon':cd['lon'],'airline':r.partner_airline,'aircraft':r.partner_aircraft}
            route_out.append({'id':r.id,'aircraft_id':a.id,'tail':a.tail,'model':s['spec']['name'],'origin':r.origin,'destination':r.destination,'commercial_destination':r.commercial_destination,'via':r.via,'frequency':r.frequency,'flight':s['flight'],'economy':econ,'pricing':cfg,'crew':crew,'partner':partner,
                              'origin_airport':o,'destination_airport':d})
        employees=db.scalar(select(func.count()).select_from(Employee).where(Employee.user_id==u.id)) or 0
        active_campaigns=db.scalar(select(func.count()).select_from(MarketingCampaign).where(MarketingCampaign.user_id==u.id,MarketingCampaign.ends_at>now_utc())) or 0
        progress=career_progress(db,u);quests=daily_quests(db,u)
        overall_sat=round(sum(h['satisfaction']['score'] for h in hub_out)/len(hub_out)) if hub_out else 0
        today_start=datetime.combine(now_utc().date(),datetime.min.time(),tzinfo=timezone.utc)
        today_flights=db.scalars(select(FlightRecord).where(FlightRecord.user_id==u.id,FlightRecord.completed_at>=today_start)).all()
        today_profit=sum(x.profit for x in today_flights);today_pax=sum(x.passengers for x in today_flights)
        db.commit()
        return {'user':{'username':u.username,'company_name':u.company_name,'cash':round(u.cash,2),'reputation':u.reputation},
                'profile':{'primary_color':p.primary_color,'secondary_color':p.secondary_color,'accent_color':p.accent_color,'logo_text':p.logo_text,'logo_data':p.logo_data,'livery_template':p.livery_template},
                'hubs':hub_out,'aircraft':aircraft,'routes':route_out,'sim_speed':SIM_SPEED,'progression':progress,'quests':quests,
                'company':{'employees':employees,'marketing_boost':marketing,'active_campaigns':active_campaigns,'partner_bonus':pbonus,'satisfaction':overall_sat,
                           'today_flights':len(today_flights),'today_profit':round(today_profit,2),'today_passengers':today_pax}}

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


@app.get('/api/weather/radar')
def api_weather_radar(request:Request):
    # Proxy the RainViewer metadata server-side so browser CORS/ad blockers do not
    # silently kill the weather layer. No long-term weather data is persisted.
    with SessionLocal() as db:require_user(request,db)
    now=time.time();key=('rainviewer','metadata');cached=_weather_cache.get(key)
    if cached and now-cached[0] < 120:return cached[1]
    try:
        with httpx.Client(timeout=6.0,headers={'User-Agent':'SKYLINE-Airways/0.8'}) as client:
            r=client.get('https://api.rainviewer.com/public/weather-maps.json');r.raise_for_status();d=r.json()
        frame=((d.get('radar') or {}).get('past') or [])
        frame=frame[-1] if frame else None
        out={'ok':bool(frame),'source':'RainViewer','host':d.get('host',''),'path':(frame or {}).get('path',''),'generated':(frame or {}).get('time')}
    except Exception as e:
        out={'ok':False,'source':'RainViewer','reason':type(e).__name__}
    _weather_cache[key]=(now,out);return out

FR24_BASE_URL=os.getenv('FR24_API_BASE_URL','https://fr24api.flightradar24.com/api').rstrip('/')

def _fr24_token():
    # Primary key plus compatible aliases to avoid a silent failure when the secret
    # was already created in Render under a different obvious name.
    for key in ('FR24_API_TOKEN','FLIGHTRADAR24_API_TOKEN','FLIGHTRADAR_TOKEN','FR24_TOKEN'):
        value=os.getenv(key,'').strip()
        if value:return value
    return ''

def _fr24_headers():
    return {
        'Authorization':f'Bearer {_fr24_token()}',
        'Accept':'application/json',
        'Accept-Version':'v1',
        'User-Agent':'SKYLINE-Airways/0.7.1'
    }

def _fr24_normalize(x, airport=None):
    """Normalize FR24 full-position payload without ever exposing the API token."""
    lat=x.get('lat'); lon=x.get('lon')
    if lat is None or lon is None:return None
    try: alt=float(x.get('alt')) if x.get('alt') is not None else None
    except (TypeError,ValueError): alt=None
    try: speed=float(x.get('gspeed')) if x.get('gspeed') is not None else None
    except (TypeError,ValueError): speed=None
    try: heading=float(x.get('track') or 0)
    except (TypeError,ValueError): heading=0
    distance_km=None; on_ground=False; phase='airborne'
    if airport:
        distance_km=haversine_km(float(airport['lat']),float(airport['lon']),float(lat),float(lon))
        elev=float(airport.get('elevation_ft') or 0)
        # FR24's full-position payload does not provide a universal on_ground flag.
        # For an airport view we infer surface traffic from proximity, field elevation
        # and groundspeed. This fixes high-elevation airports where `alt < 200` fails.
        surface_radius=7.5 if airport.get('type')=='large_airport' else 5.5 if airport.get('type')=='medium_airport' else 4.0
        altitude_margin=700 if airport.get('type')=='large_airport' else 550
        low_enough=(alt is None) or alt <= elev+altitude_margin
        slow_enough=(speed is None) or speed <= 85
        on_ground=distance_km <= surface_radius and low_enough and slow_enough
        if on_ground: phase='ground'
        elif distance_km <= 18 and alt is not None and alt <= elev+6000: phase='terminal-area'
    else:
        # Approximation used only to keep obvious surface targets off the world-globe layer.
        on_ground=(speed is not None and speed <= 55 and alt is not None and alt <= 1200)
        if on_ground:phase='ground'
    return {
        'id':x.get('fr24_id'),'callsign':x.get('callsign') or x.get('flight') or '',
        'flight':x.get('flight') or '', 'country':'','lon':float(lon),'lat':float(lat),
        'altitude_ft':alt,'velocity_kts':speed,'heading':heading,'type':x.get('type') or '',
        'reg':x.get('reg') or '','origin':x.get('orig_iata') or x.get('orig_icao') or '',
        'destination':x.get('dest_iata') or x.get('dest_icao') or '',
        'airline':x.get('painted_as') or x.get('operating_as') or '',
        'on_ground':on_ground,'phase':phase,'distance_km':round(distance_km,2) if distance_km is not None else None,
        'timestamp':x.get('timestamp')
    }

def _fetch_fr24(bounds,limit=120,airport=None):
    token=_fr24_token()
    if not token:raise RuntimeError('FR24_API_TOKEN absent')
    headers=_fr24_headers()
    last_error=None
    with httpx.Client(timeout=9.0,headers=headers) as client:
        for mode in ('full','light'):
            try:
                r=client.get(f'{FR24_BASE_URL}/live/flight-positions/{mode}',params={'bounds':bounds,'limit':max(1,min(180,int(limit)))})
                r.raise_for_status()
                raw=r.json().get('data') or []
                states=[]
                for x in raw:
                    n=_fr24_normalize(x,airport)
                    if n:states.append(n)
                if airport:states.sort(key=lambda x:(x.get('distance_km') is None,x.get('distance_km') or 9999))
                return states,mode
            except httpx.HTTPStatusError as e:
                last_error=e
                # Some FR24 plans expose light but not full. Try light before falling back.
                if mode=='full' and e.response.status_code in (401,402,403,404,429):
                    continue
                raise
    if last_error:raise last_error
    return [],'full'

def _opensky_hub(a,span):
    params={'lamin':a['lat']-span,'lomin':a['lon']-span,'lamax':a['lat']+span,'lomax':a['lon']+span}
    with httpx.Client(timeout=7.0,headers={'User-Agent':'SKYLINE-Airways/0.7.1'}) as client:
        r=client.get('https://opensky-network.org/api/states/all',params=params);r.raise_for_status();raw=r.json().get('states') or []
    states=[]
    for x in raw[:140]:
        if len(x)<11 or x[5] is None or x[6] is None:continue
        dist=haversine_km(a['lat'],a['lon'],x[6],x[5])
        states.append({'id':x[0],'icao24':x[0],'callsign':(x[1] or '').strip(),'flight':(x[1] or '').strip(),'country':x[2] or '',
                       'lon':x[5],'lat':x[6],'altitude_ft':int((x[7] or 0)*3.28084),'velocity_kts':round((x[9] or 0)*1.94384,1),
                       'heading':x[10] or 0,'type':'','reg':'','origin':'','destination':'','airline':'','on_ground':bool(x[8]),
                       'phase':'ground' if bool(x[8]) else 'airborne','distance_km':round(dist,2)})
    states.sort(key=lambda x:x.get('distance_km',9999))
    return states

@app.get('/api/integrations/fr24/status')
def api_fr24_status(request:Request):
    with SessionLocal() as db:require_user(request,db)
    configured=bool(_fr24_token())
    return {'configured':configured,'provider':'Flightradar24 API' if configured else 'OpenSky fallback',
            'api_version':'v1','secret_location':'server environment','token_exposed':False}


@app.get('/api/integrations/fr24/test')
def api_fr24_test(request:Request,ident:str='CDG'):
    with SessionLocal() as db:require_user(request,db)
    if not _fr24_token():
        return {'ok':False,'configured':False,'provider':'Flightradar24','reason':'FR24_API_TOKEN absent dans l’environnement Render.'}
    a=airport_detail(ident)
    if not a:raise HTTPException(404,'Aéroport introuvable')
    span=.12
    bounds=f"{a['lat']+span},{a['lat']-span},{a['lon']-span},{a['lon']+span}"
    try:
        states,mode=_fetch_fr24(bounds,25,a)
        return {'ok':True,'configured':True,'provider':'Flightradar24','mode':mode,'airport':a['code'],
                'count':len(states),'ground_count':sum(1 for x in states if x.get('on_ground')),
                'message':'Connexion FR24 valide. Les positions brutes ne sont pas stockées.'}
    except httpx.HTTPStatusError as e:
        return {'ok':False,'configured':True,'provider':'Flightradar24','status_code':e.response.status_code,
                'reason':'Clé refusée, crédit/plan insuffisant, ou endpoint non autorisé.'}
    except Exception as e:
        return {'ok':False,'configured':True,'provider':'Flightradar24','reason':type(e).__name__}

@app.get('/api/live-traffic')
def api_live_traffic(ident:str):
    """Traffic around one airport. FR24 is preferred here as well as on the globe."""
    a=airport_detail(ident)
    if not a:raise HTTPException(404,'Aéroport introuvable')
    now=time.time();provider='fr24' if _fr24_token() else 'opensky';key=('hub',a['ident'],provider);cached=_traffic_cache.get(key)
    if cached and now-cached[0]<22:return cached[1]
    span=.18 if a['type']=='large_airport' else .13 if a['type']=='medium_airport' else .10
    fr24_error=None
    if _fr24_token():
        try:
            bounds=f"{a['lat']+span},{a['lat']-span},{a['lon']-span},{a['lon']+span}"
            states,fr24_mode=_fetch_fr24(bounds,120,a)
            out={'source':'Flightradar24 API','states':states,'licensed':True,'configured':True,
                 'ground_count':sum(1 for x in states if x.get('on_ground')),'nearby_count':len(states),'real_only':True,'fr24_mode':fr24_mode}
            _traffic_cache[key]=(now,out);return out
        except httpx.HTTPStatusError as e:
            fr24_error=f'HTTP {e.response.status_code}'
        except Exception as e:
            fr24_error=type(e).__name__
    try:
        states=_opensky_hub(a,span)
        out={'source':'OpenSky','states':states,'licensed':False,'configured':bool(_fr24_token()),
             'ground_count':sum(1 for x in states if x.get('on_ground')),'nearby_count':len(states),'real_only':True}
        if fr24_error:out['fr24_error']=fr24_error
    except Exception:
        out={'source':'unavailable','states':[],'licensed':False,'configured':bool(_fr24_token()),'ground_count':0,'nearby_count':0,'real_only':True}
        if fr24_error:out['fr24_error']=fr24_error
    _traffic_cache[key]=(now,out);return out

@app.get('/api/live-traffic/box')
def api_live_traffic_box(lamin:float,lomin:float,lamax:float,lomax:float,limit:int=300):
    lamin=max(-85,min(85,lamin));lamax=max(-85,min(85,lamax));lomin=max(-180,min(180,lomin));lomax=max(-180,min(180,lomax));limit=max(20,min(180,limit))
    bucket=(round(lamin,1),round(lomin,1),round(lamax,1),round(lomax,1),limit,'fr24' if _fr24_token() else 'opensky');now=time.time();cached=_traffic_cache.get(('box',)+bucket)
    if cached and now-cached[0]<24:return cached[1]
    fr24_error=None
    if _fr24_token():
        try:
            bounds=f'{lamax},{lamin},{lomin},{lomax}'
            states,fr24_mode=_fetch_fr24(bounds,limit)
            out={'source':'Flightradar24 API','states':states,'licensed':True,'configured':True,'real_only':True,'fr24_mode':fr24_mode}
            _traffic_cache[('box',)+bucket]=(now,out);return out
        except httpx.HTTPStatusError as e:
            fr24_error=f'HTTP {e.response.status_code}'
        except Exception as e:
            fr24_error=type(e).__name__
    try:
        params={'lamin':lamin,'lomin':lomin,'lamax':lamax,'lomax':lomax}
        with httpx.Client(timeout=7.0,headers={'User-Agent':'SKYLINE-Airways/0.7.1'}) as client:
            r=client.get('https://opensky-network.org/api/states/all',params=params);r.raise_for_status();raw=r.json().get('states') or []
        states=[]
        for x in raw[:limit]:
            if len(x)<11 or x[5] is None or x[6] is None:continue
            states.append({'id':x[0],'callsign':(x[1] or '').strip(),'flight':(x[1] or '').strip(),'country':x[2] or '', 'lon':x[5],'lat':x[6],
                           'altitude_ft':int((x[7] or 0)*3.28084),'velocity_kts':round((x[9] or 0)*1.94384,1),'heading':x[10] or 0,'type':'','reg':'',
                           'origin':'','destination':'','airline':'','on_ground':bool(x[8]),'phase':'ground' if bool(x[8]) else 'airborne'})
        out={'source':'OpenSky','states':states,'licensed':False,'configured':bool(_fr24_token()),'real_only':True}
        if fr24_error:out['fr24_error']=fr24_error
    except Exception:
        out={'source':'unavailable','states':[],'licensed':False,'configured':bool(_fr24_token()),'real_only':True}
        if fr24_error:out['fr24_error']=fr24_error
    _traffic_cache[('box',)+bucket]=(now,out);return out


SPECIAL_BRANCHES={
    'sar':{'label':'Secours héliporté / SAR','min_level':61,'base_cost':18_000_000,'icon':'🚁',
           'desc':'Medevac, secours montagne et maritime, missions automatiques H24.'},
    'fire':{'label':'Sécurité civile / incendies','min_level':66,'base_cost':28_000_000,'icon':'🛩️',
            'desc':'Bases bombardiers d’eau, remplissage, maintenance et contrats saisonniers.'},
    'gendarmerie':{'label':'Gendarmerie / service public','min_level':71,'base_cost':24_000_000,'icon':'🚁',
                   'desc':'Couverture territoriale, disponibilité H24 et interventions automatisées.'},
    'government':{'label':'Contrats gouvernementaux','min_level':76,'base_cost':38_000_000,'icon':'🏛️',
                  'desc':'Transport d’État, logistique et missions internationales.'},
    'defense':{'label':'Défense du territoire','min_level':81,'base_cost':75_000_000,'icon':'🛡️',
               'desc':'Gestion stratégique de transport, surveillance, ravitaillement et disponibilité. Aucun combat pilotable.'},
}
SPECIAL_CONTRACT_TEMPLATES=[
    {'code':'pt_fire_summer','branch':'fire','title':'Soutien incendies – Portugal','country':'Portugal','reward':5_850_000,'days':14,'min_level':66,'aircraft':['CL2T'],'required_count':2},
    {'code':'fr_sar_h24','branch':'sar','title':'Couverture secours H24','country':'France','reward':3_200_000,'days':10,'min_level':61,'aircraft':['EC45','A139'],'required_count':2},
    {'code':'med_sar','branch':'sar','title':'Surveillance & secours maritime','country':'Méditerranée','reward':4_100_000,'days':12,'min_level':63,'aircraft':['EC45','A139'],'required_count':1},
    {'code':'public_h24','branch':'gendarmerie','title':'Disponibilité service public H24','country':'France','reward':4_800_000,'days':14,'min_level':71,'aircraft':['EC45','NH90'],'required_count':2},
    {'code':'gov_airlift','branch':'government','title':'Pont aérien gouvernemental','country':'International','reward':8_500_000,'days':14,'min_level':76,'aircraft':['A400','C30J'],'required_count':2},
    {'code':'territory_readiness','branch':'defense','title':'Disponibilité stratégique territoriale','country':'Europe','reward':12_000_000,'days':14,'min_level':81,'aircraft':['A400','C30J','RFAL','MQ9'],'required_count':3},
]

@app.get('/api/special-ops')
def api_special_ops(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u)
        bases=db.scalars(select(SpecialBase).where(SpecialBase.user_id==u.id).order_by(SpecialBase.id)).all()
        contracts=db.scalars(select(SpecialContract).where(SpecialContract.user_id==u.id).order_by(SpecialContract.id.desc())).all()
        base_out=[{'id':b.id,'airport_ident':b.airport_ident,'branch':b.branch,'name':b.name,'level':b.level,'purchase_price':b.purchase_price} for b in bases]
        owned_by_branch={b.branch for b in bases}
        items=[]
        for code,meta in SPECIAL_BRANCHES.items():
            m=dict(meta);m['code']=code;m['unlocked']=pr['level']>=meta['min_level'];m['owned']=code in owned_by_branch
            m['reason']='Disponible' if m['unlocked'] else f"Niveau {meta['min_level']} requis (actuel {pr['level']})"
            items.append(m)
        fleet_types=[x for (x,) in db.execute(select(Aircraft.type_icao).where(Aircraft.user_id==u.id)).all()]
        ct=[]
        for t in SPECIAL_CONTRACT_TEMPLATES:
            row=dict(t);row['unlocked']=pr['level']>=t['min_level'];row['has_base']=t['branch'] in owned_by_branch
            row['compatible_aircraft_count']=sum(1 for code in fleet_types if code in t['aircraft'])
            row['fleet_ready']=row['compatible_aircraft_count']>=t.get('required_count',1)
            row['active']=any(c.contract_code==t['code'] and c.status=='active' for c in contracts)
            ct.append(row)
        active=[{'id':c.id,'title':c.title,'country':c.country,'branch':c.branch,'reward':c.reward,'status':c.status,
                 'ends_at':c.ends_at.isoformat() if c.ends_at else None} for c in contracts[:20]]
        return {'level':pr['level'],'branches':items,'bases':base_out,'contracts':ct,'active_contracts':active}

@app.post('/api/special-ops/base')
def api_special_base(req:SpecialBaseReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u);meta=SPECIAL_BRANCHES.get(req.branch)
        if not meta:raise HTTPException(404,'Branche spécialisée inconnue')
        if pr['level']<meta['min_level']:raise HTTPException(400,f"Niveau {meta['min_level']} requis")
        h=db.scalar(select(UserHub).where(UserHub.user_id==u.id,UserHub.airport_ident==req.airport_ident))
        if not h:raise HTTPException(400,'Cette base doit être construite sur un hub possédé.')
        existing=db.scalar(select(SpecialBase).where(SpecialBase.user_id==u.id,SpecialBase.airport_ident==req.airport_ident,SpecialBase.branch==req.branch))
        if existing:return {'ok':True,'base_id':existing.id,'already_owned':True}
        cost=meta['base_cost']
        if u.cash<cost:raise HTTPException(400,'Trésorerie insuffisante')
        u.cash-=cost;b=SpecialBase(user_id=u.id,airport_ident=req.airport_ident,branch=req.branch,name=f"{meta['label']} · {req.airport_ident}",purchase_price=cost)
        db.add(b);log_tx(db,u.id,'special_base',f"Base spécialisée · {meta['label']}",-cost);db.commit();db.refresh(b)
        return {'ok':True,'base_id':b.id,'cash':u.cash}

@app.post('/api/special-ops/contract')
def api_special_contract(req:SpecialContractReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u);t=next((x for x in SPECIAL_CONTRACT_TEMPLATES if x['code']==req.contract_code),None)
        if not t:raise HTTPException(404,'Contrat inconnu')
        if pr['level']<t['min_level']:raise HTTPException(400,f"Niveau {t['min_level']} requis")
        base=db.get(SpecialBase,req.base_id)
        if not base or base.user_id!=u.id or base.branch!=t['branch']:raise HTTPException(400,'Base spécialisée compatible requise')
        fleet_types=[x for (x,) in db.execute(select(Aircraft.type_icao).where(Aircraft.user_id==u.id)).all()]
        compatible=sum(1 for code in fleet_types if code in t['aircraft'])
        if compatible < t.get('required_count',1):
            raise HTTPException(400,f"Flotte compatible insuffisante : {t.get('required_count',1)} appareil(s) requis parmi {', '.join(t['aircraft'])}.")
        existing=db.scalar(select(SpecialContract).where(SpecialContract.user_id==u.id,SpecialContract.contract_code==t['code'],SpecialContract.status=='active'))
        if existing:return {'ok':True,'contract_id':existing.id,'already_active':True}
        # Contract engine is strategic: dispatch and mission execution are automatic.
        c=SpecialContract(user_id=u.id,base_id=base.id,contract_code=t['code'],branch=t['branch'],title=t['title'],country=t['country'],
                          reward=t['reward'],ends_at=now_utc()+timedelta(days=t['days']))
        db.add(c);db.commit();db.refresh(c)
        return {'ok':True,'contract_id':c.id,'status':'active','message':'Contrat activé. Dispatch automatique par OPS.'}

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
        f'way["aeroway"="terminal"]({south},{west},{north},{east});'
        f'node["aeroway"="gate"]({south},{west},{north},{east});'
        f'node["aeroway"="parking_position"]({south},{west},{north},{east});'
        ');out body;>;out skel qt;'
    )
    out=None
    try:
        with httpx.Client(timeout=10,headers={'User-Agent':'SKYLINE-Airways-Realism/0.6'}) as client:
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
                if kind in ('apron','terminal') and len(coords)>=3:
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
            priority={'runway':0,'terminal':1,'taxiway':2,'gate':3,'parking_position':4,'apron':5}
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
        db.execute(delete(SpecialContract).where(SpecialContract.user_id==u.id));db.execute(delete(SpecialBase).where(SpecialBase.user_id==u.id));db.execute(delete(CompanyResearch).where(CompanyResearch.user_id==u.id));db.execute(delete(ShopEntitlement).where(ShopEntitlement.user_id==u.id));db.execute(delete(AirlineAllianceMembership).where(AirlineAllianceMembership.user_id==u.id));db.execute(delete(HRPolicy).where(HRPolicy.user_id==u.id));db.execute(delete(IPOState).where(IPOState.user_id==u.id));db.execute(delete(GameWallet).where(GameWallet.user_id==u.id));db.execute(delete(Route).where(Route.user_id==u.id));db.execute(delete(Aircraft).where(Aircraft.user_id==u.id));db.execute(delete(HubAsset).where(HubAsset.user_id==u.id));db.execute(delete(HubUpgrade).where(HubUpgrade.user_id==u.id));db.execute(delete(HotelProperty).where(HotelProperty.user_id==u.id));db.execute(delete(Partner).where(Partner.user_id==u.id));db.execute(delete(MarketingCampaign).where(MarketingCampaign.user_id==u.id));db.execute(delete(Employee).where(Employee.user_id==u.id));db.execute(delete(Loan).where(Loan.user_id==u.id));db.execute(delete(FinanceTransaction).where(FinanceTransaction.user_id==u.id));db.execute(delete(UserHub).where(UserHub.user_id==u.id))
        u.cash=180_000_000;u.reputation=50;u.hub_code='';u.last_settled=now_utc();db.commit();return {'ok':True}

# ============================================================================
# v1.1 PREMIUM FUNCTIONAL — shop, alliances and real-traffic world seed
# ============================================================================
class ShopPurchaseReq(BaseModel):
    item_code:str
class AirlineAllianceJoinReq(BaseModel):
    alliance_code:str
class PlayerAllianceCreateReq(BaseModel):
    name:str
    tag:str
class PlayerAllianceJoinReq(BaseModel):
    alliance_id:int
class PlayerAllianceContributionReq(BaseModel):
    amount:float
class AllianceChatReq(BaseModel):
    message:str

SHOP_ITEMS=[
    {'code':'livery_airfrance','type':'livery','title':'Air France · livrée officielle (prototype privé)','subtitle':'Habillage Air France pour le studio de livrée','token_price':650,'cash_price':0,'image':'/static/liveries/airfrance-a350.jpg','premium':True},
    {'code':'premium_a350','type':'aircraft_access','title':'Airbus A350 · accès premium','subtitle':'Déverrouille la sélection premium A350 dans la boutique','token_price':900,'cash_price':0,'image':'/static/aircraft/real/a350.jpg','premium':True},
    {'code':'premium_b38m','type':'aircraft_access','title':'Boeing 737 MAX 8 · accès premium','subtitle':'Accès premium et fiche photo vérifiée','token_price':700,'cash_price':0,'image':'/static/aircraft/real/b737max8.jpg','premium':True},
    {'code':'pack_growth','type':'pack','title':'Pack Croissance','subtitle':'Capital + tokens pour accélérer une expansion sans contourner les prérequis','token_price':1200,'cash_price':8_000_000,'image':'/static/aircraft/real/a321neo.jpg','premium':False,'bonus_cash':12_000_000,'bonus_tokens':350},
    {'code':'pack_flagship','type':'pack','title':'Pack Flagship','subtitle':'Capital + tokens pour développer un hub majeur','token_price':2600,'cash_price':18_000_000,'image':'/static/aircraft/real/a350.jpg','premium':True,'bonus_cash':28_000_000,'bonus_tokens':900},
]
AIRLINE_ALLIANCES={
    'skyteam':{'code':'skyteam','name':'SkyTeam','logo':'/static/brands/skyteam.svg','min_level':30,'description':'Codeshare, salons partenaires et bonus de correspondance.'},
    'star':{'code':'star','name':'Star Alliance','logo':'/static/brands/staralliance.svg','min_level':30,'description':'Réseau mondial, connexions protégées et coopération commerciale.'},
    'oneworld':{'code':'oneworld','name':'oneworld','logo':'/static/brands/oneworld.svg','min_level':30,'description':'Réseau premium, salons et accords de partage de code.'},
}

def wallet_for(db,user_id):
    w=db.get(GameWallet,user_id)
    if not w:
        w=GameWallet(user_id=user_id,tokens=500);db.add(w);db.flush()
    return w

def shop_state(db,u):
    w=wallet_for(db,u.id)
    owned={x.item_code for x in db.scalars(select(ShopEntitlement).where(ShopEntitlement.user_id==u.id)).all()}
    items=[]
    for item in SHOP_ITEMS:
        x=dict(item);x['owned']=x['code'] in owned;items.append(x)
    return {'tokens':w.tokens,'items':items,'payment_mode':'prototype_private','real_money_enabled':False,
            'note':'Les achats de cette build utilisent uniquement les ressources du jeu. Aucun débit bancaire réel.'}

@app.get('/api/shop')
def api_shop(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);out=shop_state(db,u);db.commit();return out

@app.post('/api/shop/purchase')
def api_shop_purchase(req:ShopPurchaseReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);item=next((x for x in SHOP_ITEMS if x['code']==req.item_code),None)
        if not item:raise HTTPException(404,'Article introuvable')
        if db.scalar(select(ShopEntitlement).where(ShopEntitlement.user_id==u.id,ShopEntitlement.item_code==item['code'])):
            raise HTTPException(400,'Article déjà acquis')
        w=wallet_for(db,u.id);tp=int(item.get('token_price') or 0);cp=float(item.get('cash_price') or 0)
        # Packs are bought with tokens in the private prototype; their cash_price is descriptive balancing data.
        if w.tokens<tp:raise HTTPException(400,'Tokens insuffisants')
        w.tokens-=tp
        bonus_cash=float(item.get('bonus_cash') or 0);bonus_tokens=int(item.get('bonus_tokens') or 0)
        if bonus_cash:u.cash+=bonus_cash;log_tx(db,u.id,'shop',f"Boutique · {item['title']}",bonus_cash)
        if bonus_tokens:w.tokens+=bonus_tokens
        db.add(ShopEntitlement(user_id=u.id,item_code=item['code'],item_type=item['type'],acquired_with='tokens'))
        db.commit();return {'ok':True,'tokens':w.tokens,'cash':u.cash,'item_code':item['code'],'bonus_cash':bonus_cash,'bonus_tokens':bonus_tokens}


def player_alliance_payload(db,u):
    member=db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id))
    if not member:return None
    a=db.get(PlayerAlliance,member.alliance_id)
    if not a:return None
    rows=db.scalars(select(PlayerAllianceMember).where(PlayerAllianceMember.alliance_id==a.id).order_by(PlayerAllianceMember.contribution.desc())).all()
    members=[]
    for m in rows:
        mu=db.get(User,m.user_id)
        members.append({'user_id':m.user_id,'username':mu.username if mu else f'Pilote {m.user_id}','company_name':mu.company_name if mu else 'Compagnie','role':m.role,'contribution':m.contribution})
    msgs=db.scalars(select(AllianceMessage).where(AllianceMessage.alliance_id==a.id).order_by(AllianceMessage.created_at.desc()).limit(40)).all()
    chat=[]
    for m in reversed(msgs):
        mu=db.get(User,m.user_id)
        chat.append({'id':m.id,'username':mu.username if mu else 'Membre','message':m.message,'created_at':m.created_at.isoformat() if m.created_at else ''})
    return {'id':a.id,'name':a.name,'tag':a.tag,'role':member.role,'treasury':a.treasury,'xp':a.xp,'members':members,'chat':chat,'member_count':len(members)}

@app.get('/api/alliances')
def api_alliances(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u)
        am=db.scalar(select(AirlineAllianceMembership).where(AirlineAllianceMembership.user_id==u.id))
        airline=[]
        for x in AIRLINE_ALLIANCES.values():
            q=dict(x);q['joined']=bool(am and am.alliance_code==x['code']);q['eligible']=pr['level']>=x['min_level'];airline.append(q)
        publics=[]
        for a in db.scalars(select(PlayerAlliance).order_by(PlayerAlliance.xp.desc(),PlayerAlliance.treasury.desc()).limit(30)).all():
            count=db.scalar(select(func.count()).select_from(PlayerAllianceMember).where(PlayerAllianceMember.alliance_id==a.id)) or 0
            founder=db.get(User,a.founder_user_id)
            publics.append({'id':a.id,'name':a.name,'tag':a.tag,'members':count,'treasury':a.treasury,'xp':a.xp,'founder':founder.username if founder else '—'})
        return {'airline_alliances':airline,'airline_membership':am.alliance_code if am else '',
                'player_alliance':player_alliance_payload(db,u),'public_player_alliances':publics,'level':pr['level']}

@app.post('/api/alliances/airline/join')
def api_airline_alliance_join(req:AirlineAllianceJoinReq,request:Request):
    code=req.alliance_code.lower().strip();cfg=AIRLINE_ALLIANCES.get(code)
    if not cfg:raise HTTPException(404,'Alliance aérienne inconnue')
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u)
        if pr['level']<cfg['min_level']:raise HTTPException(400,f"Niveau {cfg['min_level']} requis")
        row=db.scalar(select(AirlineAllianceMembership).where(AirlineAllianceMembership.user_id==u.id))
        if row:row.alliance_code=code;row.joined_at=now_utc()
        else:db.add(AirlineAllianceMembership(user_id=u.id,alliance_code=code))
        u.reputation=min(100,u.reputation+2);db.commit();return {'ok':True,'alliance':cfg['name']}

@app.post('/api/alliances/player/create')
def api_player_alliance_create(req:PlayerAllianceCreateReq,request:Request):
    name=' '.join(req.name.strip().split())[:80];tag=''.join(ch for ch in req.tag.upper().strip() if ch.isalnum())[:6]
    if len(name)<3 or len(tag)<2:raise HTTPException(400,'Nom ou tag trop court')
    with SessionLocal() as db:
        u=require_user(request,db)
        if db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id)):raise HTTPException(400,'Tu appartiens déjà à une alliance de joueurs')
        if db.scalar(select(PlayerAlliance).where((PlayerAlliance.name==name)|(PlayerAlliance.tag==tag))):raise HTTPException(400,'Nom ou tag déjà utilisé')
        fee=500_000
        if u.cash<fee:raise HTTPException(400,'500 000 € sont nécessaires pour créer une alliance')
        u.cash-=fee;a=PlayerAlliance(name=name,tag=tag,founder_user_id=u.id);db.add(a);db.flush();db.add(PlayerAllianceMember(alliance_id=a.id,user_id=u.id,role='founder'));log_tx(db,u.id,'alliance',f'Création alliance {name}',-fee);db.commit();return {'ok':True,'alliance_id':a.id}

@app.post('/api/alliances/player/join')
def api_player_alliance_join(req:PlayerAllianceJoinReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db)
        if db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id)):raise HTTPException(400,'Tu appartiens déjà à une alliance')
        a=db.get(PlayerAlliance,req.alliance_id)
        if not a:raise HTTPException(404,'Alliance introuvable')
        count=db.scalar(select(func.count()).select_from(PlayerAllianceMember).where(PlayerAllianceMember.alliance_id==a.id)) or 0
        if count>=50:raise HTTPException(400,'Alliance complète')
        db.add(PlayerAllianceMember(alliance_id=a.id,user_id=u.id,role='member'));db.commit();return {'ok':True}

@app.post('/api/alliances/player/leave')
def api_player_alliance_leave(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);m=db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id))
        if not m:raise HTTPException(400,'Aucune alliance')
        a=db.get(PlayerAlliance,m.alliance_id)
        if m.role=='founder':
            count=db.scalar(select(func.count()).select_from(PlayerAllianceMember).where(PlayerAllianceMember.alliance_id==a.id)) or 0
            if count>1:raise HTTPException(400,'Le fondateur doit rester tant que d’autres membres sont présents')
            db.execute(delete(AllianceMessage).where(AllianceMessage.alliance_id==a.id));db.delete(m);db.delete(a)
        else:db.delete(m)
        db.commit();return {'ok':True}

@app.post('/api/alliances/player/contribute')
def api_player_alliance_contribute(req:PlayerAllianceContributionReq,request:Request):
    amount=round(max(0,min(50_000_000,float(req.amount))),2)
    if amount<10_000:raise HTTPException(400,'Contribution minimale : 10 000 €')
    with SessionLocal() as db:
        u=require_user(request,db);m=db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id))
        if not m:raise HTTPException(400,'Aucune alliance')
        if u.cash<amount:raise HTTPException(400,'Fonds insuffisants')
        a=db.get(PlayerAlliance,m.alliance_id);u.cash-=amount;m.contribution+=amount;a.treasury+=amount;a.xp+=int(amount/5000);log_tx(db,u.id,'alliance',f'Contribution alliance {a.name}',-amount);db.commit();return {'ok':True,'treasury':a.treasury,'xp':a.xp}

@app.post('/api/alliances/chat')
def api_alliance_chat(req:AllianceChatReq,request:Request):
    msg=' '.join(req.message.strip().split())[:500]
    if not msg:raise HTTPException(400,'Message vide')
    with SessionLocal() as db:
        u=require_user(request,db);m=db.scalar(select(PlayerAllianceMember).where(PlayerAllianceMember.user_id==u.id))
        if not m:raise HTTPException(400,'Rejoins une alliance de joueurs pour utiliser le chat')
        db.add(AllianceMessage(alliance_id=m.alliance_id,user_id=u.id,message=msg));db.commit();return {'ok':True}

@app.get('/api/live-traffic/world-seed')
def api_live_traffic_world_seed(request:Request,limit_per_hub:int=45):
    """Small real-traffic sample around owned hubs so aircraft are visible at globe launch.
    It deliberately avoids a full-world FR24 query to keep API credits and server memory under control.
    """
    limit_per_hub=max(15,min(60,limit_per_hub))
    with SessionLocal() as db:
        u=require_user(request,db);hubs=user_hubs(db,u)[:4]
    if not hubs:return {'source':'none','states':[],'hubs':[]}
    provider='Flightradar24 API' if _fr24_token() else 'OpenSky';states=[];seen=set();hub_codes=[];fr24_mode=''
    for h in hubs:
        a=airport_detail(h.airport_ident)
        if not a:continue
        hub_codes.append(a['code']);span=.55 if a['type']=='large_airport' else .38
        try:
            if _fr24_token():
                bounds=f"{a['lat']+span},{a['lat']-span},{a['lon']-span},{a['lon']+span}";rows,mode=_fetch_fr24(bounds,limit_per_hub,a);fr24_mode=mode
            else:rows=_opensky_hub(a,span)
        except Exception:continue
        for x in rows:
            key=x.get('id') or x.get('fr24_id') or f"{x.get('callsign')}:{round(x.get('lat',0),3)}:{round(x.get('lon',0),3)}"
            if key in seen:continue
            seen.add(key);states.append(x)
    return {'source':provider,'states':states[:220],'hubs':hub_codes,'real_only':True,'fr24_mode':fr24_mode,'configured':bool(_fr24_token())}

class ResearchUpgradeReq(BaseModel):
    code:str

@app.get('/api/research')
def api_research(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u);levels=research_levels(db,u.id);items=[]
        for code,cfg in RESEARCH_PROJECTS.items():
            lvl=levels.get(code,0);price=int(cfg['base_cost']*(1.65**lvl));items.append({'code':code,**cfg,'level':lvl,'price':price,'available':pr['level']>=cfg['min_level'],'maxed':lvl>=cfg['max']})
        return {'level':pr['level'],'items':items,'fuel_cost_factor':research_cost_factor(db,u.id,{'description':'L2J','category':'Jet'}),'turboprop_cost_factor':research_cost_factor(db,u.id,{'description':'L2T','category':'Turbopropulseur'})}

@app.post('/api/research/upgrade')
def api_research_upgrade(req:ResearchUpgradeReq,request:Request):
    cfg=RESEARCH_PROJECTS.get(req.code)
    if not cfg:raise HTTPException(404,'Projet R&D inconnu')
    with SessionLocal() as db:
        u=require_user(request,db);pr=career_progress(db,u)
        if pr['level']<cfg['min_level']:raise HTTPException(400,f"Niveau {cfg['min_level']} requis")
        row=db.scalar(select(CompanyResearch).where(CompanyResearch.user_id==u.id,CompanyResearch.code==req.code))
        if not row:row=CompanyResearch(user_id=u.id,code=req.code,level=0);db.add(row);db.flush()
        if row.level>=cfg['max']:raise HTTPException(400,'Niveau maximum atteint')
        price=int(cfg['base_cost']*(1.65**row.level))
        if u.cash<price:raise HTTPException(400,'Fonds insuffisants')
        u.cash-=price;row.level+=1;row.updated_at=now_utc();log_tx(db,u.id,'research',f"R&D · {cfg['name']} niv. {row.level}",-price);db.commit();return {'ok':True,'level':row.level,'price':price}

# -------- v1.1 HR automation & IPO --------
class HRPolicyReq(BaseModel):
    enabled:bool=True
    monthly_budget:float=9_000_000
    target_buffer_percent:int=15

class IPOReq(BaseModel):
    equity_percent:float=15.0
    ticker:str='SKY'

@app.get('/api/hr/policy')
def api_hr_policy(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);p=hr_policy_for(db,u.id);targets=hr_targets(db,u.id)
        payroll=db.scalar(select(func.sum(Employee.salary_monthly)).where(Employee.user_id==u.id)) or 0
        db.commit()
        return {'enabled':p.enabled,'monthly_budget':p.monthly_budget,'target_buffer_percent':p.target_buffer_percent,
                'last_autohire_at':p.last_autohire_at.isoformat() if p.last_autohire_at else None,
                'payroll':round(payroll,2),'targets':targets}

@app.post('/api/hr/policy')
def api_hr_policy_update(req:HRPolicyReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);p=hr_policy_for(db,u.id);p.enabled=bool(req.enabled);p.monthly_budget=max(100_000,min(250_000_000,float(req.monthly_budget)));p.target_buffer_percent=max(0,min(50,int(req.target_buffer_percent)));p.updated_at=now_utc();db.commit()
        return {'ok':True,'enabled':p.enabled,'monthly_budget':p.monthly_budget,'target_buffer_percent':p.target_buffer_percent}

@app.post('/api/hr/auto-balance')
def api_hr_auto_balance(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);out=auto_balance_hr(db,u,force=True,max_hires=36);db.commit();out['targets']=hr_targets(db,u.id);return out


def ipo_snapshot(db,u):
    pr=career_progress(db,u);fleet=db.scalar(select(func.count()).select_from(Aircraft).where(Aircraft.user_id==u.id)) or 0
    hubs=db.scalar(select(func.count()).select_from(UserHub).where(UserHub.user_id==u.id)) or 0
    profitable=db.scalar(select(func.count()).select_from(FlightRecord).where(FlightRecord.user_id==u.id,FlightRecord.profit>0)) or 0
    flights=db.scalar(select(func.count()).select_from(FlightRecord).where(FlightRecord.user_id==u.id)) or 0
    profit=db.scalar(select(func.sum(FlightRecord.profit)).where(FlightRecord.user_id==u.id)) or 0
    # Management-game valuation; deliberately transparent and deterministic.
    valuation=max(50_000_000,u.cash*1.8+fleet*7_500_000+hubs*24_000_000+max(0,profit)*7+u.reputation*2_500_000)
    profit_ratio=profitable/max(1,flights)
    reqs={
        'level':{'label':'Niveau compagnie','value':pr['level'],'target':50,'ok':pr['level']>=50},
        'fleet':{'label':'Flotte','value':fleet,'target':25,'ok':fleet>=25},
        'hubs':{'label':'Hubs','value':hubs,'target':3,'ok':hubs>=3},
        'rotations':{'label':'Rotations','value':flights,'target':250,'ok':flights>=250},
        'reputation':{'label':'Réputation','value':u.reputation,'target':75,'ok':u.reputation>=75},
        'profitability':{'label':'Vols rentables','value':round(profit_ratio*100),'target':65,'ok':profit_ratio>=.65},
    }
    state=db.get(IPOState,u.id)
    return {'valuation':round(valuation,2),'requirements':reqs,'eligible':all(x['ok'] for x in reqs.values()),
            'is_public':bool(state and state.is_public),'ticker':state.ticker if state else '',
            'equity_sold_percent':state.equity_sold_percent if state else 0,'cash_raised':state.cash_raised if state else 0,
            'share_price':state.share_price if state else 0,'market_confidence':state.market_confidence if state else min(95,max(35,45+u.reputation*.45+profit_ratio*15))}

@app.get('/api/ipo')
def api_ipo(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);return ipo_snapshot(db,u)

@app.post('/api/ipo/launch')
def api_ipo_launch(req:IPOReq,request:Request):
    pct=max(5,min(35,float(req.equity_percent)));ticker=''.join(ch for ch in req.ticker.upper() if ch.isalnum())[:6] or 'SKY'
    with SessionLocal() as db:
        u=require_user(request,db);snap=ipo_snapshot(db,u)
        if snap['is_public']:raise HTTPException(400,'La compagnie est déjà cotée')
        if not snap['eligible']:
            missing=', '.join(x['label'] for x in snap['requirements'].values() if not x['ok'])
            raise HTTPException(400,'Prérequis IPO manquants : '+missing)
        raised=snap['valuation']*(pct/100)*.94;shares=10_000_000;price=snap['valuation']/shares
        row=db.get(IPOState,u.id)
        if not row:row=IPOState(user_id=u.id);db.add(row)
        row.is_public=True;row.ticker=ticker;row.equity_sold_percent=pct;row.cash_raised=raised;row.share_price=price;row.market_confidence=snap['market_confidence'];row.launched_at=now_utc();row.updated_at=now_utc();u.cash+=raised
        log_tx(db,u.id,'ipo',f'Introduction en Bourse {ticker} · {pct:.0f}% du capital',raised);db.commit()
        return {'ok':True,'ticker':ticker,'equity_percent':pct,'cash_raised':raised,'share_price':price,'valuation':snap['valuation']}

class OfficialLiveryReq(BaseModel):
    livery_code:str

@app.post('/api/aircraft/{aircraft_id}/livery/official')
def api_aircraft_official_livery(aircraft_id:int,req:OfficialLiveryReq,request:Request):
    code=req.livery_code.strip().lower()
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        if code=='airfrance':
            if not db.scalar(select(ShopEntitlement).where(ShopEntitlement.user_id==u.id,ShopEntitlement.item_code=='livery_airfrance')):
                raise HTTPException(403,'Pack livrée Air France non acquis dans la boutique')
            if not a.type_icao.upper().startswith('A35'):
                raise HTTPException(400,'Cette livrée de démonstration est actuellement disponible sur A350 uniquement')
            a.livery_primary='#071b3c';a.livery_secondary='#f6f7f8';a.livery_accent='#d81f2a';a.livery_template='official_airfrance';a.livery_name='Air France · officielle'
            d=livery_detail_for(db,u.id,a);d.tail_color='#071b3c';d.engine_color='#f6f7f8';d.belly_color='#e8ebee';d.nose_color='#f6f7f8';d.stripe_style='official_airfrance'
            db.commit();return {'ok':True,'livery_name':a.livery_name,'preview':'/static/liveries/airfrance-a350.jpg'}
        raise HTTPException(404,'Livrée officielle inconnue')
