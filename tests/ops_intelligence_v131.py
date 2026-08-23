"""Deterministic tests for the v1.3.1 OPS intelligence engine (no network)."""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
db_path=Path(tempfile.gettempdir())/'skyline_ops_v131_suite.db'
try: db_path.unlink()
except FileNotFoundError: pass
os.environ['DATABASE_URL']=f'sqlite:///{db_path}'
os.environ['SECRET_KEY']='ops-test-secret'
sys.path.insert(0,str(ROOT))

import main
from models import User, UserHub, Aircraft, Route

with main.SessionLocal() as db:
    u=User(email='ops-v131@example.test',username='ops-v131',password_hash='x',company_name='OPS v131',cash=1_000_000_000,reputation=50)
    db.add(u); db.flush()
    db.add(UserHub(user_id=u.id,airport_ident='LFPG',is_primary=True,purchase_price=0))
    a1=Aircraft(user_id=u.id,type_icao='A359',tail='F-TST01',home_hub='LFPG')
    a2=Aircraft(user_id=u.id,type_icao='A359',tail='F-TST02',home_hub='LFPG')
    db.add_all([a1,a2]); db.flush()
    db.add_all([
        Route(user_id=u.id,aircraft_id=a1.id,origin='LFPG',destination='KJFK',frequency=1),
        Route(user_id=u.id,aircraft_id=a2.id,origin='LFPG',destination='UAAA',frequency=1),
    ])
    db.commit(); db.refresh(u)

    def fake_notams(codes,ttl=600):
        codes=list(codes); by={c:[] for c in codes}
        if 'KJFK' in by:
            by['KJFK']=[{'number':'A1234/26','location':'KJFK','class':'RWY','category':'runway','severity':'critical','start':'now','end':'later','text':'RWY 04L/22R CLSD','active':True}]
        uk={'number':'A0050/26','location':'UKBV','class':'AIRSPACE','category':'airspace','severity':'critical','start':'now','end':'later','text':'AIRSPACE PROHIBITED FOR ALL AIRCRAFT ATS IS NOT PROVIDED','active':True}
        for c in ('UKBV','UKDV','UKFV','UKLV','UKOV'):
            if c in by: by[c]=[uk]
        return {'ok':True,'configured':True,'provider':'FAA NOTAM Search','by_station':by,'data':[x for rows in by.values() for x in rows]}

    main._fetch_notams_many=fake_notams
    main._fetch_sigmet_geojson=lambda:{'ok':True,'features':[{
        'type':'Feature','geometry':{'type':'Polygon','coordinates':[[[-45,45],[-35,45],[-35,55],[-45,55],[-45,45]]]},
        'properties':{'hazard':'SEV TURB','rawSigmet':'SEV TURB OBS'}
    }]}
    main._aviation_weather_product=lambda *args,**kwargs:{'ok':False,'data':[],'raw':''}

    out=main._ops_intelligence(db,u)
    assert out['mode']=='relevant-only'
    assert any(a['kind']=='notam' and a.get('airport')=='KJFK' for a in out['alerts'])
    assert any(a['kind']=='sigmet' for a in out['alerts'])
    assert any(a['kind']=='airspace' for a in out['alerts'])
    assert {x['icao'] for x in out['monitored_airports']}=={'LFPG','KJFK','UAAA'}

print('SKYLINE v1.3.1 OPS intelligence: OK')
