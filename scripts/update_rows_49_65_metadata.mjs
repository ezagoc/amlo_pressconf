import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata";
const outputPath = `${outputDir}/newspaper_metadata.xlsx`;

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");

await fs.mkdir(outputDir, { recursive: true });
const before = await workbook.render({ sheetName: "Hoja1", range: "A49:AB65", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_49_65_before.png`, new Uint8Array(await before.arrayBuffer()));

const values = sheet.getRange("A1:AB246").values;
const headers = values[0];
const col = Object.fromEntries(headers.map((name, index) => [name, index]));

function setRowByName(name, updates) {
  const rowIndex = values.findIndex((row, index) => index > 0 && row[col["name.page"]] === name);
  if (rowIndex < 0) throw new Error(`Row not found: ${name}`);
  const row = [...values[rowIndex]];
  for (const [key, value] of Object.entries(updates)) {
    if (!(key in col)) throw new Error(`Column not found: ${key}`);
    row[col[key]] = value;
  }
  sheet.getRangeByIndexes(rowIndex, 0, 1, headers.length).values = [row];
  values[rowIndex] = row;
}

const centerUnclearLow = {
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
};

setRowByName("San Luis Hoy", {
  "municipality": "San Luis Potosi",
  "CVE_ENT": 24,
  "coverage.scope": "regional",
  "address": "Independencia No. 1205, Centro Historico, C.P. 78000, San Luis Potosi, S.L.P.",
  "city.headq": 24,
  "legal_name": "Editora de Medios Impresos, S.A. de C.V.",
  "owner.person": "Miguel Valladares Garcia / Pablo Valladares Garcia",
  "owner.family": "Familia Valladares Garcia / Valladares",
  "owner_group": "Grupo Pulso / Editora de Medios Impresos",
  "conglomerate": "Grupo Pulso",
  "founder.name": "Miguel Roman Valladares Garcia",
  "year_founded": 1993,
  ...centerUnclearLow,
  "ideology.source": "https://sanluishoy.com.mx/directorio/; https://sanluishoy.com.mx/bitacora/bitacora-17-de-marzo/48555/; https://www.pulsoslp.com.mx/slp/pulso-diario-de-san-luis-llego-para-quedarse-valladares/2080877; https://www.mexico.mom-gmr.org/en/owner/companies/detail/company/company/show/sin-embargo-s-de-rl-de-cv/",
  "type.media": "periodico",
});

setRowByName("El Debate Sinaloa", {
  "municipality": "Culiacan",
  "CVE_ENT": 25,
  "coverage.scope": "state",
  "address": "Blvd. Francisco I. Madero 555 Pte., Col. Centro, C.P. 80000, Culiacan, Sinaloa",
  "city.headq": 25,
  "legal_name": "Empresas El Debate, S.A. de C.V.",
  "owner.person": "Luis Javier Salido Artola",
  "owner.family": "Familia Salido Artola",
  "owner_group": "Grupo El Debate / Empresas El Debate",
  "conglomerate": "Grupo El Debate",
  "founder.name": "Manuel Moreno Rivas",
  "year_founded": 1941,
  ...centerUnclearLow,
  "ideology.source": "https://www.debate.com.mx/pages/quienes-somos.html; https://www.debate.com.mx/site/nuestros-principios.html; https://www.debate.com.mx/pages/aviso-de-privacidad.html; https://sic.gob.mx/ficha.php?table=impresos&table_id=175",
  "type.media": "periodico",
});

setRowByName("El Imparcial de Sonora", {
  "municipality": "Hermosillo",
  "CVE_ENT": 26,
  "coverage.scope": "state",
  "address": "Sufragio Efectivo y Mina No. 71, Col. Centro, C.P. 83000, Hermosillo, Sonora",
  "city.headq": 26,
  "legal_name": "Impresora y Editorial, S.A. de C.V.",
  "owner.person": "Juan Fernando Healy Loera",
  "owner.family": "Familia Healy",
  "owner_group": "Grupo Healy",
  "conglomerate": "Grupo Healy",
  "founder.name": "Jose Abraham Mendivil Rincon",
  "year_founded": 1937,
  ...centerUnclearLow,
  "ideology.source": "https://www.elimparcial.com/pages/nuestra-empresa/; https://www.elimparcial.com/son/sonora/2022/05/09/nace-una-historia-de-periodismo/; https://www.elimparcial.com/son/sonora/2024/05/01/celebra-el-imparcial-87-anos-de-logros-y-con-nuevos-desafios/",
  "type.media": "periodico",
});

setRowByName("Tribuna", {
  "municipality": "Cajeme / Ciudad Obregon",
  "CVE_ENT": 26,
  "coverage.scope": "regional",
  "address": "Rodolfo Elias Calles No. 278, Col. Campestre, C.P. 85160, Ciudad Obregon, Sonora",
  "city.headq": 26,
  "legal_name": "Tribuna del Yaqui, S.A. de C.V.",
  "owner.person": "Sergio Garcia",
  "owner.family": "Familia Felix Escalante / Felix Bours",
  "owner_group": "Tribuna Sonora",
  "conglomerate": null,
  "year_founded": 1965,
  ...centerUnclearLow,
  "ideology.source": "https://mpm.sizq.net/?id=4BD4E251-2D6E-C5C5-2930-EB68837C0AA8&r=periodicoInternet%2Fview; https://tribuna.com.mx/; https://revistacronica10.blogspot.com/2012/11/; https://www.primeraplanadigital.com.mx/de-primera-mano-536/",
  "type.media": "periodico",
});

setRowByName("El Diario de Sonora", {
  "municipality": "Nogales",
  "CVE_ENT": 26,
  "coverage.scope": "regional",
  "address": "Blvd. Luis Donaldo Colosio No. 3163 Sur, Col. El Greco, C.P. 84094, Nogales, Sonora",
  "city.headq": 26,
  "legal_name": "Editorial Diario de la Frontera, S.A. de C.V.",
  "owner.person": "Mario de la Fuente Manriquez / Lorenzo de la Fuente Barreda",
  "owner.family": "Familia De la Fuente",
  "owner_group": "El Diario de Sonora / MAS Medios Nogales",
  "conglomerate": "MAS Medios Nogales",
  "founder.name": "Luis Orduno",
  "year_founded": 1991,
  ...centerUnclearLow,
  "ideology.source": "https://eldiariodesonora.com.mx/empresa; https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=380; https://eldiariodesonora.com.mx/el-diario-de-sonora-cumple-30-anos-de-informar; https://www.infocajeme.com/general/2026/01/cierran-el-periodico-impreso-diario-de-la-frontera/",
  "type.media": "periodico",
});

setRowByName("Diario Avance Tabasco", {
  "CVE_ENT": 27,
  "coverage.scope": "state",
  "address": "Jose Pages Llergo No. 116 esq. Sanchez Magallanes, Col. Nueva Villahermosa, C.P. 86070, Villahermosa, Tabasco",
  "city.headq": 27,
  "owner.person": "Ignacio Cobo Gonzalez",
  "owner.family": "Familia Cobo",
  "owner_group": "Sistema Informativo de Tabasco",
  "conglomerate": "Sistema Informativo de Tabasco",
  "founder.name": "Fernando Alcala Bates",
  "year_founded": 1971,
  ...centerUnclearLow,
  "ideology.source": "https://diarioavancetabasco.com/?p=422846; https://www.diariopresente.mx/elsoldelsureste/partido-aniversario-entre-payasos-y-musicos/436473; https://www.diariopresente.mx/tabasco/trabajo-en-equipo-en-cobertura-del-sit/327199; https://fliphtml5.com/tfthn/wsib/Martes_31_de_diciembre_del_2024/",
  "type.media": "periodico",
});

setRowByName("El Sol del Sureste", {
  "CVE_ENT": 27,
  "coverage.scope": "state",
  "address": "Jose Pages Llergo No. 116 esq. Sanchez Magallanes, Col. Nueva Villahermosa, C.P. 86070, Villahermosa, Tabasco",
  "city.headq": 27,
  "legal_name": "Sistema Informativo de Tabasco",
  "owner.person": "Ignacio Cobo Gonzalez",
  "owner.family": "Familia Cobo",
  "owner_group": "Sistema Informativo de Tabasco / Diario Presente",
  "conglomerate": "Sistema Informativo de Tabasco",
  "founder.name": "Mary Fe Diaz Izquierdo",
  "year_founded": 2001,
  ...centerUnclearLow,
  "ideology.source": "https://www.mpm.com.mx/?id=B9FF6A01-BF0E-6FDB-41BC-AE5893D8BF2F&r=periodico%2Fview; https://www.diariopresente.mx/elsoldelsureste/trayectoria-editorial-25-anos-el-sol-del-sureste/464122; https://www.diariopresente.mx/elsoldelsureste/el-sol-del-sureste-25-anos-de-liderazgo-en-tabasco/464193; https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=217",
  "type.media": "periodico",
});

setRowByName("El Bravo de Matamoros", {
  "CVE_ENT": 28,
  "coverage.scope": "regional",
  "address": "Primera y Morelos No. 129, Zona Centro, C.P. 87300, Heroica Matamoros, Tamaulipas",
  "city.headq": 28,
  "legal_name": "Compania Periodistica del Bravo, S.A. de C.V.",
  "owner.person": "Jose Carretero Balboa",
  "owner.family": "Familia Carretero",
  "owner_group": "El Bravo de Matamoros",
  "conglomerate": null,
  "founder.name": "Gregorio Garza Flores",
  "year_founded": 1951,
  ...centerUnclearLow,
  "ideology.source": "https://www.elbravo.mx/politica-de-cookies-ue/; https://www.elbravo.mx/noticiero-102/; https://fliphtml5.com/ldht/dgny/El_Bravo_%7C_08211976/18/; https://www.dnb.com/business-directory/company-profiles.compa%C3%B1%C3%ADa_period%C3%ADstica_del_bravo_sa_de_cv.7aaeee2e8f4a4233ed6ea2ab1387cd05.html",
  "type.media": "periodico",
});

setRowByName("El Mañana", {
  "CVE_ENT": 28,
  "coverage.scope": "regional",
  "address": "Matias Canales 504, Col. Riberena, C.P. 88620, Reynosa, Tamaulipas",
  "city.headq": 28,
  "legal_name": "Editora DEMAR, S.A. de C.V.",
  "owner.person": "Orlando Tomas Deandar Martinez / Heriberto Cesar Deandar Martinez",
  "owner.family": "Familia Deandar",
  "owner_group": "El Manana / Editora DEMAR",
  "conglomerate": "Editora DEMAR",
  "founder.name": "Heriberto Eustagio Deandar Amador",
  "year_founded": "1932 Nuevo Laredo; 1949 Reynosa",
  ...centerUnclearLow,
  "ideology.source": "https://www.elmanana.com/contenido/informacioninstitucional-2504.html; https://elmanana.azurewebsites.net/directorio; https://sic.gob.mx/ficha.php?table=impresos&table_id=251; https://www.elmanana.com/opinion/editoriales/generaciones-dan-continuidad-a-el-manana-6130963.html",
  "type.media": "periodico",
});

setRowByName("Expreso", {
  "municipality": "Ciudad Victoria",
  "CVE_ENT": 28,
  "coverage.scope": "state",
  "city.headq": 28,
  "owner.person": "Pedro Alfonso Garcia Hernandez",
  "owner_group": "Grupo Editorial Expreso-La Razon",
  "conglomerate": "Grupo Editorial Expreso-La Razon",
  "founder.name": "Pedro Alfonso Garcia Hernandez; Francisco Cuellar Cardona; Victor Contreras",
  "year_founded": 1995,
  ...centerUnclearLow,
  "ideology.source": "https://expreso.press/2025/02/27/expreso-una-larga-historia-de-exito/; https://expreso.press/tamaulipas/; https://www.jornada.com.mx/noticia/2022/06/29/estados/asesinan-a-antonio-de-la-cruz-periodista-critico-al-gobierno-de-tamaulipas-1455; https://expreso.press/2026/09/09/la-palabra-tambien-es-contrapeso/",
  "type.media": "periodico",
});

setRowByName("Hora Cero Tamaulipas", {
  "municipality": "Reynosa",
  "CVE_ENT": 28,
  "coverage.scope": "regional",
  "address": "Carretera Riberena Km. 3.5 Local 1, Col. Rancho Grande, C.P. 88610, Reynosa, Tamaulipas",
  "city.headq": 28,
  "legal_name": "Editora Hora Cero, S.A. de C.V.",
  "owner.person": "Heriberto Deandar Robinson",
  "owner.family": "Familia Deandar",
  "owner_group": "Grupo Verbo Libre Editores / Hora Cero",
  "conglomerate": "Grupo Verbo Libre Editores",
  "founder.name": "Heriberto Deandar Robinson",
  "year_founded": 1998,
  ...centerUnclearLow,
  "ideology.source": "https://horacero.com.mx/nosotros; https://horacero.com.mx/aviso-legal; https://horacero.com.mx/aviso-de-privacidad; https://sic.gob.mx/ficha.php?table=impresos&table_id=255; https://horacerotam.com/local/una-empresa-con-raices-fuertes-y-muy-profundas/",
  "type.media": "periodico",
});

setRowByName("La Tarde de Reynosa", {
  "CVE_ENT": 28,
  "coverage.scope": "municipal",
  "address": "Matias Canales 504, Col. Riberena, C.P. 88620, Reynosa, Tamaulipas",
  "city.headq": 28,
  "legal_name": "Editora DEMAR, S.A. de C.V.",
  "owner.person": "Orlando Deandar Ayala",
  "owner.family": "Familia Deandar",
  "owner_group": "El Manana / Editora DEMAR",
  "conglomerate": "Editora DEMAR",
  "founder.name": "Heriberto Eustagio Deandar Amador",
  "year_founded": 1971,
  ...centerUnclearLow,
  "ideology.source": "https://fliphtml5.com/pvjh/zgas/LAT20160713/; https://elmanana.azurewebsites.net/directorio; https://www.elmanana.com/visitan-el-manana-de-reynosa/3492053; https://portalanterior.ine.mx/archivos2/portal/EncuestasElectorales/EleccionesFederales/2005-2006/EncuestasEntregadas/",
  "type.media": "periodico",
});

setRowByName("Imagen del Golfo", {
  "municipality": "Xalapa / Veracruz",
  "CVE_ENT": 30,
  "coverage.scope": "state",
  "address": "Concepcion Beistegui 107, Col. Del Valle, C.P. 03100, Benito Juarez, Ciudad de Mexico",
  "city.headq": 30,
  "legal_name": "Imagen del Golfo Multimedios, S.A. de C.V.",
  "owner.person": "Jose Pablo Robles Martinez",
  "owner.family": "Familia Robles Barajas / Robles Hillman",
  "owner_group": "Corporativo Imagen del Golfo",
  "conglomerate": "Corporativo Imagen del Golfo",
  "founder.name": "Jose Pablo Robles Martinez",
  ...centerUnclearLow,
  "ideology.source": "https://imagendelgolfo.mx/pages/directorio.html; https://imagendelgolfo.mx/pages/aviso.html; https://veracruz.articulo19.org/sector-privado-medios/; https://imagendelgolfo.mx/estado/imagen-del-golfo-se-consolida-como-lider-digital-20260529-0114.html",
  "type.media": "periodico",
});

setRowByName("Diario del Istmo", {
  "municipality": "Coatzacoalcos",
  "CVE_ENT": 30,
  "coverage.scope": "regional",
  "address": "Av. Miguel Hidalgo No. 1115, Col. Centro, C.P. 96400, Coatzacoalcos, Veracruz",
  "city.headq": 30,
  "legal_name": "Editora La Voz del Istmo, S.A. de C.V.",
  "owner.person": "Hector Robles Barajas",
  "owner.family": "Familia Robles Barajas / Robles Hillman",
  "owner_group": "Corporativo Imagen del Golfo",
  "conglomerate": "Corporativo Imagen del Golfo",
  "founder.name": "Ruben Pabello Rojas",
  "year_founded": 1979,
  ...centerUnclearLow,
  "ideology.source": "https://pemc.veracruz.gob.mx/medio-comunicacion/voz-en-libertad-imagen-de-veracruz/; https://diariodelistmo.com/coatzacoalcos/Diario-del-Istmo-45-aniversario-conoce-la-historia-de-este-medio-en-casi-cinco-decadas-de-vida-20240325-0054.html; https://www.mpm.com.mx/?id=16860ECC-E023-F28A-332A-753EC280556C&r=periodicoInternet%2Fview; https://veracruz.articulo19.org/sector-privado-medios/",
  "type.media": "periodico",
});

setRowByName("Imagen de Veracruz", {
  "municipality": "Boca del Rio / Veracruz",
  "CVE_ENT": 30,
  "coverage.scope": "state",
  "address": "Blvd. Adolfo Ruiz Cortines 1917, Col. Jardines de Virginia, C.P. 94294, Boca del Rio, Veracruz",
  "city.headq": 30,
  "legal_name": "Editora La Voz del Istmo, S.A. de C.V.",
  "owner.person": "Jose Pablo Robles Martinez",
  "owner.family": "Familia Robles Barajas / Robles Hillman",
  "owner_group": "Corporativo Imagen del Golfo",
  "conglomerate": "Corporativo Imagen del Golfo",
  "founder.name": "Jose Pablo Robles Martinez",
  ...centerUnclearLow,
  "ideology.source": "https://imagendeveracruz.mx/contacto; https://sic.gob.mx/ficha.php?table=impresos&table_id=287; https://imagendeveracruz.mx/veracruz/Construyen-alianzas-estrategicas-los-lideres-Imagen-de-Veracruz-y-Grupo-Pazos-20241218-0053.html; https://veracruz.articulo19.org/sector-privado-medios/",
  "type.media": "periodico",
});

setRowByName("La Opinión de Poza Rica", {
  "CVE_ENT": 30,
  "coverage.scope": "regional",
  "address": "Mariano Arista No. 209, Col. Tajin, C.P. 93330, Poza Rica de Hidalgo, Veracruz",
  "city.headq": 30,
  "legal_name": "Editorial Gibb, S.A. de C.V.",
  "owner.person": "Gonzalo Hernandez Gibb / Norma Arango Gibb",
  "owner.family": "Familia Gibb",
  "owner_group": "La Opinion de Poza Rica / Editorial Gibb",
  "conglomerate": null,
  "founder.name": "Raul Gibb Quintero; Margarita Guerrero de Gibb",
  "year_founded": 1953,
  ...centerUnclearLow,
  "ideology.source": "https://www.mpm.com.mx/?id=D0D855BA-BB09-2384-8ECE-EA39212BB756&r=periodicoInternet%2Fview; https://sic.gob.mx/ficha.php?table=impresos&table_id=293; https://laopinion.net/70-anos-de-periodismo-responsable/; https://veracruzdelossilencios.org/sector-privado-medios",
  "type.media": "periodico",
});

setRowByName("La Opinión de Veracruz", {
  "municipality": "Minatitlan",
  "CVE_ENT": 30,
  "coverage.scope": "regional",
  "city.headq": 30,
  "owner.family": "Familia Rodriguez Jara / Rodriguez Ladron de Guevara",
  "owner_group": "La Opinion de Minatitlan / La Opinion de Veracruz",
  "conglomerate": null,
  "founder.name": "Manuel Rodriguez Olan",
  "year_founded": 1934,
  ...centerUnclearLow,
  "ideology.source": "https://www.laopiniondeveracruz.com/; https://fliphtml5.com/ivector/gpvf/LA_OPINION_1_15_DE_DICIEMBRE_DE_2024/2/; https://fliphtml5.com/ivector/qlva/18_de_octubre_de_2025_la_opinion/; https://notimina.com/secciones/local/el-diario-la-opinion-de-minatitlan-estaria-cumpliendo-90-anos-de-existencia/; https://enlaceveracruz212.com.mx/nota.php?id=62577",
  "type.media": "periodico",
});

const check = await workbook.inspect({
  kind: "table",
  range: "Hoja1!A49:AB65",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 28,
  tableMaxCellChars: 90,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const after = await workbook.render({ sheetName: "Hoja1", range: "A49:AB65", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_49_65_after.png`, new Uint8Array(await after.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(outputPath);
