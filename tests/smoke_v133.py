"""Deterministic v1.3.3 tests: hierarchical hubs + targeted FR24 detail, no network."""
from __future__ import annotations
import os,sys,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from sqlalchemy import select

ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
db_path=Path(tempfile.gettempdir())/'skyline_v133_regression.db'
try:db_path.unlink()
except FileNotFoundError:pass
os.environ['DATABASE_URL']=f'sqlite:///{db_path}';os.environ['SECRET_KEY']='v133-test';os.environ['COOKIE_SECURE']='0';os.environ.pop('FR24_API_TOKEN',None)
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main

c=TestClient(main.app)
r=c.post('/register',data={'email':'v133@example.test','username':'v133','company_name':'V133 Air','password':'abcdefgh'},follow_redirects=False);assert r.status_code==303
# Give enough cash/level for deterministic hub purchases.
with main.SessionLocal() as db:
    u=db.scalar(select(main.User).where(main.User.email=='v133@example.test'));u.cash=2_000_000_000;db.commit()
orig_progress=main.career_progress
main.career_progress=lambda db,u:{'level':100,'xp_total':1,'xp_current':0,'xp_next':1,'progress_pct':100,'era':'test','flights_completed':0,'quests_claimed':0}
assert c.post('/api/hubs/buy',json={'ident':'LFPG'}).status_code==200
assert c.post('/api/hubs/buy',json={'ident':'LFBL'}).status_code==200

cdg=c.get('/api/hub/LFPG').json();limoges=c.get('/api/hub/LFBL').json()
assert cdg.get('zones') and any(z['code']=='terminal' for z in cdg['zones']) and any(z['code']=='mobility' for z in cdg['zones'])
cdg_nodes={n['code']:n for n in cdg['nodes']};lim_nodes={n['code']:n for n in limoges['nodes']}
assert cdg_nodes['RAIL']['context_available'] and 'TGV' in cdg_nodes['RAIL']['name']
assert cdg_nodes['METRO']['context_available']
assert lim_nodes['BUS']['context_available'] and lim_nodes['RIDESHARE']['context_available']
assert not lim_nodes['METRO']['context_available'] and lim_nodes['METRO']['state']=='unavailable'
# Backend must reject a contextually impossible metro at Limoges even with player level/cash.
r=c.post('/api/hub/upgrade',json={'ident':'LFBL','code':'METRO'});assert r.status_code==400

# A root construction really transitions available -> construction -> active.
node=next(n for n in cdg['nodes'] if n['can_upgrade'])
if node['level']==0:
    r=c.post('/api/hub/upgrade',json={'ident':'LFPG','code':node['code']});assert r.status_code==200 and r.json()['state']=='construction'
    with main.SessionLocal() as db:
        row=db.scalar(select(main.HubConstruction).where(main.HubConstruction.user_id==1,main.HubConstruction.airport_ident=='LFPG',main.HubConstruction.code==node['code']))
        if row:row.completes_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit()
    cdg=c.get('/api/hub/LFPG').json();assert next(n for n in cdg['nodes'] if n['code']==node['code'])['state']=='active'

# Targeted click detail fallback can recover a ground target without a world snapshot.
orig_token=main._fr24_token;orig_fetch=main._fetch_fr24
main._fr24_token=lambda:'test'
def fake_fetch(bounds,limit=120,airport=None,modes=('full','light')):
    return ([{'fr24_id':'abc123','lat':49.0,'lon':2.0,'altitude_ft':0,'velocity_kts':8,'heading':120,'on_ground':True,'phase':'ground','type':'A359','reg':'F-GROUND','hex':'39ABCD','callsign':'AFR001','flight':'AF001','painted_as':'AFR','operating_as':'AFR','origin':'CDG','destination':'JFK'}],'full')
main._fetch_fr24=fake_fetch
out=main._fr24_live_detail_fallback('abc123',49.0,2.0,'F-GROUND','39ABCD','AFR001')
assert out and out['on_ground'] and out['reg']=='F-GROUND' and out['painted_as']=='AFR'
main._fetch_fr24=orig_fetch;main._fr24_token=orig_token;main.career_progress=orig_progress
print('SKYLINE v1.3.3 regression: OK')
