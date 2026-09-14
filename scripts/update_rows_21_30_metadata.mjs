import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputPath = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata/newspaper_metadata.xlsx";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");
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
}

const centerUnclearLow = {
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
};

setRowByName("Aguas", {
  "CVE_ENT": 1,
  "coverage.scope": "state",
  "address": "Quinta Avenida No. 101, Fracc. Las Américas, CP 20230, Aguascalientes, Aguascalientes",
  "city.headq": 1,
  "legal_name": "Empresa Editorial de Aguascalientes, S.A. de C.V.",
  "owner_group": "Hidrocálido / Empresa Editorial de Aguascalientes",
  "year_founded": 2000,
  ...centerUnclearLow,
  "ideology.source": "https://aguasdigital.com/aviso-legal/; https://aguasdigital.com/aviso-de-privacidad/; https://www.mpm.com.mx/?id=2000648B-0C20-027C-CFAB-899D094AE780&r=periodico%2Fview",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Hidrocálido", {
  "CVE_ENT": 1,
  "coverage.scope": "state",
  "address": "Quinta Avenida 101, Fracc. Las Américas, CP 20230, Aguascalientes, Aguascalientes",
  "city.headq": 1,
  "legal_name": "Empresa Editorial de Aguascalientes, S.A. de C.V.",
  "owner_group": "Hidrocálido / Empresa Editorial de Aguascalientes",
  "founder.name": "Agustín Morales Padilla",
  "year_founded": 1981,
  ...centerUnclearLow,
  "ideology.source": "https://www.hidrocalidodigital.com/quienes-somos/; https://www.hidrocalidodigital.com/politica-privacidad/; https://www.hidrocalidodigital.com/aviso-legal/",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Frontera", {
  "CVE_ENT": 2,
  "coverage.scope": "state",
  "address": "Vía Rápida Poniente #13483, Col. Anexa 20 de Noviembre, Tijuana, Baja California",
  "city.headq": 2,
  "legal_name": "Impresora y Editorial, S.A. de C.V.",
  "owner.person": "Juan F. Healy Loera",
  "owner.family": "Familia Healy",
  "owner_group": "Grupo Healy",
  "year_founded": 1999,
  ...centerUnclearLow,
  "ideology.source": "https://www.elimparcial.com/tijuana/pages/directorio/; https://www.elimparcial.com/tij/tijuana/2025/07/29/frontera-crece-con-tijuana/",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("La Crónica Mexicali, El Imparcial", {
  "CVE_ENT": 2,
  "coverage.scope": "state",
  "address": "Av. Héroes de la Patria No. 952, Centro Cívico, Mexicali, Baja California",
  "city.headq": 2,
  "legal_name": "Impresora y Editorial, S.A. de C.V.",
  "owner.person": "Juan F. Healy Loera",
  "owner.family": "Familia Healy",
  "owner_group": "Grupo Healy",
  "year_founded": 1990,
  ...centerUnclearLow,
  "ideology.source": "https://www.elimparcial.com/mexicali/pages/directorio/; https://www.elimparcial.com/mxl/mexicali/2015/11/17/la-cronica-sigue-firme-luis-alejandro-bernal-director-gral/; https://www.elimparcial.com/mxl/mexicali/2019/11/04/cumple-la-cronica-29-anos-informando-a-los-cachanillas/",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Diario de México", {
  "CVE_ENT": 9,
  "coverage.scope": "state, national",
  "address": "Chimalpopoca 38, Col. Obrera, Cuauhtémoc, CP 06800, Ciudad de México",
  "city.headq": 9,
  "legal_name": "Editorial DDM, S.A. de C.V.",
  "owner_group": "Diario de México",
  "year_founded": 1949,
  ...centerUnclearLow,
  "ideology.source": "https://www.diariodemexico.com/aviso-legal.html; https://edictos.diariodemexico.com/avisodeprivacidad/",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Diario de Chiapas", {
  "CVE_ENT": 7,
  "coverage.scope": "state",
  "address": "4a. Oriente Sur No. 1850, CP 29080, Tuxtla Gutiérrez, Chiapas",
  "city.headq": 7,
  "owner.person": "Gerardo Toledo Coutiño",
  "owner.family": "Familia Toledo Coutiño",
  "owner_group": "Diario Media Group",
  "founder.name": "Enrique Toledo Esponda",
  "year_founded": 1975,
  ...centerUnclearLow,
  "ideology.source": "https://diariodechiapas.com/directorio/; https://www.chiapas.gob.mx/funcionarios/social/prensa-local; https://diariodechiapas.com/metropoli/diario-de-chiapas50-anos-informando/",
  "type.media": "periodico",
  "platform": "print, digital, radio, tv, social media",
});

setRowByName("El Orbe", {
  "municipality": "Tapachula",
  "CVE_ENT": 7,
  "coverage.scope": "regional",
  "address": "Av. Antonio Damiano Cajas Mz. M, altos 2, Fracc. Insurgentes, CP 30750, Tapachula, Chiapas",
  "city.headq": 7,
  "legal_name": "Editora Zamora Cruz, S.A. de C.V.",
  "owner.person": "Enrique Zamora Cruz",
  "owner.family": "Familia Zamora Cruz",
  "founder.name": "Juan Zamora Velázquez",
  ...centerUnclearLow,
  "ideology.source": "https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=94; https://www.jornada.com.mx/2005/10/28/index.php?article=014n3soc&section=sociedad; https://embed-rech-01.dialog.cm/elorbe/docs/27052026",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("El Diario de Ciudad Delicias", {
  "CVE_ENT": 8,
  "coverage.scope": "regional",
  "city.headq": 8,
  "legal_name": "Publicaciones del Chuviscar, S.A. de C.V.",
  "owner.person": "Osvaldo Rodríguez Borunda",
  "owner_group": "El Diario",
  ...centerUnclearLow,
  "ideology.source": "https://eldiariodedelicias.mx/pagina/quienes-somos.html; https://eldiariodedelicias.mx/pagina/politica-de-privacidad.html; https://www.mpm.com.mx/?id=F0BCF0FC-1478-B6FF-2CFB-6765F88A8A39&r=periodico%2Fview",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("El Diario de Chihuahua", {
  "CVE_ENT": 8,
  "coverage.scope": "state",
  "address": "Av. Universidad 1900, Col. San Felipe, CP 31240, Chihuahua, Chihuahua",
  "city.headq": 8,
  "legal_name": "Publicaciones del Chuviscar, S.A. de C.V.",
  "owner.person": "Osvaldo Rodríguez Borunda",
  "owner_group": "El Diario",
  "year_founded": 1985,
  ...centerUnclearLow,
  "ideology.source": "https://www.eldiariodechihuahua.mx/pages/directorio.html; https://sic.gob.mx/ficha.php?table=impresos&table_id=98; https://www.eldiariodechihuahua.mx/estado/2026/feb/17/el-diario-50-anos-de-historia-en-la-frontera-772524.html",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("El Diario Juárez", {
  "municipality": "Ciudad Juárez",
  "CVE_ENT": 8,
  "coverage.scope": "state",
  "address": "Av. Paseo Triunfo de la República No. 3505, Zona Pronaf, CP 32315, Ciudad Juárez, Chihuahua",
  "city.headq": 8,
  "legal_name": "Publicaciones e Impresos Paso del Norte, S. de R.L. de C.V.",
  "owner.person": "Osvaldo Rodríguez Borunda",
  "owner_group": "El Diario",
  "year_founded": 1976,
  ...centerUnclearLow,
  "ideology.source": "https://diario.mx/pagina/politica-de-privacidad.html; https://eldiariodedelicias.mx/pagina/quienes-somos.html; https://www.eldiariodechihuahua.mx/estado/2026/feb/17/el-diario-50-anos-de-historia-en-la-frontera-772524.html",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

await fs.mkdir("C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata", { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(outputPath);
