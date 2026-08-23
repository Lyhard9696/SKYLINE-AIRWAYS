"""SKYLINE v1.3.6 regression: navigation runtime, catalog coverage, airline identity and lightweight FR24."""
from __future__ import annotations
import os,sys,tempfile,subprocess,sqlite3
from pathlib import Path
from sqlalchemy import select
ROOT=Path(__file__).resolve().parents[1];os.chdir(ROOT)
db_path=Path(tempfile.gettempdir())/'skyline_v136_regression.db'
try: db_path.unlink()
except FileNotFoundError: pass
os.environ['DATABASE_URL']=f'sqlite:///{db_path}';os.environ['SECRET_KEY']='v136-test';os.environ['COOKIE_SECURE']='0';os.environ.pop('FR24_API_TOKEN',None)
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main
c=TestClient(main.app)
assert c.get('/health').json()['version']=='1.3.6'
assert subprocess.run(['node','--check','static/game-v136.js']).returncode==0
html=c.get('/login'); assert html.status_code==200
r=c.post('/register',data={'email':'v136@example.test','username':'v136','company_name':'V136 Air','password':'abcdefgh'},follow_redirects=False); assert r.status_code==303
# 591/591 local catalog renders exist.
con=sqlite3.connect(ROOT/'data/catalog.sqlite'); codes=[r[0] for r in con.execute('select icao from aircraft_types')]
assert len(codes)>=591
missing=[x for x in codes if not (ROOT/'static/aircraft/catalog'/f'{x}.svg').exists()]
assert not missing, missing[:10]
# Airline identity resolves from seed or bundled catalog even without FR24 token.
for code in ('AFR','DAL','UAE','EIN'):
    d=c.get('/api/integrations/fr24/airline/'+code).json(); assert d['airline']['name'] and d['airline']['name']!=code
# Contextual hub system remains functional.
with main.SessionLocal() as db:
    u=db.scalar(select(main.User).where(main.User.email=='v136@example.test'));u.cash=2_000_000_000;db.commit()
orig_progress=main.career_progress
main.career_progress=lambda db,u:{'level':100,'xp_total':1,'xp_current':0,'xp_next':1,'progress_pct':100,'era':'test','flights_completed':0,'quests_claimed':0}
assert c.post('/api/hubs/buy',json={'ident':'LFPG'}).status_code==200
hub=c.get('/api/hub/LFPG').json(); assert hub.get('zones') and hub.get('nodes')
# FR24 ground + airborne positions are both retained by the viewport endpoint.
orig_token,orig_fetch=main._fr24_token,main._fetch_fr24
main._fr24_token=lambda:'test'
def fake_fetch(bounds,limit=120,airport=None,modes=('full','light')):
    return ([
      {'fr24_id':'g','lat':49.0,'lon':2.0,'altitude_ft':0,'velocity_kts':8,'heading':120,'on_ground':True,'phase':'ground','type':'A359','reg':'F-GROUND','hex':'39ABCD','callsign':'AFR001','painted_as':'AFR','operating_as':'AFR'},
      {'fr24_id':'a','lat':49.2,'lon':2.2,'altitude_ft':31000,'velocity_kts':440,'heading':250,'on_ground':False,'phase':'airborne','type':'B789','reg':'N-AIR','hex':'ABCDEF','callsign':'DAL002','painted_as':'DAL','operating_as':'DAL'}], 'light')
main._fetch_fr24=fake_fetch
box=c.get('/api/live-traffic/box?lamin=48&lomin=1&lamax=50&lomax=3&limit=40').json()
assert box['total_count']==2 and box['ground_count']==1 and box['airborne_count']==1
main._fetch_fr24,main._fr24_token=orig_fetch,orig_token;main.career_progress=orig_progress
# Client final override disables fictional global traffic and keeps live aircraft visible from world zoom.
js=(ROOT/'static/game-v136.js').read_text()
assert "initWorldAITraffic=function()" in js and "V136_MAJOR_AIRLINES" in js
assert "minzoom:1.0" in js
print('SKYLINE v1.3.6 regression: OK')
