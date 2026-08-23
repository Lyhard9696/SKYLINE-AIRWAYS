import math
import os
import sqlite3
from functools import lru_cache

ROOT = os.path.dirname(os.path.abspath(__file__))
CATALOG_DB = os.path.join(ROOT, 'data', 'catalog.sqlite')

# Core modern-airliner overrides. Source catalogue supplies the identity/dimensions;
# these values are gameplay-oriented market/configuration values and can later be
# replaced by licensed OEM datasets without touching the rest of the engine.
OVERRIDES = {
    'AT46': dict(seats=48, range_nm=726, cruise_kts=300, price=22_000_000),
    'AT72': dict(seats=72, range_nm=825, cruise_kts=275, price=26_000_000),
    'AT73': dict(seats=72, range_nm=825, cruise_kts=275, price=26_000_000),
    'BCS1': dict(seats=120, range_nm=3450, cruise_kts=447, price=46_000_000),
    'BCS3': dict(seats=145, range_nm=3400, cruise_kts=447, price=52_000_000),
    'A318': dict(seats=118, range_nm=3100, cruise_kts=447, price=38_000_000),
    'A319': dict(seats=144, range_nm=3750, cruise_kts=447, price=44_000_000),
    'A19N': dict(seats=156, range_nm=3750, cruise_kts=447, price=49_000_000),
    'A320': dict(seats=180, range_nm=3300, cruise_kts=447, price=48_000_000),
    'A20N': dict(seats=186, range_nm=3400, cruise_kts=447, price=58_000_000),
    'A321': dict(seats=220, range_nm=3200, cruise_kts=447, price=60_000_000),
    'A21N': dict(seats=244, range_nm=4000, cruise_kts=447, price=72_000_000),
    'A332': dict(seats=260, range_nm=7250, cruise_kts=470, price=105_000_000),
    'A333': dict(seats=300, range_nm=6350, cruise_kts=470, price=112_000_000),
    'A338': dict(seats=260, range_nm=8150, cruise_kts=470, price=124_000_000),
    'A339': dict(seats=310, range_nm=7200, cruise_kts=470, price=132_000_000),
    'A343': dict(seats=300, range_nm=6700, cruise_kts=470, price=48_000_000),
    'A345': dict(seats=300, range_nm=9000, cruise_kts=470, price=62_000_000),
    'A346': dict(seats=370, range_nm=7900, cruise_kts=470, price=68_000_000),
    'A359': dict(seats=325, range_nm=8100, cruise_kts=488, price=180_000_000),
    'A35K': dict(seats=369, range_nm=8700, cruise_kts=488, price=205_000_000),
    'A388': dict(seats=555, range_nm=8000, cruise_kts=488, price=245_000_000),
    'B712': dict(seats=117, range_nm=2060, cruise_kts=444, price=24_000_000),
    'B737': dict(seats=149, range_nm=3365, cruise_kts=453, price=38_000_000),
    'B738': dict(seats=189, range_nm=2935, cruise_kts=453, price=48_000_000),
    'B739': dict(seats=220, range_nm=2950, cruise_kts=453, price=52_000_000),
    'B37M': dict(seats=172, range_nm=3850, cruise_kts=453, price=56_000_000),
    'B38M': dict(seats=189, range_nm=3550, cruise_kts=453, price=62_000_000),
    'B39M': dict(seats=220, range_nm=3550, cruise_kts=453, price=67_000_000),
    'B3JM': dict(seats=230, range_nm=3300, cruise_kts=453, price=72_000_000),
    'B752': dict(seats=239, range_nm=3900, cruise_kts=461, price=34_000_000),
    'B753': dict(seats=295, range_nm=3400, cruise_kts=461, price=36_000_000),
    'B763': dict(seats=269, range_nm=5990, cruise_kts=486, price=48_000_000),
    'B764': dict(seats=304, range_nm=5625, cruise_kts=486, price=55_000_000),
    'B772': dict(seats=314, range_nm=5240, cruise_kts=482, price=62_000_000),
    'B77L': dict(seats=317, range_nm=8555, cruise_kts=482, price=128_000_000),
    'B773': dict(seats=368, range_nm=6030, cruise_kts=482, price=72_000_000),
    'B77W': dict(seats=396, range_nm=7370, cruise_kts=482, price=140_000_000),
    'B778': dict(seats=395, range_nm=8200, cruise_kts=488, price=198_000_000),
    'B779': dict(seats=426, range_nm=7285, cruise_kts=488, price=205_000_000),
    'B788': dict(seats=248, range_nm=7355, cruise_kts=488, price=145_000_000),
    'B789': dict(seats=296, range_nm=7635, cruise_kts=488, price=160_000_000),
    'B78X': dict(seats=336, range_nm=6430, cruise_kts=488, price=172_000_000),
    'B744': dict(seats=416, range_nm=7670, cruise_kts=504, price=72_000_000),
    'B748': dict(seats=467, range_nm=7730, cruise_kts=504, price=116_000_000),
    'E170': dict(seats=76, range_nm=2150, cruise_kts=447, price=29_000_000),
    'E75L': dict(seats=88, range_nm=2200, cruise_kts=447, price=32_000_000),
    'E75S': dict(seats=88, range_nm=2200, cruise_kts=447, price=32_000_000),
    'E190': dict(seats=114, range_nm=2450, cruise_kts=447, price=38_000_000),
    'E195': dict(seats=132, range_nm=2300, cruise_kts=447, price=41_000_000),
    'E135': dict(seats=37, range_nm=1750, cruise_kts=430, price=10_000_000),
    'E145': dict(seats=50, range_nm=1550, cruise_kts=430, price=12_000_000),
    'CRJ2': dict(seats=50, range_nm=1700, cruise_kts=424, price=10_000_000),
    'CRJ7': dict(seats=78, range_nm=1378, cruise_kts=447, price=18_000_000),
    'CRJ9': dict(seats=90, range_nm=1553, cruise_kts=447, price=23_000_000),
    'CRJX': dict(seats=104, range_nm=1622, cruise_kts=447, price=28_000_000),
    'DH8D': dict(seats=78, range_nm=1100, cruise_kts=360, price=24_000_000),
    'MD11': dict(seats=293, range_nm=6840, cruise_kts=490, price=32_000_000),
    'MD82': dict(seats=155, range_nm=2050, cruise_kts=430, price=9_000_000),
    'MD83': dict(seats=155, range_nm=2500, cruise_kts=430, price=10_000_000),
    'MD88': dict(seats=155, range_nm=2050, cruise_kts=430, price=11_000_000),
    'MD90': dict(seats=172, range_nm=2455, cruise_kts=430, price=14_000_000),
    'A139': dict(seats=15, range_nm=573, cruise_kts=167, price=13_000_000),
    'A169': dict(seats=10, range_nm=440, cruise_kts=155, price=11_000_000),
    'A189': dict(seats=18, range_nm=490, cruise_kts=150, price=18_000_000),
    'EC35': dict(seats=7, range_nm=340, cruise_kts=137, price=6_500_000),
    'H145': dict(seats=10, range_nm=350, cruise_kts=134, price=9_500_000),
    'EC45': dict(seats=10, range_nm=351, cruise_kts=129, price=10_000_000),
    'A400': dict(seats=116, range_nm=4800, cruise_kts=422, price=170_000_000),
    'C30J': dict(seats=92, range_nm=2835, cruise_kts=355, price=95_000_000),
    'RFAL': dict(seats=1, range_nm=2000, cruise_kts=510, price=100_000_000),
}


