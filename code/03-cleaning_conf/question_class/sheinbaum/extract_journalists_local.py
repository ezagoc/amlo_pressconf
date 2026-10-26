"""Export transcript-reviewed journalist/outlet introductions without an API.

The TSV ledger is the source of inclusion decisions. Outlet spellings are
matched only inside reviewed evidence, never transferred between dates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import pandas as pd
from prepare import DEFAULT_ROOT, atomic_json

HERE = Path(__file__).resolve().parent

# Conservative spellings observed in the reviewed transcript introductions.
# Parent groups and individual titles remain distinct when both are stated.
MEDIA = {
'Instituto Mexicano de la Radio': r'instituto mexicano de la radio|\bimer\b',
'Medios Unidos de Comunicación de Chiapas': r'medios unidos de comunicacion de chiapas',
'Telesur': r'telesur',
'JF Informa': r'jf informa',
'Frecuencia CAD': r'frecuencia\s*cad(?:\.com)?',
'EsAhoraAM': r'es\s*ahora\s*am',
'Somos Más': r'somos mas',
'Diario Plaza Juárez': r'diario plaza juarez',
'Red de Periodistas Enlace Mexamerica': r'red de periodistas enlace mexamerica',
'La Jornada': r'la jornada(?! del campo)',
'QuintanaRooMX': r'quintana\s*roo\s*[, .]*mx',
'NotiCabo': r'noticabo',
'Cabo Visión TV': r'cabo vision\.?\s*tv',
'24 Horas': r'24 horas',
'Publimetro': r'publimetro(?: mexico)?',
'POPLab': r'poplab|laboratorio de periodismo y opinion publica',
'El Chapucero': r'(?:el )?chapucero',
'Efecto Colateral': r'efecto colateral',
'Grupo Imagen': r'grupo imagen',
'Canal 14 SPR': r'canal 14(?:\s*[, ]*spr)?|spr canal 14',
'Altavoz Radio': r'altavoz radio',
'TV Migrante': r'tv migrante',
'Radio Educación': r'radio educacion',
'Nación 14': r'nacion 14',
'Cuatro Media Telecomunicaciones': r'(?:cuatro|quatro)\s*media(?: telecomunicaciones)?',
'AVA Noticias': r'ava noticias',
'El Heraldo Media Group': r'(?:el )?heraldo media group',
'LM Noticias': r'lm noticias|informativo lm',
'ADN 40': r'adn\s*40',
'Bajo Palabra': r'bajo palabra',
'Noticias de Frente': r'noticias\s*de\s*frente(?:\.com)?',
'Noticieros': r'\bnoticieros\b(?! el reloj| en redes)',
'Polemón': r'polemon',
'Reporte Los Cabos': r'reporte los cabos',
'Proceso': r'\bproceso\b',
'Animal Político': r'animal politico',
'Helios Comunicación': r'helios comunicacion',
'Agencias de Información y Opinión': r'agencias de informacion y opinion',
'Periodismo Internacional Alternativo': r'periodismo internacional alternativo',
'Portal Alba': r'portal alba',
'Rebelión': r'\brebelion\b',
'Poder México': r'poder mexico',
'Global Energy': r'global energy',
'Sputnik': r'sputnik',
'Pie de Página': r'pie de pagina',
'Diario Red': r'diario red',
'Sonora Power': r'sonora power',
'Lobos Cadena 7': r'lobos cadena 7',
'México al Minuto': r'mexico al minuto',
'Huellas de México': r'huellas de mexico',
'El Financiero': r'(?:el )?financiero(?: bloomberg)?',
'La Hoguera': r'la hoguera',
'Eli TV Oficial': r'eli tv oficial',
'Noticias del Movimiento Consciencia': r'noticias del movimiento con[sc]*iencia',
'Iztaccíhuatl en el Sendero de la Luna': r'iztaccihuatl en el sendero de la luna',
'Animales con Derechos': r'animales con derechos',
'Vanguardia Veracruz': r'vanguardia(?:\s*,?\s*veracruz)?',
'Associated Press': r'\bap\b|associated press',
'Infobae México': r'infobae(?: mexico)?',
'Grupo Siete Noticias': r'grupo siete noticias',
'Grupo Milenio': r'(?:grupo )?milenio',
'Diario Imagen': r'diario imagen',
'Comunicante MX': r'comunicante\s*mx',
'Noticiero en Redes': r'noticiero(?:s)? en redes',
'Instituto Estatal de Radio y Televisión': r'instituto estatal de radio y television',
'Radio Puntos Suspensivos Comunicación': r'(?:radio )?puntos suspensivos(?: comunicacion)?',
'Grupo Fórmula': r'grupo formula',
'Grupo ACIR': r'grupo acir',
'Grupo Transmedia': r'grupo transmedia',
'La Chispa': r'la chispa',
'HCTV Noticias': r'\bhctv(?: noticias)?|\bhc\b',
'Revolución 3.0': r'revolucion 3\.0',
'Máxima FM': r'maxima fm',
'Cuarto Poder': r'cuarto poder(?: de chiapas)?',
'Ruido en la Red': r'ruido en la red',
'Lánzate Canal 73': r'lanzate canal 73',
'Capital 21': r'capital 21',
'Voces del Periodista': r'voces del periodista',
'Siker': r'\bsiker\b',
'Transmitiendo desde la Frontera': r'transmitiendo desde la frontera',
'Diario Basta': r'(?:diario )?basta',
'Tabasco Hoy': r'tabasco hoy',
'Campeche Hoy': r'campeche hoy',
'Quintana Roo Hoy': r'quintana roo hoy',
'Grupo Cantón': r'grupo canton',
'Perspectivas MX': r'perspectivas\s*mx',
'Sin Puntos ni Comas': r'sin puntos,? ni comas',
'Medios Digitales del Pacífico': r'medios? digitales del pacifico',
'julioomargs.com': r'julioomargs\.com',
'Canal Once': r'canal once|(?<=del )once\b|(?<=de )once\b',
'Reporte Índigo': r'reporte indigo',
'Los Angeles Times': r'los angeles times',
'MVS Noticias': r'mvs(?: noticias)?(?: los cabos)?',
'Eclipse Baja California Sur': r'eclipse baja california sur',
'Pulso Saludable': r'pulso saludable',
'ATiempo.com.mx': r'atiempo\.com\.mx',
'Puente Libre': r'puente\s*libre(?:\s*mx)?',
'Astillero Informa': r'astillero informa',
'RT en Español': r'\brt en espanol',
'Los Reporteros MX': r'los reporteros\s*mx',
'Radio Resultados': r'radio resultados',
'Sin Línea': r'sin linea',
'El Político en las Redes': r'el politico en las redes',
'Infopolitano': r'infopolitano',
'Enfoque Noticias': r'enfoque noticias',
'NRM': r'\bnrm\b',
'Hidalgo News': r'hidalgo news',
'México News World': r'(?:mexico )?news world',
'Albavisión': r'albavision(?: canal 13)?',
'El Soberano': r'el soberano',
'Contralínea': r'contralinea',
'Sin Embargo': r'sin embargo(?: mx)?',
'Oro Sólido': r'oro solido',
'Empuje Migrante': r'empuje migrante',
'Diario del Istmo': r'(?:el )?diario del istmo',
'Imagen de Veracruz': r'imagen[,]? de veracruz',
'Imagen del Golfo': r'imagen,? del golfo|corporativo imagen,? del golfo',
'Zagazine': r'zagazine',
'El Deforma': r'(?:el )?deforma',
'SDPNoche': r'sdpnoche',
'Centinela Informa': r'centinela informa',
'The Human Hoy': r'the human hoy',
'Noticieros El Reloj': r'noticieros el reloj',
'Radio Relax 104.5 FM': r'(?:radio )?relax 104\.5 fm(?: noticias)?',
'enprivadoveracruz.com.mx': r'enprivadoveracruz\.com\.mx',
'TeleUrban': r'teleurban',
'W Radio': r'w radio',
'NX Noticias': r'nx noticias',
'El Universal': r'el universal',
'AE Grupo Informativo': r'ae grupo informativo',
'Grupo Larsa Comunicaciones': r'grupo larsa comunicaciones',
'sandraaguilera.com': r'sandraaguilera\.com',
'ECOS Media México': r'ecos media (?:mexico|mx)',
'Luces del Siglo': r'luces de[l]? siglo',
'El Nopal Times': r'(?:el )?nopal times',
'Polo Puga': r'polo puga',
'El Charro Político': r'(?:el )?charro politico',
'Grupo Healy': r'grupo healy',
'El Imparcial de Sonora': r'el imparcial(?:,? de sonora)?',
'La Crónica de Mexicali': r'la cronica(?:,? de mexicali)?',
'Frontera de Tijuana': r'frontera,? de tijuana',
'Radio Universidad de Guadalajara': r'radio universidad de guadalajara',
'Canal 44': r'canal 44',
'Red Periodística de Puerto Vallarta': r'red periodistica(?: de puerto vallarta)?',
'Ángulo 7': r'angulo 7',
'Canal de las Noticias': r'canal de las noticias',
'Grupo Intermedia': r'grupo intermedia',
'Canal 33': r'(?:canal|el) 33',
'Canal 66': r'(?:canal|el) 66',
'El Sudcaliforniano': r'el sudcaliforniano',
'Once Digital': r'once digital',
'Sin Censura': r'sin censura(?: tv)?',
'Vittor Blogs': r'vittor blogs',
'México Informa': r'mexico informa',
'México Comunica': r'mexico comunica',
'Tijuana Comunica': r'tijuana comunica',
'Xinhua': r'xinhua',
'Fortuna': r'(?:revista )?fortuna',
'Business Energy': r'business energy',
'Enfoque Oportuno': r'enfoque oportuno',
'La Razón': r'la razon',
'Código Libre': r'codigo libre',
'MxFlorida.com': r'mxflorida\.com',
'El Reportero Urbano': r'el reportero urbano',
'Canal 5 TV': r'canal 5 tv',
'Yo También': r'yo tambien',
'Chiwas News': r'chiwas news',
'ABC Australia': r'abc australia',
'Reforma': r'\breforma\b',
# Additional outlet-only introductions.
'Bloomberg Línea': r'bloomberg linea',
'Bloomberg News': r'bloomberg news',
'Posta Ciudad de México': r'posta ciudad de mexico',
'El Sol de México': r'el sol de mexico',
'Miled México': r'miled mexico',
'Ahora Noticias': r'ahora noticias',
'Domo de Cristal': r'domo de cristal',
'La Pancarta de Quintana Roo': r'la pancarta(?: de quintana roo)?',
'AguaQuemada.mx': r'aguaquemada\.mx',
'Los Tubos.com': r'los tubos\.com',
'Postdata.com': r'postdata\.com',
'El Debate': r'(?:el )?debate',
'Código Rojo': r'codigo rojo',
'Radio Turquesa': r'radio turquesa',
'Radio Tepoztlán': r'radio tepoztlan',
'Rompeviento TV': r'rompeviento\s*tv',
'El Heraldo USA': r'el heraldo usa',
'La Jornada del Campo': r'la jornada del campo',
'Alerta Multimedio': r'alerta multimedio',
'Tiempo.com.mx': r'(?<!a)tiempo\.com\.mx',
'Once Noticias': r'once noticias(?! digital)',
'Once Noticias Digital': r'once noticias digital',
'Asociación Mundial de Radios Comunitarias': r'asociacion mundial de radios comunitarias',
'Política y Rock and Roll Radio': r'politica y rock and roll radio',
'Reuters': r'reuters',
'Acapulco al Tanto': r'acapulco al tanto',
'SDP Noticias': r'sdp\s*noticias',
'Vive la Noticia': r'vive la noticia',
'Máxima': r'maxima(?! fm)',
'Radio Tosepan Limakxtum': r'radio tosepan limakxtum',
'Ya es Noticia México': r'ya es noticia mexico',
'Voces de Radio': r'voces de radio',
'Voces Diario': r'voces diario',
'Luces Mañaneras': r'luces mananeras',
}


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')


def normalize(text, digits=False):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9\s]' if digits else r'[^a-z\s]', '', fold(text))).strip()


def media_matches(text):
    text = ' '.join(text.split())
    normalized = fold(text)
    found=[]
    for outlet, pattern in MEDIA.items():
        match=re.search(r'(?<!\w)(?:'+pattern+r')(?!\w)',normalized)
        if match:
            found.append((outlet,text[match.start():match.end()],match.start()))
    return sorted(found,key=lambda x:x[2])


def export(root):
    source=pd.read_parquet(root/'auxiliar/transcript_rows.parquet').set_index(['date','source_row'])
    ledger=pd.read_csv(HERE/'reviewed_introductions.tsv',sep='\t',keep_default_na=False)
    extra=HERE/'reviewed_outlet_only.tsv'
    if extra.exists():
        ledger=pd.concat([ledger,pd.read_csv(extra,sep='\t',keep_default_na=False)],ignore_index=True).fillna('')
    records=[]
    for row in ledger.itertuples():
        date=pd.Timestamp(row.date)
        numbers=[int(n) for n in str(row.evidence_rows).split(';')]
        paragraphs=[source.loc[(date,n),'text'] for n in numbers]
        evidence='\n'.join(paragraphs)
        if hashlib.sha256(evidence.encode()).hexdigest()!=row.evidence_sha256:
            raise ValueError(f'Source changed; re-review {row.date}:{row.source_row}')
        # Inclusion and affiliations are explicitly reviewed in the ledger.
        # The dictionary only checks support and retrieves the raw spelling.
        wanted=row.outlets.split('|') if row.outlets else []
        matches=[m for m in media_matches(evidence) if m[0] in wanted]
        if {m[0] for m in matches} != set(wanted):
            raise ValueError(f'Reviewed outlet not supported by evidence at {row.date}:{row.source_row}')
        for outlet,raw,_ in matches or [(None,None,None)]:
            records.append({'date':date,'reporter':row.reporter or None,
                'outlet':outlet,'reporter_aux':normalize(row.reporter) if row.reporter else None,
                'outlet_aux':normalize(outlet,True) if outlet else None,
                'no_outlet_flag':outlet is None,'no_reporter_flag':not bool(row.reporter),
                'name_status':row.name_status,'source_row':row.source_row,
                'outlet_status':('not_stated' if outlet is None else
                    'ambiguous_label_as_transcribed' if outlet in ['Noticieros','Máxima','HCTV Noticias'] else 'stated_in_transcript'),
                'source_rows':str(row.evidence_rows),'outlet_as_written':raw,
                'evidence_text':evidence,'source_path':source.loc[(date,numbers[0]),'source_path'],
                'extraction_method':'transcript_review_no_api'})
    evidence=pd.DataFrame(records).sort_values(['date','source_row','outlet'],na_position='last')
    output=root/'auxiliar'
    evidence.to_parquet(output/'journalist_media_evidence.parquet',index=False)
    evidence.to_csv(output/'journalist_media_evidence.csv',index=False)
    # Repeated self-introductions on the same day are not extra appearances.
    evidence['appearance_key']=evidence.reporter_aux.fillna('not_stated')
    daily=evidence.drop_duplicates(['date','appearance_key','outlet_aux']).drop(columns='appearance_key')
    daily.to_parquet(output/'periodistas_v2_all_years.parquet',index=False)
    daily.to_csv(output/'journalists_and_media.csv',index=False)
    daily[daily.no_reporter_flag | daily.no_outlet_flag | daily.name_status.eq('partial_name') |
          daily.outlet_status.eq('ambiguous_label_as_transcribed')].to_csv(output/'journalists_media_review.csv',index=False)
    pairs=daily.dropna(subset=['reporter']).groupby(['reporter','reporter_aux','outlet','outlet_aux'],dropna=False).agg(
        n_conference_days=('date','nunique'),first_date=('date','min'),last_date=('date','max')).reset_index()
    pairs.to_csv(output/'journalist_media_directory.csv',index=False)
    outlets=daily.dropna(subset=['outlet']).groupby(['outlet','outlet_aux']).agg(n_conference_days=('date','nunique'),
        n_named_reporters=('reporter_aux','nunique'),first_date=('date','min'),last_date=('date','max')).reset_index()
    outlets.to_csv(output/'media_directory.csv',index=False)
    manifest=pd.read_csv(output/'conference_manifest.csv',parse_dates=['date'])
    coverage=daily.groupby('date').agg(n_records=('outlet','size'),n_named_reporters=('reporter_aux','nunique'),
        n_outlets=('outlet_aux','nunique'),n_outlet_only_records=('no_reporter_flag','sum')).reset_index()
    coverage=manifest[['date','n_question_rows']].merge(coverage,on='date',how='left').fillna(0)
    coverage.to_csv(output/'journalist_media_coverage.csv',index=False)
    report={'method':'Transcript-reviewed introductions; no API calls',
        'n_records':len(daily),'n_evidence_records':len(evidence),'n_conference_dates':daily.date.nunique(),
        'n_source_conferences':len(manifest),'n_reporter_name_forms':daily.reporter_aux.nunique(),
        'n_outlet_labels':daily.outlet_aux.nunique(),'n_outlet_only_records':int(daily.no_reporter_flag.sum()),
        'n_records_without_outlet':int(daily.no_outlet_flag.sum()),
        'limitations':['Explicit self-identifications/outlet introductions only; this is not a complete attendance census.',
        'Missing names are not imputed from other dates. Partial names and transcript spellings are retained.',
        'Name forms may refer to the same person; observed daily combinations are not counts of distinct attendees.',
        'Parent media groups and individual titles are separate labels when both are stated.',
        'No political alignment, news context, or individual question classification was performed.']}
    atomic_json(output/'journalist_media_report.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,default=DEFAULT_ROOT)
    args=parser.parse_args()
    export(args.output_root)
