import math
from datetime import datetime, timezone

SIM_SPEED = 120.0  # simulated seconds per real second (6 simulated minutes per real second)

# Upgrade positions are bearings/distances around the actual airport reference point.
# This keeps the layer spatially coherent for every real airport while the satellite
# image remains the precise geographic basemap.
UPGRADES = [
    dict(code='GATES_CONTACT', name='Portes au contact', cat='Airside', max=25, cost=1_800_000, bearing=15, dist=450, desc='Passerelles et postes au contact. Chaque niveau ajoute une porte exploitable.', prereq=None),
    dict(code='GATES_REMOTE', name='Parkings avions éloignés', cat='Airside', max=20, cost=1_150_000, bearing=42, dist=720, desc='Stands au large, bus et capacité de pointe.', prereq=None),
    dict(code='WIDEBODY', name='Postes gros-porteurs', cat='Airside', max=12, cost=4_500_000, bearing=63, dist=610, desc='Postes renforcés pour A330/A350/777/787/A380 et équivalents.', prereq='GATES_CONTACT'),
    dict(code='REGIONAL', name='Zone régionale', cat='Airside', max=12, cost=1_050_000, bearing=92, dist=520, desc='Optimise les rotations de turbopropulseurs et jets régionaux.', prereq=None),
    dict(code='APRON', name='Aires de trafic', cat='Airside', max=10, cost=2_800_000, bearing=118, dist=760, desc='Plus de surface opérationnelle pour stationnement et services.', prereq=None),
    dict(code='TAXI', name='Capacité taxiways', cat='Airside', max=10, cost=4_000_000, bearing=142, dist=980, desc='Réduit les conflits de roulage et augmente le débit au sol.', prereq=None),
    dict(code='DEICING', name='Dégivrage', cat='Airside', max=8, cost=2_600_000, bearing=164, dist=820, desc='Baies, glycol et équipes de dégivrage.', prereq=None),
    dict(code='FUEL', name='Fuel farm & hydrants', cat='Airside', max=10, cost=3_400_000, bearing=190, dist=980, desc='Stockage carburant, hydrants et rapidité de ravitaillement.', prereq=None),
    dict(code='PUSHBACK', name='Flotte pushback', cat='Airside', max=10, cost=650_000, bearing=216, dist=600, desc='Tracteurs et équipes de repoussage.', prereq=None),
    dict(code='GROUND_FLEET', name='Véhicules de piste', cat='Airside', max=10, cost=900_000, bearing=238, dist=680, desc='Bus, GPU, escaliers, convoyeurs, loaders et véhicules de service.', prereq=None),

    dict(code='TERMINAL', name='Capacité terminal', cat='Terminal', max=20, cost=3_000_000, bearing=270, dist=350, desc='Surface, halls, salles d’embarquement et débit passagers.', prereq=None),
    dict(code='CHECKIN', name='Enregistrement', cat='Terminal', max=10, cost=750_000, bearing=286, dist=470, desc='Comptoirs, dépose bagage et traitement des pointes.', prereq='TERMINAL'),
    dict(code='SELFSERVICE', name='Bornes & self bag drop', cat='Terminal', max=10, cost=650_000, bearing=300, dist=520, desc='Automatisation de l’enregistrement et du dépôt bagages.', prereq='CHECKIN'),
    dict(code='BOARDING', name='Embarquement', cat='Terminal', max=10, cost=850_000, bearing=315, dist=520, desc='Portiques, files, priorités et embarquement biométrique.', prereq='TERMINAL'),
    dict(code='ARRIVALS', name='Arrivées', cat='Terminal', max=10, cost=900_000, bearing=332, dist=560, desc='Flux arrivées, carrousels et correspondances.', prereq='TERMINAL'),
    dict(code='BAGGAGE', name='Système bagages', cat='Terminal', max=15, cost=1_700_000, bearing=348, dist=650, desc='Tri, correspondances, fiabilité et bagages spéciaux.', prereq='TERMINAL'),
    dict(code='TOILETS', name='Toilettes & sanitaires', cat='Terminal', max=10, cost=350_000, bearing=7, dist=300, desc='Capacité, propreté, PMR, douches et maintenance.', prereq='TERMINAL'),
    dict(code='WIFI', name='Wi‑Fi & connectivité', cat='Terminal', max=10, cost=500_000, bearing=25, dist=315, desc='Couverture, débit, application et services connectés.', prereq='TERMINAL'),
    dict(code='SIGNAGE', name='Signalétique & orientation', cat='Terminal', max=10, cost=420_000, bearing=45, dist=330, desc='Wayfinding, écrans, multilingue et accessibilité.', prereq='TERMINAL'),

    dict(code='SECURITY', name='Sûreté', cat='Sécurité', max=12, cost=1_250_000, bearing=72, dist=340, desc='Scanners, files, inspection, contrôle d’accès et supervision.', prereq='TERMINAL'),
    dict(code='BORDER', name='Police aux frontières', cat='Sécurité', max=12, cost=1_500_000, bearing=88, dist=360, desc='Guichets, e-gates et traitement des flux internationaux.', prereq='SECURITY'),
    dict(code='CUSTOMS', name='Douanes', cat='Sécurité', max=10, cost=1_150_000, bearing=104, dist=385, desc='Contrôles douaniers, zones rouge/verte et flux cargo.', prereq='BORDER'),
    dict(code='FIRE', name='Pompiers aéroportuaires', cat='Sécurité', max=10, cost=3_200_000, bearing=132, dist=1250, desc='ARFF, véhicules mousse/eau et catégorie incendie.', prereq=None),
    dict(code='MEDICAL', name='Centre médical', cat='Sécurité', max=10, cost=1_250_000, bearing=150, dist=740, desc='Urgences, médical passagers et soutien opérationnel.', prereq=None),
    dict(code='CRISIS', name='Centre de crise', cat='Sécurité', max=8, cost=2_100_000, bearing=169, dist=700, desc='Coordination crise, continuité d’activité et redondance.', prereq='OPS'),

    dict(code='DUTYFREE', name='Duty Free', cat='Commercial', max=12, cost=1_100_000, bearing=206, dist=350, desc='Surface duty free, assortiment et revenus commerciaux.', prereq='TERMINAL'),
    dict(code='RETAIL', name='Galerie commerciale', cat='Commercial', max=12, cost=1_350_000, bearing=224, dist=390, desc='Boutiques, luxe, services et revenu au m².', prereq='TERMINAL'),
    dict(code='FOOD', name='Restauration', cat='Commercial', max=12, cost=950_000, bearing=242, dist=410, desc='Cafés, restauration rapide, restaurants et offre locale.', prereq='TERMINAL'),
    dict(code='HOTEL', name='Hôtel aéroportuaire', cat='Commercial', max=8, cost=4_800_000, bearing=255, dist=950, desc='Nuitées passagers, équipages et gestion des irrégularités.', prereq=None),
    dict(code='PARK_SHORT', name='Parking courte durée', cat='Commercial', max=12, cost=800_000, bearing=274, dist=920, desc='Parking visiteurs, dépose minute et revenus annexes.', prereq=None),
    dict(code='PARK_LONG', name='Parking longue durée', cat='Commercial', max=12, cost=1_100_000, bearing=290, dist=1250, desc='Parking longue durée avec navettes.', prereq='PARK_SHORT'),
    dict(code='PARK_PREM', name='Parking premium', cat='Commercial', max=10, cost=1_500_000, bearing=308, dist=900, desc='Voiturier, recharge EV et clientèle premium.', prereq='PARK_SHORT'),
    dict(code='TRANSIT', name='Hub transports terrestres', cat='Commercial', max=10, cost=2_600_000, bearing=325, dist=1050, desc='Bus, taxis, navettes, rail et intermodalité.', prereq=None),

    dict(code='LOUNGE_BUS', name='Lounge Business', cat='Premium', max=10, cost=1_300_000, bearing=343, dist=290, desc='Salon affaires, restauration, douches et espaces de travail.', prereq='TERMINAL'),
    dict(code='LOUNGE_FIRST', name='Lounge First', cat='Premium', max=10, cost=2_300_000, bearing=358, dist=285, desc='Suites, dining, spa, concierge et transfert premium.', prereq='LOUNGE_BUS'),
    dict(code='SLEEP', name='Suites & sleeping pods', cat='Premium', max=8, cost=1_450_000, bearing=17, dist=270, desc='Repos en correspondance et récupération équipages premium.', prereq='LOUNGE_BUS'),
    dict(code='FASTTRACK', name='Fast Track premium', cat='Premium', max=10, cost=850_000, bearing=35, dist=270, desc='Parcours premium sûreté/frontière/embarquement.', prereq='SECURITY'),

    dict(code='LINE_MAINT', name='Maintenance en ligne', cat='Technique', max=12, cost=1_700_000, bearing=60, dist=1120, desc='Transit checks, dépannage et petites réparations.', prereq=None),
    dict(code='HEAVY_MAINT', name='Hangars maintenance lourde', cat='Technique', max=10, cost=5_500_000, bearing=78, dist=1420, desc='Checks lourds, immobilisation et grands chantiers.', prereq='LINE_MAINT'),
    dict(code='PARTS', name='Stocks pièces', cat='Technique', max=10, cost=1_250_000, bearing=96, dist=1180, desc='Pièces critiques, consommables et logistique technique.', prereq='LINE_MAINT'),
    dict(code='CATERING', name='Centre catering', cat='Technique', max=12, cost=1_900_000, bearing=114, dist=1050, desc='Production repas, chaîne froide et chargement cabine.', prereq=None),
    dict(code='CABIN_SERVICE', name='Service à bord', cat='Technique', max=12, cost=1_150_000, bearing=132, dist=910, desc='Qualité du service, équipement cabine et turnaround.', prereq='CATERING'),
    dict(code='CLEANING', name='Nettoyage cabine', cat='Technique', max=10, cost=650_000, bearing=150, dist=860, desc='Équipes, rapidité de rotation et qualité cabine.', prereq=None),
    dict(code='CREW', name='Centre équipages', cat='Technique', max=12, cost=1_400_000, bearing=168, dist=860, desc='Briefing, repos, planning, transport et réserves.', prereq=None),
    dict(code='TRAINING', name='Centre de formation', cat='Technique', max=10, cost=3_900_000, bearing=185, dist=1200, desc='Simulateurs, formations types, instructeurs et PNC.', prereq='CREW'),
    dict(code='OPS', name='Operations Control Center', cat='Technique', max=12, cost=2_800_000, bearing=205, dist=780, desc='Dispatch, NOTAM, météo, recovery réseau et décisions automatiques.', prereq=None),

    dict(code='CARGO', name='Terminal cargo', cat='Cargo', max=15, cost=3_500_000, bearing=228, dist=1350, desc='Fret, palettes, ULD, express et capacité cargo.', prereq=None),
    dict(code='CARGO_COLD', name='Chaîne froide cargo', cat='Cargo', max=10, cost=1_900_000, bearing=246, dist=1500, desc='Pharma, alimentaire, température contrôlée.', prereq='CARGO'),
    dict(code='CARGO_EXPRESS', name='Hub express', cat='Cargo', max=10, cost=2_700_000, bearing=263, dist=1550, desc='Tri nocturne, express et rotations rapides.', prereq='CARGO'),
    dict(code='CARGO_HEAVY', name='Fret lourd / hors gabarit', cat='Cargo', max=8, cost=3_200_000, bearing=282, dist=1550, desc='Charges lourdes, équipements spéciaux et rampes.', prereq='CARGO'),

    dict(code='SUSTAIN', name='Énergie & durabilité', cat='Infrastructure', max=12, cost=1_500_000, bearing=302, dist=1450, desc='Électricité au sol, solaire, réduction bruit et émissions.', prereq=None),
    dict(code='WATER', name='Eau & utilités', cat='Infrastructure', max=10, cost=850_000, bearing=318, dist=1320, desc='Eau potable, eaux usées, réseau technique et résilience.', prereq=None),
    dict(code='IT', name='Systèmes IT aéroport', cat='Infrastructure', max=12, cost=1_250_000, bearing=336, dist=1080, desc='DCS, AODB, cyber, réseau et supervision temps réel.', prereq=None),
]
UPGRADE_BY_CODE = {x['code']: x for x in UPGRADES}