def db():
    con = sqlite3.connect(f'file:{CATALOG_DB}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def _clean(s):
    return (s or '').strip()


def airport_price(a, runway_count=0):
    t = a['type']
    base = {
        'large_airport': 28_000_000,
        'medium_airport': 12_000_000,
        'small_airport': 3_500_000,
        'heliport': 1_800_000,
        'seaplane_base': 1_500_000,
        'balloonport': 900_000,
    }.get(t, 2_000_000)
    if a['scheduled']:
        base *= 1.25
    base += min(runway_count, 6) * 650_000
    return int(round(base / 50_000) * 50_000)


def _airport_row(r, with_price=False):
    d = dict(r)
    d['code'] = d.get('iata') or d.get('icao') or d['ident']
    d['display'] = f"{d['code']} · {d['name']}" + (f" — {d['municipality']}" if d.get('municipality') else '')
    if with_price:
        with db() as con:
            rc = con.execute('select count(*) from runways where airport_ident=? and closed=0', (d['ident'],)).fetchone()[0]
        d['runway_count'] = rc
        d['price'] = airport_price(d, rc)
    d['purchasable'] = d.get('type') not in ('closed',)
    return d


def search_airports(q='', limit=30, scheduled_only=False, types=None):
    q = _clean(q)
    limit = max(1, min(100, int(limit)))
    with db() as con:
        where = ['1=1']
        args = []
        if q:
            like = f"%{q}%"
            where.append('(ident LIKE ? OR iata LIKE ? OR icao LIKE ? OR name LIKE ? OR municipality LIKE ? OR keywords LIKE ?)')
            args += [like] * 6
        if scheduled_only:
            where.append('scheduled=1')
        if types:
            placeholders = ','.join('?' * len(types))
            where.append(f'type IN ({placeholders})')
            args += list(types)
        exact_order = ''
        if q:
            exact_order = "case when upper(ident)=? or upper(iata)=? or upper(icao)=? then 0 else 1 end,"
            args += [q.upper(), q.upper(), q.upper()]
        sql = f'''select * from airports where {' and '.join(where)}
                  order by {exact_order} scheduled desc,
                  case type when 'large_airport' then 0 when 'medium_airport' then 1 when 'small_airport' then 2 else 3 end,
                  case when iata!='' then 0 else 1 end, name limit ?'''
        args.append(limit)
        rows = con.execute(sql, args).fetchall()
    return [_airport_row(r) for r in rows]


def airport_detail(ident):
    ident = _clean(ident).upper()
    with db() as con:
        r = con.execute('select * from airports where upper(ident)=? or upper(iata)=? or upper(icao)=? limit 1', (ident, ident, ident)).fetchone()
        if not r:
            return None
        d = dict(r)
        runways = [dict(x) for x in con.execute('select * from runways where airport_ident=? order by length_ft desc', (d['ident'],)).fetchall()]
    d = _airport_row(d)
    d['runways'] = runways
    d['runway_count'] = sum(1 for x in runways if not x['closed'])
    d['longest_runway_ft'] = max([x['length_ft'] or 0 for x in runways] or [0])
    d['price'] = airport_price(d, d['runway_count'])
    return d


def major_airports(limit=2500):
    limit = max(100, min(5000, int(limit)))
    with db() as con:
        rows = con.execute('''select * from airports where scheduled=1 and type in ('large_airport','medium_airport')
                              order by case type when 'large_airport' then 0 else 1 end,
                              case when iata!='' then 0 else 1 end limit ?''', (limit,)).fetchall()
    return [_airport_row(r) for r in rows]



def airport_countries(min_scheduled=2):
    """Countries with scheduled airports, for strategic base selection."""
    with db() as con:
        rows=con.execute("select country, count(*) as n from airports where scheduled=1 and country!='' group by country having count(*)>=? order by n desc, country",(int(min_scheduled),)).fetchall()
    return [{'code':r['country'],'airport_count':int(r['n'])} for r in rows]


def special_base_airports(country, limit=120):
    country=_clean(country).upper()[:2]
    if not country:return []
    limit=max(10,min(240,int(limit)))
    sql="select * from airports where country=? and scheduled=1 and type in ('large_airport','medium_airport','small_airport') order by case type when 'large_airport' then 0 when 'medium_airport' then 1 else 2 end, case when iata!='' then 0 else 1 end, name limit ?"
    with db() as con:
        rows=con.execute(sql,(country,limit)).fetchall()
    out=[]
    for r in rows:
        d=_airport_row(r,with_price=False)
        out.append({'ident':d['ident'],'code':d['code'],'name':d['name'],'municipality':d.get('municipality') or '', 'country':d.get('country') or country,'type':d['type'],'lat':d['lat'],'lon':d['lon']})
    return out

def all_owned_hub_candidates(q='', limit=50):
    return search_airports(q, limit=limit)


def _num(v, default=None):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def aircraft_spec_from_row(row):
    r = dict(row)
    code = r['icao']
    desc = r.get('description') or ''
    cls = desc[:1] if desc else 'L'
    eng = desc[-1:] if desc else ''
    mtow = _num(r.get('mtow'))
    length = _num(r.get('length'))
    source_range = _num(r.get('operating_range'))
    source_speed = _num(r.get('cruise_speed'))
    ov = OVERRIDES.get(code, {})

    if cls == 'H':
        category = 'Hélicoptère'
        default_speed = 145
        default_range = 360
    elif cls in ('A', 'S'):
        category = 'Amphibie / hydravion'
        default_speed = 180
        default_range = 700
    elif eng == 'T':
        category = 'Turbopropulseur'
        default_speed = 280
        default_range = 1200
    elif eng == 'J':
        if (mtow or 0) > 180_000 or (r.get('wtc') == 'H'):
            category = 'Jet long-courrier / lourd'
            default_range = 6000
        elif (mtow or 0) > 45_000:
            category = 'Jet commercial'
            default_range = 3200
        else:
            category = 'Jet régional / affaires'
            default_range = 1800
        default_speed = 445
    elif eng == 'P':
        category = 'Avion à pistons'
        default_speed = 130
        default_range = 650
    else:
        category = 'Aéronef'
        default_speed = 200
        default_range = 900

    range_nm = ov.get('range_nm') or source_range or default_range
    cruise_kts = ov.get('cruise_kts') or source_speed or default_speed

    if 'seats' in ov:
        seats = ov['seats']
    elif cls == 'H':
        seats = max(4, min(28, int(((mtow or 4000) / 1000) * 1.8)))
    elif r.get('iata'):
        if r.get('wtc') == 'H':
            seats = max(220, min(520, int(((mtow or 220000) / 1000) * 1.28)))
        elif (mtow or 0) >= 100_000:
            seats = max(180, min(330, int((mtow / 1000) * 1.2)))
        elif (mtow or 0) >= 35_000:
            seats = max(70, min(230, int((mtow / 1000) * 2.2)))
        else:
            seats = max(18, min(100, int(((mtow or 20000) / 1000) * 2.5)))
    else:
        seats = max(4, min(70, int(((mtow or 8000) / 1000) * 1.5)))

    if 'price' in ov:
        price = ov['price']
    else:
        if mtow:
            factor = 650_000 if eng == 'J' else (450_000 if eng == 'T' else 250_000)
            price = int(max(4_000_000, min(260_000_000, (mtow / 1000) * factor)))
        else:
            price = 22_000_000 if r.get('iata') else 8_000_000
        if not r.get('iata'):
            price = int(price * 0.65)
    price = int(round(price / 250_000) * 250_000)
    lease = int(round((price * 0.055) / 50_000) * 50_000)

    if cls == 'H':
        runway_required_m = 0
    else:
        runway_required_m = int(max(650, min(3500, 900 + ((mtow or 30000) / 1000) * 6.1)))

    commercial = bool(r.get('iata')) and cls in ('L', 'A', 'S', 'H')
    return {
        'icao': code, 'iata': r.get('iata') or '', 'manufacturer': r.get('manufacturer') or '',
        'name': r.get('name') or code, 'description': desc, 'wtc': r.get('wtc') or '',
        'service_ceiling': r.get('service_ceiling'), 'approach_speed': r.get('approach_speed'),
        'cruise_kts': int(round(cruise_kts)), 'max_speed': r.get('maximum_speed'),
        'length_m': r.get('length'), 'wingspan_m': r.get('wingspan'), 'fuel_capacity_l': r.get('fuel_capacity'),
        'range_nm': int(round(range_nm)), 'range_km': int(round(range_nm * 1.852)), 'mtow_kg': r.get('mtow'),
        'seats': int(seats), 'price': price, 'lease': lease, 'category': category,
        'commercial': commercial, 'runway_required_m': runway_required_m,
        'source_values_complete': bool(source_range and source_speed and mtow),
    }



# v0.8: special-purpose aircraft are intentionally visible in the same catalogue
# as the civil fleet. Their late-game use is gated by the special-operations engine,
# not hidden from the player.
SPECIAL_META = {
    'EC45': {'special_role':'Secours / sécurité civile', 'min_level':22, 'image':'/static/aircraft/real/h145.jpg'},
    'A139': {'special_role':'SAR / VIP / service public', 'min_level':24, 'image':''},
    'A400': {'special_role':'Transport stratégique', 'min_level':32, 'image':'/static/aircraft/real/a400m.jpg'},
    'C30J': {'special_role':'Transport / logistique stratégique', 'min_level':32, 'image':''},
    'RFAL': {'special_role':'Défense du territoire', 'min_level':35, 'image':'/static/aircraft/real/rafale.jpg'},
}
SPECIAL_AIRCRAFT = {
    'CL2T': {
        'icao':'CL2T','iata':'','manufacturer':'De Havilland Canada / Canadair','name':'CL-415 / DHC-515 family',
        'description':'Aerial firefighting amphibian','wtc':'M','service_ceiling':15000,'approach_speed':90,
        'cruise_kts':180,'max_speed':195,'length_m':19.8,'wingspan_m':28.6,'fuel_capacity_l':12690,
        'range_nm':1300,'range_km':2408,'mtow_kg':19890,'seats':2,'price':42_000_000,'lease':2_300_000,
        'category':'Bombardier d’eau / amphibie','commercial':False,'runway_required_m':950,
        'source_values_complete':False,'models':[],'special_role':'Sécurité civile / lutte incendie','min_level':26,
        'image':'/static/aircraft/real/cl415.jpg'
    },
    'NH90': {
        'icao':'NH90','iata':'','manufacturer':'NHIndustries','name':'NH90',
        'description':'Medium multirole helicopter','wtc':'M','service_ceiling':20000,'approach_speed':0,
        'cruise_kts':160,'max_speed':175,'length_m':19.6,'wingspan_m':16.3,'fuel_capacity_l':2500,
        'range_nm':430,'range_km':796,'mtow_kg':11000,'seats':20,'price':46_000_000,'lease':2_550_000,
        'category':'Hélicoptère','commercial':False,'runway_required_m':0,
        'source_values_complete':False,'models':[],'special_role':'Service public / transport stratégique','min_level':28,
        'image':'/static/aircraft/real/nh90.jpg'
    },
    'MQ9': {
        'icao':'MQ9','iata':'','manufacturer':'General Atomics','name':'MQ-9 class surveillance UAV',
        'description':'Strategic surveillance remotely piloted aircraft','wtc':'M','service_ceiling':50000,'approach_speed':90,
        'cruise_kts':170,'max_speed':260,'length_m':11.0,'wingspan_m':20.0,'fuel_capacity_l':0,
        'range_nm':1000,'range_km':1852,'mtow_kg':4800,'seats':0,'price':32_000_000,'lease':1_750_000,
        'category':'Surveillance stratégique','commercial':False,'runway_required_m':1100,
        'source_values_complete':False,'models':[],'special_role':'Surveillance / souveraineté','min_level':30,
        'image':''
    }
}

def _specialize(spec):
    if not spec:
        return spec
    out=dict(spec)
    out.update(SPECIAL_META.get((out.get('icao') or '').upper(),{}))
    code=(out.get('icao') or '').upper()
    # Only use a photograph when its airframe family is known. A wrong photo is
    # worse than an explicit "photo non disponible" state.
    verified={
        'A21N':'/static/aircraft/real/a321neo.jpg',
        'A359':'/static/aircraft/real/a350.jpg','A35K':'/static/aircraft/real/a350.jpg',
        'B38M':'/static/aircraft/real/b737max8.jpg','B37M':'/static/aircraft/real/b737max8.jpg',
        'B39M':'/static/aircraft/real/b737max8.jpg','B3JM':'/static/aircraft/real/b737max8.jpg',
        'E290':'/static/aircraft/real/e190e2.jpg','E295':'/static/aircraft/real/e190e2.jpg',
        'EC45':'/static/aircraft/real/h145.jpg','NH90':'/static/aircraft/real/nh90.jpg',
        'CL2T':'/static/aircraft/real/cl415.jpg','A400':'/static/aircraft/real/a400m.jpg',
        'RFAL':'/static/aircraft/real/rafale.jpg',
    }
    if code in verified:
        out['image']=verified[code];out['photo_verified']=True
    else:
        # keep a manually curated image only when explicitly supplied; otherwise no fake family photo
        out['image']=out.get('image','') if out.get('special_role') else ''
        out['photo_verified']=bool(out.get('image'))
    out.setdefault('special_role','')
    out.setdefault('min_level',1)
    return out

def _special_matches(spec,q='',manufacturer='',category=''):
    q=(q or '').strip().lower(); manufacturer=(manufacturer or '').strip().lower()
    if q and q not in ' '.join(str(spec.get(k,'')) for k in ('icao','manufacturer','name','category','special_role')).lower():
        return False
    if manufacturer and manufacturer != str(spec.get('manufacturer','')).lower():
        return False
    if category and category != spec.get('category'):
        return False
    return True

def search_aircraft(q='', manufacturer='', commercial_only=True, category='', limit=60, offset=0):
    q = _clean(q)
    manufacturer = _clean(manufacturer)
    limit = max(1, min(120, int(limit)))
    offset = max(0, int(offset))
    with db() as con:
        where = ['1=1']
        args = []
        if q:
            like = f'%{q}%'
            where.append('(icao LIKE ? OR iata LIKE ? OR manufacturer LIKE ? OR name LIKE ?)')
            args += [like] * 4
        if manufacturer:
            where.append('manufacturer=?')
            args.append(manufacturer)
        if commercial_only:
            where.append("iata!=''")
        rows = con.execute(f'''select * from aircraft_types where {' and '.join(where)}
                              order by manufacturer,name limit ? offset ?''', (*args, limit, offset)).fetchall()
    specs = [_specialize(aircraft_spec_from_row(r)) for r in rows]
    if category:
        specs = [x for x in specs if x['category'] == category]
    if not commercial_only and offset==0:
        synthetic=[_specialize(x) for x in SPECIAL_AIRCRAFT.values() if _special_matches(x,q,manufacturer,category)]
        existing={x['icao'] for x in specs}
        specs=synthetic+[x for x in specs if x['icao'] not in {y['icao'] for y in synthetic}]
    return specs[:limit]


def aircraft_detail(code):
    code = _clean(code).upper()
    if code in SPECIAL_AIRCRAFT:
        return _specialize(SPECIAL_AIRCRAFT[code])
    with db() as con:
        r = con.execute('select * from aircraft_types where upper(icao)=? limit 1', (code,)).fetchone()
        if not r:
            return None
        spec = _specialize(aircraft_spec_from_row(r))
        spec['models'] = [dict(x) for x in con.execute('select * from aircraft_models where type_icao=? order by name', (r['icao'],)).fetchall()]
    return spec


def aircraft_manufacturers():
    with db() as con:
        names={r[0] for r in con.execute("select distinct manufacturer from aircraft_types where manufacturer!='' order by manufacturer").fetchall()}
    names.update(x['manufacturer'] for x in SPECIAL_AIRCRAFT.values())
    return sorted(names)


def search_airlines(q='', limit=40):
    q = _clean(q)
    limit = max(1, min(100, int(limit)))
    with db() as con:
        if q:
            like=f'%{q}%'
            rows=con.execute('''select * from airlines where icao like ? or iata like ? or name like ? or callsign like ?
                                order by active desc,name limit ?''',(like,like,like,like,limit)).fetchall()
        else:
            rows=con.execute('select * from airlines order by active desc,name limit ?',(limit,)).fetchall()
    return [dict(r) for r in rows]


def longest_runway_m(ident):
    with db() as con:
        v = con.execute('select max(length_ft) from runways where airport_ident=? and closed=0', (ident,)).fetchone()[0]
    return int((v or 0) * 0.3048)
