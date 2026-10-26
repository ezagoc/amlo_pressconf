"""Read-only roster/attendance audit. Inputs are review-mode R CSV snapshots."""
import json
import re
import unicodedata
import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('/Users/ezagoc/Dropbox/Media/data')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=ROOT / 'outputs/sheinbaum-roster-20261019')
OUT = parser.parse_args().output
OUT.mkdir(parents=True, exist_ok=True)

def key(value):
    if pd.isna(value):
        return ''
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', str(value).lower()).encode('ascii', 'ignore').decode())

q = pd.read_csv('/tmp/sheinbaum-current-mapped.csv')
a = pd.read_csv('/tmp/attendance-original.csv')
m = pd.read_excel(DATA / '00-newspaper_data/mexican_newspapers.xlsx', sheet_name='Periodicos')
metadata = pd.read_excel(DATA / '00-newspaper_data/newspaper_metadata.xlsx', sheet_name='Hoja1')
for registry in (m, metadata):
    if 'analysis_merged_into' in registry:
        registry.drop(registry.index[registry.analysis_merged_into.notna()], inplace=True)
for df, col in [(q, 'date'), (a, 'fecha')]:
    df[col] = pd.to_datetime(df[col], utc=True).dt.date.astype(str)
a['key'] = a.medios.map(key)
lookup = {}
for i, row in m.iterrows():
    for col in ['name.page', 'names.transcripts', 'names.conference', 'bene_final']:
        if key(row[col]):
            lookup.setdefault(key(row[col]), set()).add(i)

