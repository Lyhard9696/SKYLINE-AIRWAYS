import os, math, json, base64, hashlib, hmac, secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from itsdangerous import URLSafeSerializer, BadSignature
from sqlalchemy import create_engine, String, Integer, Float, DateTime, ForeignKey, Text, select, delete
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(APP_DIR, 'skyline.db')}")
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-' + secrets.token_hex(24))
SIM_SPEED = 240.0  # simulated seconds per real second

connect_args = {'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    company_name: Mapped[str] = mapped_column(String(120))
    hub_code: Mapped[str] = mapped_column(String(8), default='CDG')
    cash: Mapped[float] = mapped_column(Float, default=90_000_000)
    reputation: Mapped[int] = mapped_column(Integer, default=50)
    last_settled: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Aircraft(Base):
    __tablename__ = 'aircraft'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    model_code: Mapped[str] = mapped_column(String(32))
    tail: Mapped[str] = mapped_column(String(24))
    acquisition: Mapped[str] = mapped_column(String(16), default='buy')
    condition: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class HubUpgrade(Base):
    __tablename__ = 'hub_upgrades'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    level: Mapped[int] = mapped_column(Integer, default=0)

class Route(Base):
    __tablename__ = 'routes'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    aircraft_id: Mapped[int] = mapped_column(ForeignKey('aircraft.id'), index=True)
    origin: Mapped[str] = mapped_column(String(8))
    destination: Mapped[str] = mapped_column(String(8))
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)

AIRPORTS = {
    'CDG': {'name':'Paris Charles de Gaulle','lat':49.0097,'lon':2.5479,'country':'France','demand':1.00},
    'LHR': {'name':'London Heathrow','lat':51.4700,'lon':-0.4543,'country':'Royaume-Uni','demand':0.98},
    'AMS': {'name':'Amsterdam Schiphol','lat':52.3105,'lon':4.7683,'country':'Pays-Bas','demand':0.84},
    'FRA': {'name':'Frankfurt','lat':50.0379,'lon':8.5622,'country':'Allemagne','demand':0.88},
    'MAD': {'name':'Madrid Barajas','lat':40.4983,'lon':-3.5676,'country':'Espagne','demand':0.76},
    'FCO': {'name':'Rome Fiumicino','lat':41.8003,'lon':12.2389,'country':'Italie','demand':0.72},
    'LIS': {'name':'Lisbon Humberto Delgado','lat':38.7742,'lon':-9.1342,'country':'Portugal','demand':0.62},
    'IST': {'name':'Istanbul','lat':41.2753,'lon':28.7519,'country':'Turquie','demand':0.90},
    'DXB': {'name':'Dubai International','lat':25.2532,'lon':55.3657,'country':'Émirats arabes unis','demand':0.96},
    'DOH': {'name':'Doha Hamad','lat':25.2731,'lon':51.6081,'country':'Qatar','demand':0.78},
    'JFK': {'name':'New York JFK','lat':40.6413,'lon':-73.7781,'country':'États-Unis','demand':1.00},
    'YUL': {'name':'Montréal Trudeau','lat':45.4706,'lon':-73.7408,'country':'Canada','demand':0.74},
    'YOW': {'name':'Ottawa','lat':45.3225,'lon':-75.6692,'country':'Canada','demand':0.43},
    'LAX': {'name':'Los Angeles','lat':33.9416,'lon':-118.4085,'country':'États-Unis','demand':0.92},
    'GRU': {'name':'São Paulo Guarulhos','lat':-23.4356,'lon':-46.4731,'country':'Brésil','demand':0.82},
    'HND': {'name':'Tokyo Haneda','lat':35.5494,'lon':139.7798,'country':'Japon','demand':0.96},
    'SIN': {'name':'Singapore Changi','lat':1.3644,'lon':103.9915,'country':'Singapour','demand':0.89},
    'JNB': {'name':'Johannesburg OR Tambo','lat':-26.1337,'lon':28.2420,'country':'Afrique du Sud','demand':0.62},
    'IKA': {'name':'Tehran Imam Khomeini','lat':35.4161,'lon':51.1522,'country':'Iran','demand':0.45},
    'SVO': {'name':'Moscow Sheremetyevo','lat':55.9726,'lon':37.4146,'country':'Russie','demand':0.58},
}