def now_utc():
    return datetime.now(timezone.utc)


def destination_point(lat, lon, bearing_deg, distance_m):
    R = 6371000.0
    br = math.radians(bearing_deg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    d = distance_m / R
    p2 = math.asin(math.sin(p1)*math.cos(d) + math.cos(p1)*math.sin(d)*math.cos(br))
    l2 = l1 + math.atan2(math.sin(br)*math.sin(d)*math.cos(p1), math.cos(d)-math.sin(p1)*math.sin(p2))
    return math.degrees(p2), ((math.degrees(l2)+540)%360)-180


def haversine_km(a_lat, a_lon, b_lat, b_lon):
    R=6371.0
    p1,p2=math.radians(a_lat),math.radians(b_lat)
    dp=math.radians(b_lat-a_lat); dl=math.radians(b_lon-a_lon)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))


def bearing_deg(a_lat,a_lon,b_lat,b_lon):
    p1=math.radians(a_lat); p2=math.radians(b_lat); dl=math.radians(b_lon-a_lon)
    y=math.sin(dl)*math.cos(p2)
    x=math.cos(p1)*math.sin(p2)-math.sin(p1)*math.cos(p2)*math.cos(dl)
    return (math.degrees(math.atan2(y,x))+360)%360


def interpolate_gc(lat1,lon1,lat2,lon2,t):
    # Spherical linear interpolation, stable enough for global airline routes.
    t=max(0.0,min(1.0,t))
    p1=math.radians(lat1); l1=math.radians(lon1); p2=math.radians(lat2); l2=math.radians(lon2)
    def vec(p,l): return [math.cos(p)*math.cos(l), math.cos(p)*math.sin(l), math.sin(p)]
    a=vec(p1,l1); b=vec(p2,l2)
    dot=max(-1,min(1,sum(x*y for x,y in zip(a,b))))
    w=math.acos(dot)
    if w<1e-8:
        return lat1,lon1
    s=math.sin(w)
    v=[math.sin((1-t)*w)/s*a[i]+math.sin(t*w)/s*b[i] for i in range(3)]
    lat=math.degrees(math.atan2(v[2], math.sqrt(v[0]*v[0]+v[1]*v[1])))
    lon=math.degrees(math.atan2(v[1],v[0]))
    return lat,lon


