import os, math, json, base64, hashlib, hmac, secrets, time
from datetime import datetime, timezone
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

from models import Base, User, CompanyProfile, UserHub, HubUpgrade, Aircraft, Route
from catalog import (
    search_airports, airport_detail, major_airports, search_aircraft, aircraft_detail,
    aircraft_manufacturers, search_airlines, longest_runway_m
)
from logic import (
    UPGRADES, UPGRADE_BY_CODE, SIM_SPEED, upgrade_price, hub_level, destination_point,
    route_simulation, economy_per_leg, haversine_km, now_utc
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

app=FastAPI(title='SKYLINE AIRWAYS',version='0.4')
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

def settle_economy(db,u):
    now=now_utc();last=u.last_settled
    if last is None:last=now
    if last.tzinfo is None:last=last.replace(tzinfo=timezone.utc)
    dt=max(0,min((now-last).total_seconds(),60*60*24))
    if dt<3:return
    routes=db.scalars(select(Route).where(Route.user_id==u.id)).all()
    aircraft={a.id:a for a in db.scalars(select(Aircraft).where(Aircraft.user_id==u.id)).all()}
    gain=0
    for r in routes:
        a=aircraft.get(r.aircraft_id)
        if not a:continue
        spec=spec_for_aircraft(a);o=airport_for_code(r.origin);d=airport_for_code(r.destination)
        if not o or not d:continue
        sim=route_simulation(r.created_at,o,d,spec)
        econ=economy_per_leg(o,d,spec,u.reputation)
        cycle_h=sim['cycle_minutes']/60
        legs_per_sim_hour=2/max(.2,cycle_h)
        sim_hours=dt*SIM_SPEED/3600
        gain += econ['profit']*legs_per_sim_hour*sim_hours
    if gain:u.cash += gain
    u.last_settled=now;db.commit()

# -------- Page routes --------
@app.get('/health')
def health():return {'status':'ok','version':'0.4','catalog':'85k+ airports / 591 aircraft types'}

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

# -------- Catalog APIs --------
@app.get('/api/airports/search')
def api_airport_search(q:str='',limit:int=30):return search_airports(q,limit=limit)

@app.get('/api/airports/major')
def api_airports_major(limit:int=2200):return major_airports(limit)

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
        u.cash-=price;u.hub_code=a['code']
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
        return {'airport':a,'hub':{'level':lvl,'is_primary':h.is_primary},'nodes':nodes,'own_ground_aircraft':own,'traffic_density':density}

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
        row.level+=1;u.cash-=price
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
        u.cash-=price;db.add(a);db.commit();return {'ok':True,'tail':tail,'id':a.id}

@app.post('/api/aircraft/{aircraft_id}/livery')
def api_aircraft_livery(aircraft_id:int,req:LiveryReq,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db);a=db.get(Aircraft,aircraft_id)
        if not a or a.user_id!=u.id:raise HTTPException(404,'Avion introuvable')
        a.livery_primary=req.primary[:16];a.livery_secondary=req.secondary[:16];a.livery_accent=req.accent[:16];a.livery_template=req.template[:32];a.livery_name=req.name[:80]
        db.commit();return {'ok':True}

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
                hub_out.append({'ident':h.airport_ident,'is_primary':h.is_primary,'level':hub_level(levels),'airport':{'ident':a['ident'],'code':a['code'],'name':a['name'],'lat':a['lat'],'lon':a['lon'],'type':a['type'],'country':a['country'],'municipality':a['municipality']}})
        acs=db.scalars(select(Aircraft).where(Aircraft.user_id==u.id).order_by(Aircraft.id)).all()
        routes=db.scalars(select(Route).where(Route.user_id==u.id).order_by(Route.id)).all();route_by_ac={r.aircraft_id:r for r in routes}
        aircraft=[serialize_aircraft(a,route_by_ac.get(a.id)) for a in acs]
        route_out=[]
        for r in routes:
            a=next((x for x in acs if x.id==r.aircraft_id),None)
            if not a:continue
            s=serialize_aircraft(a,r);o=airport_for_code(r.origin);d=airport_for_code(r.destination);econ=economy_per_leg(o,d,s['spec'],u.reputation) if o and d else None
            partner=None
            if r.commercial_destination:
                cd=airport_detail(r.commercial_destination)
                if cd:partner={'from':d['code'],'to':cd['code'],'from_lat':d['lat'],'from_lon':d['lon'],'to_lat':cd['lat'],'to_lon':cd['lon'],'airline':r.partner_airline,'aircraft':r.partner_aircraft}
            route_out.append({'id':r.id,'aircraft_id':a.id,'tail':a.tail,'model':s['spec']['name'],'origin':r.origin,'destination':r.destination,'commercial_destination':r.commercial_destination,'via':r.via,'frequency':r.frequency,'flight':s['flight'],'economy':econ,'partner':partner,
                              'origin_airport':o,'destination_airport':d})
        return {'user':{'username':u.username,'company_name':u.company_name,'cash':round(u.cash,2),'reputation':u.reputation},
                'profile':{'primary_color':p.primary_color,'secondary_color':p.secondary_color,'accent_color':p.accent_color,'logo_text':p.logo_text,'logo_data':p.logo_data,'livery_template':p.livery_template},
                'hubs':hub_out,'aircraft':aircraft,'routes':route_out,'sim_speed':SIM_SPEED}

# -------- Weather / live traffic --------
_weather_cache={}
_traffic_cache={}

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

_surface_cache={}

def _fallback_surface_network(a):
    features=[]
    for r in a.get('runways',[]):
        if r.get('le_lon') is None or r.get('he_lon') is None:
            continue
        features.append({
            'type':'Feature',
            'geometry':{'type':'LineString','coordinates':[[r['le_lon'],r['le_lat']],[r['he_lon'],r['he_lat']]]},
            'properties':{'kind':'runway','name':(r.get('le_ident') or '')+' / '+(r.get('he_ident') or ''),'source':'OurAirports'}
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
    span={'large_airport':.060,'medium_airport':.045,'small_airport':.028,'heliport':.018}.get(a['type'],.03)
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
                features.append({'type':'Feature','geometry':geom,'properties':{'kind':kind or 'aeroway','name':tags.get('ref') or tags.get('name') or '', 'surface':tags.get('surface') or '', 'source':'OpenStreetMap'}})
            elif e.get('type')=='node':
                tags=e.get('tags') or {};kind=tags.get('aeroway')
                if kind in ('gate','parking_position') and e.get('lon') is not None:
                    features.append({'type':'Feature','geometry':{'type':'Point','coordinates':[e['lon'],e['lat']]},'properties':{'kind':kind,'name':tags.get('ref') or tags.get('name') or '', 'source':'OpenStreetMap'}})
        if features:out={'type':'FeatureCollection','features':features,'source':'OpenStreetMap / Overpass'}
    except Exception:
        out=None
    if not out:out=_fallback_surface_network(a)
    _surface_cache[a['ident']]=(now,out)
    return out

@app.post('/api/reset-career')
def api_reset(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db)
        db.execute(delete(Route).where(Route.user_id==u.id));db.execute(delete(Aircraft).where(Aircraft.user_id==u.id));db.execute(delete(HubUpgrade).where(HubUpgrade.user_id==u.id));db.execute(delete(UserHub).where(UserHub.user_id==u.id))
        u.cash=180_000_000;u.reputation=50;u.hub_code='';u.last_settled=now_utc();db.commit();return {'ok':True}