AIRCRAFT_CATALOG = {
    'ATR72': {'name':'ATR 72-600','price':24_000_000,'lease':3_600_000,'seats':72,'range':1528,'speed':510,'category':'Régional'},
    'A220': {'name':'Airbus A220-300','price':50_000_000,'lease':7_000_000,'seats':145,'range':6700,'speed':829,'category':'Court / moyen-courrier'},
    'A320N': {'name':'Airbus A320neo','price':58_000_000,'lease':8_000_000,'seats':180,'range':6300,'speed':830,'category':'Moyen-courrier'},
    'A321N': {'name':'Airbus A321neo','price':72_000_000,'lease':9_500_000,'seats':220,'range':7400,'speed':830,'category':'Moyen / long-courrier'},
    'B38M': {'name':'Boeing 737 MAX 8','price':60_000_000,'lease':8_200_000,'seats':178,'range':6570,'speed':842,'category':'Moyen-courrier'},
    'A339': {'name':'Airbus A330-900','price':120_000_000,'lease':15_000_000,'seats':287,'range':13334,'speed':871,'category':'Long-courrier'},
    'B789': {'name':'Boeing 787-9','price':155_000_000,'lease':18_500_000,'seats':296,'range':14140,'speed':903,'category':'Long-courrier'},
    'A359': {'name':'Airbus A350-900','price':180_000_000,'lease':21_000_000,'seats':325,'range':15500,'speed':903,'category':'Long-courrier'},
}