def upgrade_price(node, level):
    return int(round((node['cost'] * (1.34 ** level)) / 10_000) * 10_000)


def hub_level(levels):
    # Long-tail progression: 1..50, with later levels intentionally expensive in score.
    score=sum(levels.values())
    return min(50, 1 + int(math.sqrt(score) * 2.55))


def route_simulation(route_created_at, origin, destination, aircraft_spec):
    distance_km = haversine_km(origin['lat'],origin['lon'],destination['lat'],destination['lon'])
    cruise_kmh = max(180, aircraft_spec['cruise_kts'] * 1.852)
    airborne_min = max(18, (distance_km / cruise_kmh) * 60 + 10)

    # Fully repeating aircraft rotation. Same physical aircraft goes out and returns.
    phases = [
        ('turnaround_origin', 32),
        ('pushback_origin', 4),
        ('taxi_out_origin', 11),
        ('outbound', airborne_min),
        ('taxi_in_destination', 9),
        ('turnaround_destination', 38),
        ('pushback_destination', 4),
        ('taxi_out_destination', 11),
        ('inbound', airborne_min),
        ('taxi_in_origin', 9),
    ]
    cycle=sum(x[1] for x in phases)
    created=route_created_at
    if created.tzinfo is None:
        created=created.replace(tzinfo=timezone.utc)
    elapsed_real=max(0,(now_utc()-created).total_seconds())
    elapsed_sim=(elapsed_real*SIM_SPEED/60.0)%cycle
    cursor=0
    phase='turnaround_origin'; phase_p=0
    for name,dur in phases:
        if elapsed_sim < cursor+dur:
            phase=name; phase_p=(elapsed_sim-cursor)/dur if dur else 0
            break
        cursor+=dur

    airborne=phase in ('outbound','inbound')
    if phase=='outbound':
        lat,lon=interpolate_gc(origin['lat'],origin['lon'],destination['lat'],destination['lon'],phase_p)
        frm,to=origin,destination
        heading=bearing_deg(lat,lon,destination['lat'],destination['lon'])
        direction='out'
    elif phase=='inbound':
        lat,lon=interpolate_gc(destination['lat'],destination['lon'],origin['lat'],origin['lon'],phase_p)
        frm,to=destination,origin
        heading=bearing_deg(lat,lon,origin['lat'],origin['lon'])
        direction='back'
    elif 'destination' in phase:
        lat,lon=destination['lat'],destination['lon']; frm=to=destination; heading=0; direction='dest_ground'
    else:
        lat,lon=origin['lat'],origin['lon']; frm=to=origin; heading=0; direction='origin_ground'

    if airborne:
        climb = min(1.0, phase_p/0.13)
        descent = min(1.0, (1-phase_p)/0.15)
        alt_factor=min(climb,descent,1.0)
        altitude_ft=int(max(2500, alt_factor * min(41000, aircraft_spec.get('service_ceiling') or 39000)))
        speed_kts=int(aircraft_spec['cruise_kts'] * (0.68 if phase_p<0.12 or phase_p>0.88 else 1.0))
    elif 'taxi' in phase or 'pushback' in phase:
        altitude_ft=0; speed_kts=7 if 'pushback' in phase else 18
    else:
        altitude_ft=0; speed_kts=0

    # Fuel resets for each leg; purely operational indicator, not certified dispatch math.
    if phase=='outbound': fuel=max(12,int(100-phase_p*72))
    elif phase=='inbound': fuel=max(12,int(100-phase_p*72))
    elif 'destination' in phase: fuel=100
    else: fuel=100

    labels={
        'turnaround_origin':'À la porte', 'pushback_origin':'Pushback', 'taxi_out_origin':'Roulage départ',
        'outbound':'En vol', 'taxi_in_destination':'Roulage arrivée', 'turnaround_destination':'Escale / turnaround',
        'pushback_destination':'Pushback retour', 'taxi_out_destination':'Roulage retour', 'inbound':'En vol retour',
        'taxi_in_origin':'Roulage vers la porte'
    }
    return {
        'phase':phase,'status':labels[phase],'phase_progress':round(phase_p,4),'airborne':airborne,
        'direction':direction,'lat':lat,'lon':lon,'heading':heading,'altitude_ft':altitude_ft,'speed_kts':speed_kts,
        'fuel_percent':fuel,'distance_km':int(round(distance_km)),'airborne_minutes':int(round(airborne_min)),
        'cycle_minutes':int(round(cycle)),'from':frm['code'],'to':to['code'],
    }


def economy_per_leg(origin, destination, spec, reputation=50):
    d=haversine_km(origin['lat'],origin['lon'],destination['lat'],destination['lon'])
    seats=max(1,spec['seats'])
    airport_factor=(1.18 if destination.get('type')=='large_airport' else 1.0 if destination.get('type')=='medium_airport' else .72)
    rep_factor=.82+min(100,reputation)/100*0.25
    load=max(.45,min(.94,.62+airport_factor*.12+rep_factor*.08))
    pax=seats*load
    fare=55 + d*0.095
    revenue=pax*fare
    fuel_cost=(d/1000) * max(900, (spec.get('mtow_kg') or 60000)/65) * 0.82
    fees=1400+seats*8 + (2800 if destination.get('type')=='large_airport' else 900)
    crew=900 + d*0.18
    cost=fuel_cost+fees+crew
    profit=max(-50_000,revenue-cost)
    return {'load_factor':round(load,3),'passengers':int(round(pax)),'fare':round(fare,2),'revenue':round(revenue,2),'cost':round(cost,2),'profit':round(profit,2)}
