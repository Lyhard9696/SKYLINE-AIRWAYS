"""Deterministic v1.3.2 regression suite: no external network calls."""
from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
db_path=Path(tempfile.gettempdir())/'skyline_v132_regression.db'
try:db_path.unlink()
except FileNotFoundError:pass
os.environ['DATABASE_URL']=f'sqlite:///{db_path}';os.environ['SECRET_KEY']='v132-test';os.environ['COOKIE_SECURE']='0';os.environ.pop('FR24_API_TOKEN',None)
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main

c=TestClient(main.app)
r=c.post('/register',data={'email':'v132@example.test','username':'v132','company_name':'V132 Air','password':'abcdefgh'},follow_redirects=False);assert r.status_code==303
assert c.post('/api/hubs/buy',json={'ident':'LFOB'}).status_code==200
hub=c.get('/api/hub/LFOB').json();node=next(x for x in hub['nodes'] if x['can_upgrade']);assert node['state']=='available'
out=c.post('/api/hub/upgrade',json={'ident':'LFOB','code':node['code']}).json();assert out['state']=='construction'
hub=c.get('/api/hub/LFOB').json();job=next(x for x in hub['nodes'] if x['code']==node['code']);assert job['state']=='construction' and job['construction_started_at']
with main.SessionLocal() as db:
    row=db.scalar(select(main.HubConstruction).where(main.HubConstruction.code==node['code']));row.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
hub=c.get('/api/hub/LFOB').json();done=next(x for x in hub['nodes'] if x['code']==node['code']);assert done['state']=='active' and done['level']==1

# A Special Ops base can be purchased on the country map without owning that airport as a commercial hub.
orig_progress=main.career_progress
main.career_progress=lambda db,u:{'level':100,'xp_total':1,'xp_current':0,'xp_next':1,'progress_pct':100,'era':'test','flights_completed':0,'quests_claimed':0}
sp=c.get('/api/special-ops?country=FR').json();site=next(x for x in sp['country_airports'] if x['ident']!='LFOB')
r=c.post('/api/special-ops/base',json={'airport_ident':site['ident'],'branch':'sar'});assert r.status_code==200
assert any(b['airport_ident']==site['ident'] and b['branch']=='sar' for b in c.get('/api/special-ops?country=FR').json()['bases'])
main.career_progress=orig_progress

# The compatibility world snapshot must never call the position downloader.
main._fr24_token=lambda:'test';main._fr24_live_count=lambda:{'ok':True,'count':99999}
def forbidden(*a,**k):raise AssertionError('planet-sized FR24 fetch invoked')
main._fetch_fr24=forbidden
world=main._fr24_world_snapshot();assert world['states']==[] and world['tracked_count']==99999 and world['memory_safe']

# Ground positions retain identity for the click-to-detail/photo flow.
x=main._fr24_normalize({'fr24_id':'abc','lat':49,'lon':2,'alt':0,'gspeed':12,'type':'A359','reg':'F-TEST','painted_as':'AFR','operating_as':'AFR','orig_iata':'CDG','dest_iata':'JFK'})
assert x['on_ground'] and x['reg']=='F-TEST' and x['fr24_id']=='abc'
print('SKYLINE v1.3.2 regression: OK')