# x/y are positions on the aerial hub image (0..1000 / 0..700)
HUB_NODES = [
    {'code':'GATE_A2','name':'Porte A2','cat':'Portes','max':1,'cost':2_000_000,'x':500,'y':390,'desc':'Deuxième porte au contact.','prereq':None},
    {'code':'GATE_A34','name':'Portes A3–A4','cat':'Portes','max':1,'cost':4_500_000,'x':560,'y':360,'desc':'Deux nouvelles portes au contact.','prereq':'GATE_A2'},
    {'code':'GATE_A58','name':'Portes A5–A8','cat':'Portes','max':1,'cost':9_000_000,'x':620,'y':330,'desc':'Quatre portes supplémentaires.','prereq':'GATE_A34'},
    {'code':'WIDEBODY','name':'Zone gros-porteurs','cat':'Portes','max':4,'cost':12_000_000,'x':720,'y':300,'desc':'Postes compatibles A330/A350/787.','prereq':'GATE_A58'},
    {'code':'REMOTE','name':'Parkings avions éloignés','cat':'Portes','max':8,'cost':2_500_000,'x':760,'y':420,'desc':'Stands au large avec bus.','prereq':'GATE_A34'},
    {'code':'CAR_PARK_SHORT','name':'Parking courte durée','cat':'Accès','max':10,'cost':700_000,'x':350,'y':610,'desc':'Capacité visiteurs et revenus parking.','prereq':None},
    {'code':'CAR_PARK_LONG','name':'Parking longue durée','cat':'Accès','max':10,'cost':1_200_000,'x':270,'y':640,'desc':'Parking longue durée et navettes.','prereq':'CAR_PARK_SHORT'},
    {'code':'CAR_PARK_PREM','name':'Parking premium','cat':'Accès','max':10,'cost':1_800_000,'x':440,'y':640,'desc':'Voiturier et clientèle premium.','prereq':'CAR_PARK_SHORT'},
    {'code':'GROUND_TRANSIT','name':'Hub transports terrestres','cat':'Accès','max':8,'cost':3_000_000,'x':525,'y':620,'desc':'Bus, taxis, navettes et intermodalité.','prereq':None},
    {'code':'SECURITY','name':'Sûreté terminal','cat':'Sécurité','max':10,'cost':1_000_000,'x':430,'y':470,'desc':'Scanners, lignes de contrôle et personnel.','prereq':None},
    {'code':'BORDER','name':'Police aux frontières','cat':'Sécurité','max':10,'cost':1_400_000,'x':480,'y':455,'desc':'Guichets, e-gates et flux internationaux.','prereq':'SECURITY'},
    {'code':'CUSTOMS','name':'Douanes','cat':'Sécurité','max':8,'cost':1_200_000,'x':530,'y':455,'desc':'Contrôles douaniers et arrivées internationales.','prereq':'BORDER'},
    {'code':'FIRE','name':'Pompiers aéroportuaires','cat':'Sécurité','max':8,'cost':3_500_000,'x':170,'y':400,'desc':'ARFF, véhicules et temps de réponse.','prereq':None},
    {'code':'MEDICAL','name':'Centre médical','cat':'Sécurité','max':8,'cost':2_000_000,'x':210,'y':450,'desc':'Urgences passagers et opérations.','prereq':None},
    {'code':'TOILETS','name':'Toilettes & sanitaires','cat':'Passagers','max':10,'cost':450_000,'x':405,'y':500,'desc':'Capacité, propreté, PMR et maintenance.','prereq':None},
    {'code':'BAGGAGE','name':'Système bagages','cat':'Passagers','max':10,'cost':2_200_000,'x':580,'y':510,'desc':'Tri, correspondances et fiabilité.','prereq':None},
    {'code':'DUTYFREE','name':'Duty Free','cat':'Commercial','max':10,'cost':1_500_000,'x':460,'y':520,'desc':'Surface commerciale et revenus annexes.','prereq':None},
    {'code':'FOOD','name':'Restauration','cat':'Commercial','max':10,'cost':1_200_000,'x':510,'y':530,'desc':'Cafés, restaurants et expérience passager.','prereq':None},
    {'code':'RETAIL','name':'Galerie commerciale','cat':'Commercial','max':10,'cost':2_500_000,'x':545,'y':540,'desc':'Boutiques, luxe et services.','prereq':'DUTYFREE'},
    {'code':'LOUNGE_BIZ','name':'Lounge Business','cat':'Premium','max':10,'cost':2_000_000,'x':635,'y':480,'desc':'Salon Business, douches et restauration.','prereq':None},
    {'code':'LOUNGE_FIRST','name':'Lounge First','cat':'Premium','max':10,'cost':4_000_000,'x':680,'y':470,'desc':'Expérience First / flagship.','prereq':'LOUNGE_BIZ'},
    {'code':'CATERING','name':'Centre catering','cat':'Opérations','max':10,'cost':2_500_000,'x':230,'y':330,'desc':'Préparation du service à bord.','prereq':None},
    {'code':'CABIN_SERVICE','name':'Service à bord','cat':'Opérations','max':10,'cost':1_800_000,'x':280,'y':350,'desc':'Qualité cabine, chargement et coordination.','prereq':'CATERING'},
    {'code':'MAINT','name':'Maintenance','cat':'Opérations','max':10,'cost':4_000_000,'x':170,'y':300,'desc':'Hangars, ateliers, stocks et disponibilité flotte.','prereq':None},
    {'code':'FUEL','name':'Dépôt carburant','cat':'Opérations','max':10,'cost':3_000_000,'x':830,'y':530,'desc':'Capacité de ravitaillement et débit.','prereq':None},
    {'code':'DEICING','name':'Dégivrage','cat':'Opérations','max':8,'cost':2_000_000,'x':820,'y':360,'desc':'Capacité hiver et régularité.','prereq':None},
    {'code':'CREW','name':'Centre équipages','cat':'Personnel','max':10,'cost':2_200_000,'x':310,'y':500,'desc':'Briefing, repos, rotations et fatigue.','prereq':None},
    {'code':'OPS','name':'Operations Control Center','cat':'OPS','max':10,'cost':4_500_000,'x':315,'y':410,'desc':'NOTAM, dispatch, recovery et automatisation.','prereq':None},
    {'code':'CARGO','name':'Terminal cargo','cat':'Cargo','max':10,'cost':5_000_000,'x':865,'y':430,'desc':'Fret, entrepôts et handling cargo.','prereq':None},
    {'code':'HOTEL','name':'Hôtel & repos','cat':'Passagers','max':8,'cost':3_000_000,'x':375,'y':660,'desc':'Passagers perturbés et équipages.','prereq':'GROUND_TRANSIT'},
]

