"""Back up current review inputs and stage explicit outlet-review decisions."""
from pathlib import Path
import json,shutil,hashlib
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/flagged-outlets-20261026';BACK=ROOT/'recovery/flagged-outlets-20261026'
OUT.mkdir(exist_ok=True);(OUT/'staged').mkdir(exist_ok=True);BACK.mkdir(parents=True,exist_ok=True)
files=['info_newspapers_gpt/attendance_aliases_20261016.tsv','info_newspapers_gpt/question_aliases_20261016.tsv','code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R','src/metadata_helpers.R','tests/test_reviewed_outlet_linkage.R','info_newspapers_gpt/outlet_expansion_20261016.json','info_newspapers_gpt/outlet_review_20261016/youtube_extraction_manifest.json','info_newspapers_gpt/outlet_review_20261016/youtube_review.csv','outputs/sheinbaum-roster-20261019/sheinbaum_outlet_attendance_review.xlsx']
if not (BACK/'manifest.json').exists():
 manifest=[]
 for source in [ROOT/f for f in files]+[Path('/Users/ezagoc/Dropbox/Media/data/00-newspaper_data')/f for f in ['mexican_newspapers.xlsx','newspaper_metadata.xlsx']]:
  dest=BACK/source.name;shutil.copy2(source,dest);manifest.append(dict(source=str(source),backup=str(dest),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
 (BACK/'manifest.json').write_text(json.dumps(manifest,indent=2))
config=OUT/'decisions.json'
if not config.exists():
 config.write_text(json.dumps({'groups':[
 {'canonical':'medios digitales del pacifico','brands':['sin puntos ni comas','medios digitales del pacifico'],'metadata_names':['Sin Puntos Ni Comas','Medios Digitales del Pacifico','Informando la Transformación'],'basis':'User approved 2026-10-26; Julio Omar Gomez jointly identifies both; 8/8 Sin Puntos dates match.'},
 {'canonical':'movimiento conciencia','brands':['movimiento conciencia','animales con derechos','sendero de la luna'],'metadata_names':['Movimiento Consciencia','Animales con Derechos','Iztaccihuatl en el sendero de la luna'],'basis':'User approved 2026-10-26; Elideth Fernandez joint introductions; 5/6 covered dates match, 2024-11-08 unmatched.'},
 {'canonical':'sonora power','brands':['sonora power','lobos cadena 7'],'metadata_names':['Sonora Power','Lobos Cadena 7'],'basis':'User approved 2026-10-26; Demian Duarte joint introductions; 5/5 Lobos dates match.'},
 {'canonical':'comunicante mx','brands':['comunicante mx','alerta multimedia'],'metadata_names':['Comunicante MX','Alerta Multimedia'],'basis':'User approved 2026-10-26; Gustavo/Gus Garcia joint introductions; 5/5 Alerta dates match.'}
 ],'aliases':{},'notes':{}},ensure_ascii=False,indent=2)+'\n')
print('Backups and explicit decision registry ready.')
