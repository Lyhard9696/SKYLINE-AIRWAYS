"""Smoke tests sans appels réseau externes pour SKYLINE AIRWAYS v1.3.1."""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
db_path=Path(tempfile.gettempdir())/'skyline_v13_smoke_suite.db'
try: db_path.unlink()
except FileNotFoundError: pass
os.environ['DATABASE_URL']=f'sqlite:///{db_path}'
os.environ['SECRET_KEY']='smoke-secret'
os.environ['COOKIE_SECURE']='0'
os.environ.pop('FR24_API_TOKEN',None)
os.environ.pop('AVIATION_EDGE_API_KEY',None)
sys.path.insert(0,str(ROOT))

from fastapi.testclient import TestClient
import main

c=TestClient(main.app)

def check(cond,msg):
    if not cond: raise AssertionError(msg)

r=c.get('/health'); check(r.status_code==200,'health'); check(r.json()['version']=='1.3.1','version')
r=c.post('/register',data={'email':'smoke-v13@example.com','username':'smoke-v13','company_name':'Smoke v13','password':'abcdefgh'},follow_redirects=False)
check(r.status_code==303,'register')
rows=c.get('/api/airports/search',params={'q':'CDG','limit':5}).json(); check(bool(rows),'airport search')
r=c.post('/api/hubs/buy',json={'ident':rows[0]['ident']}); check(r.status_code==200,'first hub')
r=c.get('/game'); check(r.status_code==200,'game'); check('game-v131.js?v=131' in r.text,'v131 JS'); check('premium-v131.css?v=131' in r.text,'v131 CSS')

for path in ('/api/state','/api/research','/api/alliances','/api/hubs/network','/api/aviation/notam/status','/api/integrations/fr24/status'):
    rr=c.get(path); check(rr.status_code==200,path)

# Alliance réelle : création -> XP -> niveau 2 -> amélioration commune carburant.
r=c.post('/api/alliances/player/create',json={'name':'Smoke Wings','tag':'SMK'}); check(r.status_code==200,'alliance create')
r=c.post('/api/alliances/player/contribute',json={'amount':3_000_000}); check(r.status_code==200,'alliance contribution')
p=c.get('/api/alliances').json()['player_alliance']; check(p['level']>=2,'alliance level'); check(p['can_manage'],'alliance management')
r=c.post('/api/alliances/upgrades/buy',json={'code':'fuel_contract'}); check(r.status_code==200,'alliance upgrade')
p=c.get('/api/alliances').json()['player_alliance']; check(p['upgrade_bonuses']['fuel']<0,'shared fuel bonus')
mods=c.get('/api/research').json()['modifiers']['totals']; check(mods['fuel']<=-2.2,'alliance bonus applied to company modifier engine')

# NOTAM FAA public : aucune clé, état connecté.
n=c.get('/api/aviation/notam/status').json(); check(n['configured'] is True and n['auth_required'] is False,'NOTAM public state')
# FR24 sans secret doit être propre également.
f=c.get('/api/integrations/fr24/world-summary').json(); check(f['configured'] is False,'FR24 secret state')

print('SKYLINE v1.3.1 smoke: OK')