NOTAMS = [
    {'severity':'warning','airport':'LHR','title':'RWY 27R indisponible sur créneau nocturne','effect':'Capacité réduite / retards possibles'},
    {'severity':'danger','airport':'YUL','title':'Scénario OPS : fermeture destination','effect':'Alternate YOW recommandé pour démonstration'},
]

serializer = URLSafeSerializer(SECRET_KEY, salt='skyline-session')
app = FastAPI(title='SKYLINE AIRWAYS')
app.mount('/static', StaticFiles(directory=os.path.join(APP_DIR,'static')), name='static')
templates = Jinja2Templates(directory=os.path.join(APP_DIR,'templates'))


def utcnow(): return datetime.now(timezone.utc)

def pw_hash(password:str)->str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 260_000)
    return base64.b64encode(salt).decode()+'.'+base64.b64encode(dk).decode()

def pw_verify(password:str, stored:str)->bool:
    try:
        s,d = stored.split('.',1)
        salt=base64.b64decode(s); expected=base64.b64decode(d)
        got=hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 260_000)
        return hmac.compare_digest(got, expected)
    except Exception: return False

def current_user(request:Request, db)->Optional[User]:
    token=request.cookies.get('skyline_session')
    if not token: return None
    try: uid=int(serializer.loads(token).get('uid'))
    except (BadSignature,TypeError,ValueError): return None
    return db.get(User, uid)

def require_user(request:Request, db)->User:
    u=current_user(request,db)
    if not u: raise HTTPException(401,'Non connecté')
    return u

def set_auth_cookie(resp, user_id:int):
    token=serializer.dumps({'uid':user_id})
    resp.set_cookie('skyline_session',token,max_age=60*60*24*30,httponly=True,samesite='lax',secure=os.getenv('COOKIE_SECURE','0')=='1')

def hav_km(a,b):
    R=6371.0
    p1,p2=math.radians(a['lat']),math.radians(b['lat'])
    dp=math.radians(b['lat']-a['lat']); dl=math.radians(b['lon']-a['lon'])
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def get_upgrade_levels(db,user_id):
    rows=db.scalars(select(HubUpgrade).where(HubUpgrade.user_id==user_id)).all()
    return {r.code:r.level for r in rows}