# Reviewed identity links, not fuzzy suggestions. Original IDs remain unchanged.
links = {
    'eli tv oficial': 'Eli Televisión',
    'noticias el reloj de la tlaxiaquena': 'Noticieros el Reloj de la Tlaxiaqueña',
    'movimiento conciencia': 'Movimiento Consciencia',
    'infobae mexico': 'infobae',
    'universidad de guadalajara': 'Canal Universidad de Guadalajara',
    'astillero informa': 'El Astillero',
    'canales norte (tijuana, juarez, etc)': 'Grupo Intermedia',
    'canal de las noticias': 'Grupo Intermedia',
    'mexico comunica': 'Tijuana Comunica',
    'aci': 'ACI de Hidalgo',
    'el debate': 'Debate Sinaloa',
    'alianza de medios independientes': 'Alianza de Medios (Pie de Pagina, Altavoz,…)',
}
extra = {
    'contralinea': ['CONTRALINEA. PERIODISMO DE INVESTIGACION'],
    'imagen del golfo': ['IMAGEN DEL GOLFO Y CANALES 33 Y 66 BAJA', 'IMAGEN DEL GOLFO Y CANALES 33 Y 66 BAJA CALIFORNIA', 'IMAGEN DEL GIOLFO Y CANALES 33 Y 66 BAJA CALIFORNIA'],
    'nacion 14': ['NACIÓN14.COM'],
    'maxima fm': ['MAXIMA FM/ CUARTO PODER'],
    'sin censura': ['SIN CENSURA MEDIA'],
    'noticias el reloj de la tlaxiaquena': ['NOTICIEROS EL RELOJ DE LA TLAXIAQUEÑA 9', 'NOTICIEROS EL RELOJ DE LA TLAXIAQUEÑA 91.5', 'NT EL RELOJ DE LA TLAXIAQUEÑA 91.5'],
    'es ahora am': ['ES AHORA AM NOTICIAS', 'JF INFORMA DESDE CANCÚN Y ESAHORAAM DE QUERÉTARO'],
    'business energy': ['BUSINESS ENERGY GACETA PETROLERA'],
    'reyna haydee (independiente)': ['REYNA HAYDEE RAMÍREZ HERNÁNDEZ'],
    'diario 24 horas': ['24 HORAS EL DIARIO SIN LÍMITES', 'DIARIO 24 HORAS EL DIARIO SIN LÍMITES', '24 HORAS/EL HERALDO QUINTANA ROO', '24 HORAS EL DIARIO SIN LÍMITES PUE', '24 HORAS PUEBLA', 'PERIÓDICO 24HORAS QUINTANA ROO'],
    'healy': ['GRUPO HEALY (EL IMPARCIAL, LA CR', 'GRUPO HEALY (FRONTERA, EL IMPARCIAL, LA', 'GRUPO HEALY (FRONTERA, EL IMPARCIAL, LA CRÓNICA)', 'LA CRÓNICA GRUPO HEALY', 'PERIÓDICO FRONTERA DE GRUPO HE', 'PERIÓDICO FRONTERA/GRUPO HEALY', 'PERIÓDICO FRONTERA', 'EL IMPARCIAL TIJUANA'],
    'efecto colateral': ['CHIWAS NEWS', 'EFECTO COLATERAL / EL CHAPUCERO'],
    'noticieros hctv': ['HCTV'],
    'subjetivo mx': ['SUBJETIVO', 'EL SUBJETIVO', 'SUBJETIVO 1'],
    'enlace 13 television': ['ENLACE 13', 'ENLACE 13 COAHUILA', 'ELACE 13 TELEVISIÓN'],
    'quequi': ['QUEQUI CDMX'],
    'bctneus': ['BCT NEUS', 'BCT NEWS'],
    'enprivadoveracruzcommx': ['EN PRIVADO VERACRUZ'],
    'radio tosepan limakxtum': ['RADIO TOSEPAN', 'LA RADIO TOSEPAN LIMAKXTUM'],
    'canal de las noticias': ['INTERMEDIA CANAL 44', 'CANAL 44 / XHIJ-TV / CD. JUÁREZ', 'CANAL 66', 'CANAL 66 MEXICALI'],
    'canales norte (tijuana, juarez, etc)': ['INTERMEDIA CANAL 44', 'CANAL 44 / XHIJ-TV / CD. JUÁREZ', 'CANAL 66', 'CANAL 66 MEXICALI'],
    'cnr canal 73': ['LÁNZATE CANAL 73', 'LÁNZATE CANAL 73 CNR CABLE IZZI BAJA CALIFORNIA MÉXICO', 'LÁNZATE CNR C. 73 CABLE BAJA CALI', 'LÁNZATE CNR C. 73 CABLE BAJA CALIF. MÉXICO'],
}
pending = {
    'poder mexico': 'PODER MX; PODER (not counted: incomplete names)',
    'pridemx': 'PRIDE (not counted: shortened name needs confirmation)',
    'chilango': 'CHILANGO NEWS (not counted: identity needs confirmation)',
    'radio hit la xplosiva': 'LIBERAL DEL SUR / RADIOHIT (not counted: joint label)',
    'capital': 'PORTAL CAPITAL; RED CAPITAL (not counted: ambiguous)',
    'fusion latina chicago': 'FUSIÓN LATINA (not counted: shortened name needs confirmation)',
    'reyna haydee (independiente)': 'INDEPENDIENTE (not counted: attendance has no journalist names)',
    'universidad de guadalajara': 'CANAL 44 (not counted: ambiguous with Intermedia)',
    'canales norte (tijuana, juarez, etc)': 'CANAL 44 (not counted: ambiguous with UDG)',
    'canal de las noticias': 'CANAL 44 (not counted: ambiguous with UDG)',
}
special = {
    'reyna haydee (independiente)': 'Independent journalist category, not an outlet. Her name appears in the media-label field; generic INDEPENDIENTE is not assigned to her.',
    'el regreso de donald trump': 'Program stated by Bertha Alicia Galindo. Decide whether separate from Alcanzando el Conocimiento.',
    'tv migrante': 'SPR channel; existing Canal 14 SPR category. Decide channel versus group unit.',
    'cultura colectiva': 'Explicitly introduced as Grupo Tribu; parent already listed. Decide title versus group unit.',
    'el fildeo': 'Explicitly introduced as Grupo Tribu; parent already listed. Decide title versus group unit.',
    'agora digital': 'Current user rule combines Agora (Celaya, Gabriela Montejano) and Agora Digital (Zacatecas, Gerardo Romo). Identity unresolved.',
    'associated press': 'Current user rule also maps AP Noticias (Alejandro Perez) here; verify that affiliation separately.',
    'lja': 'Historical La Jornada Aguascalientes name alone does not establish current group membership.',
}
deny = {key(x) for x in ['canal 44', 'fm', 'hc', 'independiente', 'mmm otros', 'oem otros']}
reviewed = pd.read_csv(ROOT / 'info_newspapers_gpt/attendance_aliases_20261016.tsv', sep='\t')
results = []
evidence = []
date_checks = []
focus = {'diario 24 horas', 'healy', 'domo de cristal', 'zagazine', 'subjetivo mx'}
period_start, period_end = '2024-10-01', a.fecha.max()
covered = set(a.loc[a.eligible_role == True, 'fecha'])
for outlet, g in q.dropna(subset=['outlet_aux']).groupby('outlet_aux'):
    days = g.date.nunique()
    if days < 2:
        continue
    ids = lookup.get(key(outlet), set())
    method = 'Exact existing label'
    if not ids and outlet in links:
        ids = set(m.index[m['name.page'].map(key) == key(links[outlet])])
        assert ids, (outlet, links[outlet])
        method = 'Existing outlet under another label'
    names = sorted(set(m.loc[list(ids), 'name.page'].dropna()))
    keys = {key(outlet)} | set(g.outlet_aux_before.dropna().map(key)) | {key(v) for v in extra.get(outlet, [])}
    for i in ids:
        keys.add(key(m.loc[i, 'names.conference']))
    canonical_keys = {key(outlet)} | {key(m.loc[i, 'names.transcripts']) for i in ids}
    keys |= set(reviewed.loc[(reviewed.status == 'reviewed') & reviewed.canonical_id.map(key).isin(canonical_keys), 'alias'].map(key))
    keys -= deny | {''}
    if outlet == 'revista zocalo':
        # The bare attendance label can also name the unrelated newspaper.
        keys.discard(key('ZÓCALO'))
    if outlet == 'healy':
        # Bare La Cronica / El Imparcial can refer to unrelated publishers.
        keys -= {key('LA CRÓNICA'), key('EL IMPARCIAL')}
    matched_all_roles = a[a.key.isin(keys)]
    matched = matched_all_roles[matched_all_roles.eligible_role == True]
    sheinbaum = matched[matched.fecha >= '2024-10-01']
    labels = sorted(matched.medios.unique())
    tdates = set(g.date)
    in_period = {d for d in tdates if period_start <= d <= period_end}
    same_day = tdates & set(sheinbaum.fecha)
    unmatched_covered = (in_period & covered) - same_day
    status = method if ids else ('Review analysis unit' if outlet in special else 'Missing from roster')
    # Metadata presence is checked independently of the linked master roster.
    meta_names = set(metadata['name.page'].dropna().map(key))
    meta_hit = bool(({key(outlet)} | {key(v) for v in names}) & meta_names)
    row = {
        'Outlet': outlet, 'Transcript dates': int(days), 'Roster status': status,
        'Existing entry': '; '.join(names),
        'Attendance dates 2024-25': int(sheinbaum.fecha.nunique()),
        'Attendance dates all years': int(matched.fecha.nunique()),
        'Attendance result': 'Found in Sheinbaum period' if len(sheinbaum) else ('Found only before Sheinbaum' if len(matched) else ('Possible label; unresolved' if outlet in pending else 'No verified label found')),
        'First transcript date': min(tdates), 'Last transcript date': max(tdates),
        'Transcript dates with attendance source': len(tdates & covered),
        'Same-day attendance matches': len(tdates & set(sheinbaum.fecha)),
        'Transcript dates in attendance period': len(in_period),
        'Transcript dates after attendance period': sum(d > period_end for d in tdates),
        'Unmatched dates with attendance source': len(unmatched_covered),
        'Unmatched dates': '; '.join(sorted(unmatched_covered)),
        'Attendance labels': '; '.join(labels),
        'Possible labels not counted': pending.get(outlet, ''),
        'Reporters': '; '.join(sorted(g.reporter_aux.dropna().unique())),
        'Metadata entry found': meta_hit,
        'Notes': special.get(outlet, '') + (' Existing raw aliases matched; joint labels represent co-affiliation, not extra attendees.' if any('/' in x for x in labels) else ''),
    }
    results.append(row)
    for d in sorted(in_period):
        if outlet in focus or d in unmatched_covered:
            intro = g[g.date == d].iloc[0]
            records = sheinbaum[sheinbaum.fecha == d]
            date_checks.append({'Outlet': outlet, 'Date': d,
                'Result': 'Matched' if d in same_day else ('No matched attendance' if d in covered else 'No attendance source for date'),
                'Raw attendance labels': '; '.join(sorted(records.medios.unique())),
                'Attendance source files': '; '.join(sorted(records.source_file.dropna().unique())),
                'Reporter': None if pd.isna(intro.reporter_aux) else intro.reporter_aux,
                'Introduction': intro.evidence_text, 'Transcript source': intro.source_url})
    for _,r in g.drop_duplicates(['date','reporter_aux','evidence_text']).iterrows():
        if status != 'Exact existing label':
            evidence.append({'Outlet':outlet,'Date':r.date,'Reporter':None if pd.isna(r.reporter_aux) else r.reporter_aux,'Introduction':r.evidence_text,'Source':r.source_url})

results.sort(key=lambda r: (-r['Transcript dates'],r['Outlet']))
summary = pd.DataFrame(results)
payload = {'rows':results,'evidence':evidence,'date_checks':date_checks,'coverage':{'transcripts':[q.date.min(),q.date.max()], 'attendance':[a.fecha.min(),a.fecha.max()]},'counts':summary['Roster status'].value_counts().to_dict()}
(OUT/'audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))
print(json.dumps(payload['counts']))
print(summary[summary['Roster status'].isin(['Missing from roster','Review analysis unit'])][['Outlet','Transcript dates','Roster status','Attendance dates 2024-25','Attendance dates all years','Attendance result']].to_string(index=False))
assert len(results)==len({r['Outlet'] for r in results})
assert all(r['Same-day attendance matches']<=r['Transcript dates with attendance source']<=r['Transcript dates'] for r in results)