def hub_level(levels):
    score=sum(levels.values())
    return max(1,min(12,1+score//12))

def stage_for(level):
    if level<=2:return 1
    if level<=5:return 4
    if level<=9:return 8
    return 12

def node_cost(node, level):
    return int(node['cost']*(1.0+0.36*level))

def route_operational_check(origin,dest,model=None):
    if dest=='SVO':
        return {'ok':False,'reason':'Route réglementairement indisponible dans le scénario opérationnel actuel.','alternative':None}
    if origin=='CDG' and dest=='IKA':
        return {'ok':False,'reason':'Service direct indisponible dans ce scénario.','alternative':{'via':'IST','text':'CDG → IST (Skyline), puis IST → IKA (partenaire)'}}
    if model:
        d=hav_km(AIRPORTS[origin],AIRPORTS[dest])
        if d>AIRCRAFT_CATALOG[model]['range']*0.93:
            return {'ok':False,'reason':f"Autonomie insuffisante : {int(d)} km pour {AIRCRAFT_CATALOG[model]['name']}", 'alternative':None}
    return {'ok':True,'reason':'Route exploitable dans le scénario.','alternative':None}

def route_metrics(r:Route, ac:Aircraft):
    a,b=AIRPORTS[r.origin],AIRPORTS[r.destination]
    cat=AIRCRAFT_CATALOG[ac.model_code]
    dist=hav_km(a,b)
    duration_h=max(0.65,dist/cat['speed']*1.10+0.35)
    ground_h=0.55
    created=r.created_at
    if created.tzinfo is None: created=created.replace(tzinfo=timezone.utc)
    elapsed=(utcnow()-created).total_seconds()*SIM_SPEED
    leg_s=duration_h*3600; ground_s=ground_h*3600; cycle=2*(leg_s+ground_s)
    phase=elapsed%cycle
    if phase<leg_s:
        status='En vol'; direction='out'; progress=phase/leg_s
        orig,dest=r.origin,r.destination
    elif phase<leg_s+ground_s:
        status=f"Au sol {r.destination}"; direction='ground_dest'; progress=1.0; orig,dest=r.origin,r.destination
    elif phase<2*leg_s+ground_s:
        status='En vol'; direction='back'; progress=(phase-(leg_s+ground_s))/leg_s
        orig,dest=r.destination,r.origin
    else:
        status=f"Au sol {r.origin}"; direction='ground_orig'; progress=0.0; orig,dest=r.origin,r.destination
    load=0.78+0.12*AIRPORTS[r.destination]['demand']
    revenue=dist*cat['seats']*0.095*load
    costs=dist*cat['seats']*0.058 + 2200
    profit=max(1200,revenue-costs)
    return {'distance_km':round(dist),'duration_h':round(duration_h,2),'status':status,'direction':direction,'progress':progress,'from':orig,'to':dest,'profit_leg':round(profit)}

def settle_economy(db,u:User):
    now=utcnow()
    last=u.last_settled
    if last is None:
        u.last_settled=now; db.commit(); return
    if last.tzinfo is None: last=last.replace(tzinfo=timezone.utc)
    dt=max(0,min(3600,(now-last).total_seconds()))
    if dt<3:return
    routes=db.scalars(select(Route).where(Route.user_id==u.id)).all()
    acs={a.id:a for a in db.scalars(select(Aircraft).where(Aircraft.user_id==u.id)).all()}
    gain=0
    for r in routes:
        ac=acs.get(r.aircraft_id)
        if not ac:continue
        m=route_metrics(r,ac)
        sim_hours=dt*SIM_SPEED/3600
        legs_per_sim_hour=1/(m['duration_h']+0.55)
        gain += m['profit_leg']*legs_per_sim_hour*sim_hours
    if gain:
        u.cash += gain
    u.last_settled=now
    db.commit()

@app.get('/health')
def health(): return {'status':'ok','version':'0.3'}

@app.get('/', response_class=HTMLResponse)
def root(request:Request):
    with SessionLocal() as db:
        u=current_user(request,db)
        if u:return RedirectResponse('/game',303)
    return RedirectResponse('/login',303)

@app.get('/login', response_class=HTMLResponse)
def login_page(request:Request): return templates.TemplateResponse(request,'login.html',{'error':None})

@app.post('/login', response_class=HTMLResponse)
def login(request:Request,email:str=Form(...),password:str=Form(...)):
    with SessionLocal() as db:
        u=db.scalar(select(User).where(User.email==email.strip().lower()))
        if not u or not pw_verify(password,u.password_hash):
            return templates.TemplateResponse(request,'login.html',{'error':'Email ou mot de passe incorrect.'},status_code=400)
        resp=RedirectResponse('/game',303); set_auth_cookie(resp,u.id); return resp

@app.get('/register', response_class=HTMLResponse)
def register_page(request:Request): return templates.TemplateResponse(request,'register.html',{'error':None})

@app.post('/register', response_class=HTMLResponse)
def register(request:Request,email:str=Form(...),username:str=Form(...),company_name:str=Form(...),password:str=Form(...)):
    email=email.strip().lower(); username=username.strip(); company_name=company_name.strip()
    if len(password)<8:return templates.TemplateResponse(request,'register.html',{'error':'Mot de passe : 8 caractères minimum.'},status_code=400)
    with SessionLocal() as db:
        if db.scalar(select(User).where((User.email==email)|(User.username==username))):
            return templates.TemplateResponse(request,'register.html',{'error':'Email ou pseudo déjà utilisé.'},status_code=400)
        u=User(email=email,username=username,password_hash=pw_hash(password),company_name=company_name or 'Skyline Airways')
        db.add(u); db.commit(); db.refresh(u)
        resp=RedirectResponse('/game',303); set_auth_cookie(resp,u.id); return resp

@app.get('/logout')
def logout():
    resp=RedirectResponse('/login',303); resp.delete_cookie('skyline_session'); return resp

@app.get('/game', response_class=HTMLResponse)
def game(request:Request):
    with SessionLocal() as db:
        u=current_user(request,db)
        if not u:return RedirectResponse('/login',303)
    return templates.TemplateResponse(request,'game.html',{})

class BuyAircraft(BaseModel): model_code:str; acquisition:str='buy'
class UpgradeReq(BaseModel): code:str
class RouteReq(BaseModel): aircraft_id:int; destination:str; frequency:int=1

@app.get('/api/state')
def api_state(request:Request):
    with SessionLocal() as db:
        u=require_user(request,db); settle_economy(db,u); db.refresh(u)
        levels=get_upgrade_levels(db,u.id); hlevel=hub_level(levels)
        acs=db.scalars(select(Aircraft).where(Aircraft.user_id==u.id).order_by(Aircraft.id)).all()
        routes=db.scalars(select(Route).where(Route.user_id==u.id).order_by(Route.id)).all()
        by_id={a.id:a for a in acs}; route_by_ac={r.aircraft_id:r for r in routes}
        aircraft=[]
        for a in acs:
            r=route_by_ac.get(a.id); flight=route_metrics(r,a) if r else None
            aircraft.append({'id':a.id,'tail':a.tail,'model_code':a.model_code,'model':AIRCRAFT_CATALOG[a.model_code],'condition':a.condition,'acquisition':a.acquisition,'route_id':r.id if r else None,'flight':flight})
        route_out=[]
        for r in routes:
            a=by_id.get(r.aircraft_id)
            if not a: continue
            route_out.append({'id':r.id,'origin':r.origin,'destination':r.destination,'frequency':r.frequency,'aircraft_id':a.id,'tail':a.tail,'model':AIRCRAFT_CATALOG[a.model_code]['name'],'flight':route_metrics(r,a)})
        nodes=[]
        for n in HUB_NODES:
            lvl=levels.get(n['code'],0); pre=n.get('prereq'); available=(not pre or levels.get(pre,0)>0)
            nodes.append({**n,'level':lvl,'available':available,'price':node_cost(n,lvl),'state':'active' if lvl>0 else ('available' if available else 'locked')})
        return {'user':{'username':u.username,'company_name':u.company_name,'cash':round(u.cash,2),'reputation':u.reputation,'hub_code':u.hub_code},'hub':{'level':hlevel,'stage':stage_for(hlevel),'nodes':nodes},'catalog':AIRCRAFT_CATALOG,'airports':AIRPORTS,'aircraft':aircraft,'routes':route_out,'notams':NOTAMS,'sim_speed':SIM_SPEED}

@app.post('/api/aircraft/buy')
def buy_aircraft(req:BuyAircraft, request:Request):
    if req.model_code not in AIRCRAFT_CATALOG: raise HTTPException(400,'Modèle inconnu')
    if req.acquisition not in ('buy','lease'): raise HTTPException(400,'Mode invalide')
    with SessionLocal() as db:
        u=require_user(request,db); cat=AIRCRAFT_CATALOG[req.model_code]
        cost=cat['price'] if req.acquisition=='buy' else cat['lease']
        if u.cash<cost: raise HTTPException(400,'Fonds insuffisants')
        count=db.scalar(select(Aircraft).where(Aircraft.user_id==u.id).count()) if False else len(db.scalars(select(Aircraft).where(Aircraft.user_id==u.id)).all())
        tail=f"F-SK{count+1:03d}"
        u.cash-=cost; a=Aircraft(user_id=u.id,model_code=req.model_code,tail=tail,acquisition=req.acquisition)
        db.add(a); db.commit(); return {'ok':True,'tail':tail}

@app.post('/api/hub/upgrade')
def upgrade_hub(req:UpgradeReq,request:Request):
    node=next((n for n in HUB_NODES if n['code']==req.code),None)
    if not node: raise HTTPException(404,'Amélioration inconnue')
    with SessionLocal() as db:
        u=require_user(request,db); levels=get_upgrade_levels(db,u.id); lvl=levels.get(req.code,0)
        if lvl>=node['max']: raise HTTPException(400,'Déjà au maximum')
        pre=node.get('prereq')
        if pre and levels.get(pre,0)<=0: raise HTTPException(400,'Prérequis non débloqué')
        cost=node_cost(node,lvl)
        if u.cash<cost: raise HTTPException(400,'Fonds insuffisants')
        row=db.scalar(select(HubUpgrade).where(HubUpgrade.user_id==u.id,HubUpgrade.code==req.code))
        if not row: row=HubUpgrade(user_id=u.id,code=req.code,level=0); db.add(row)
        row.level+=1; u.cash-=cost
        if node['cat'] in ('Premium','Passagers','Sécurité'):u.reputation=min(100,u.reputation+1)
        db.commit(); return {'ok':True,'level':row.level}

@app.post('/api/routes')
def create_route(req:RouteReq,request:Request):
    dest=req.destination.upper()
    if dest not in AIRPORTS or dest=='CDG': raise HTTPException(400,'Destination invalide')
    with SessionLocal() as db:
        u=require_user(request,db); a=db.get(Aircraft,req.aircraft_id)
        if not a or a.user_id!=u.id: raise HTTPException(404,'Avion introuvable')
        if db.scalar(select(Route).where(Route.aircraft_id==a.id)): raise HTTPException(400,'Cet avion est déjà affecté')
        check=route_operational_check('CDG',dest,a.model_code)
        if not check['ok']: return JSONResponse({'ok':False,'check':check},status_code=409)
        r=Route(user_id=u.id,aircraft_id=a.id,origin='CDG',destination=dest,frequency=max(1,min(7,req.frequency)))
        db.add(r); db.commit(); return {'ok':True,'route_id':r.id}

@app.delete('/api/routes/{route_id}')
def delete_route(route_id:int,request:Request):
    with SessionLocal() as db:
        u=require_user(request,db); r=db.get(Route,route_id)
        if not r or r.user_id!=u.id: raise HTTPException(404,'Route inconnue')
        db.delete(r); db.commit(); return {'ok':True}

@app.get('/api/route-check/{destination}')
def route_check(destination:str,request:Request,aircraft_id:Optional[int]=None):
    with SessionLocal() as db:
        u=require_user(request,db); model=None
        if aircraft_id:
            a=db.get(Aircraft,aircraft_id)
            if a and a.user_id==u.id:model=a.model_code
        dest=destination.upper()
        if dest not in AIRPORTS:raise HTTPException(404,'Aéroport inconnu')
        return route_operational_check('CDG',dest,model)
