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

setRowByName("El Guardián Saltillo", {
  "CVE_ENT": 5,
  "coverage.scope": "regional",
  "address": "Blvd. Venustiano Carranza y Chiapas No. 1918, CP 25280, Saltillo, Coahuila",
  "city.headq": 5,
  "legal_name": "Grupo Editorial de Coahuila, S.A. de C.V.",
  "owner.person": "Armando Castilla Galindo",
  "owner.family": "Familia Castilla",
  "owner_group": "Vanguardia",
  "year_founded": 1976,
  ...centerUnclearLow,
  "ideology.source": "https://www.mpm.com.mx/?id=ED30275F-9DAC-F0F1-71DD-36DFF0C4A328&r=periodico%2Fview; https://vanguardia.com.mx/coahuila/saltillo/2714643-reganan-medicos-del-hospital-general-FPVG2714643; https://vanguardia.com.mx/aviso-de-privacidad",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("La Prensa de Coahuila", {
  "CVE_ENT": 5,
  "coverage.scope": "state",
  "address": "Ermita No. 318-A, Centro, CP 25700, Monclova, Coahuila",
  "city.headq": 5,
  "owner.person": "Melchor Sánchez de la Fuente",
  "owner.family": "Familia Sánchez Campos",
  "owner_group": "La Prensa de Coahuila",
  "year_founded": 2005,
  ...centerUnclearLow,
  "ideology.source": "https://www.mpm.com.mx/?id=2F72A6EB-5012-C485-E188-6AEF81D7AB3D&r=periodico%2Fview; https://laprensadecoahuila.com.mx/2021/11/14/el-festejo-por-nuestros-16-anos/; https://laprensadecoahuila.com.mx/politicas-de-privacidad/",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Vanguardia", {
  "CVE_ENT": 5,
  "coverage.scope": "state",
  "address": "Boulevard Venustiano Carranza 1918, Col. República Oriente, CP 25280, Saltillo, Coahuila",
  "city.headq": 5,
  "legal_name": "Grupo Editorial de Coahuila, S.A. de C.V.",
  "owner.person": "Armando Castilla Galindo",
  "owner.family": "Familia Castilla",
  "owner_group": "Vanguardia",
  "founder.name": "Armando Castilla Sánchez",
  "year_founded": 1975,
  ...centerUnclearLow,
  "ideology.source": "https://vanguardia.com.mx/aviso-de-privacidad; https://redespoder.com/destacadas/coahuilaleaks-ruben-moreira-el-gran-hermano-encabeza-gasto-nacional-de-publicidad-en-2017/; https://www.noroeste.com.mx/nacional/unen-voces-contra-ataques-a-vanguardia-HYNO1024740",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Diario de Colima", {
  "CVE_ENT": 6,
  "coverage.scope": "state",
  "address": "Av. 20 de Noviembre 580, Col. San Pablo, CP 28060, Colima, Colima",
  "city.headq": 6,
  "legal_name": "Editora Diario de Colima, S.A. de C.V.",
  "owner_group": "Gati, S.A. de C.V.",
  ...centerUnclearLow,
  "ideology.source": "https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=145; https://diariodecolima.com/noticias/detalle/2024-05-18-diario-de-colima-tiene-nuevo-director-concelo-aqu",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("La Jornada Estado de México", {
  "CVE_ENT": 15,
  "coverage.scope": "state",
  "address": "Calle González Arratia 102, Col. San Sebastián, Toluca, Estado de México, CP 50000",
  "city.headq": 15,
  "legal_name": "Demos, Desarrollo de Medios, S.A. de C.V.",
  "owner.person": "Carmen Lira Saade",
  "owner_group": "La Jornada",
  "founder.name": "Carlos Payán Velver",
  "ideology.leftright": "left",
  "ideology.4t": "unclear",
  "ideology.confidence": "medium",
  "ideology.source": "https://lajornadaestadodemexico.com/directorio/; https://www.jornada.com.mx/pagina/aviso-legal; https://mexico.mom-gmr.org/en/media/detail/outlet/la-jornada-1/; https://www.jornada.com.mx/noticia/2025/05/26/columnas/dinero-66401",
  "type.media": "periodico",
  "platform": "digital, social media",
});

setRowByName("El Sur de Acapulco", {
  "CVE_ENT": 12,
  "coverage.scope": "state",
  "city.headq": 12,
  "owner.person": "Juan Angulo Osorio",
  "owner_group": "El Sur",
  "founder.name": "Juan Angulo Osorio",
  "year_founded": 1993,
  "ideology.leftright": "left",
  "ideology.4t": "unclear",
  "ideology.confidence": "medium",
  "ideology.source": "https://suracapulco.mx/archivoelsur/directorio; https://suracapulco.mx/en-conversatorio-de-el-sur-llama-musacchio-a-una-politica-institucional-en-publicidad/; https://la-republica-de-las-letras.webnode.mx/republicas/",
  "type.media": "periodico",
  "platform": "digital, social media",
});

setRowByName("Criterio", {
  "CVE_ENT": 13,
  "coverage.scope": "state",
  "address": "Av. Juárez No. 1012, Col. Maestranza, CP 42060, Pachuca de Soto, Hidalgo",
  "city.headq": 13,
  "legal_name": "Grupo Impresor Criterio, S.A. de C.V.",
  "owner.person": "Gerardo Márquez",
  "owner_group": "Grupo Criterio",
  ...centerUnclearLow,
  "ideology.source": "https://criteriohidalgo.com/aviso-de-privacidad; https://www.mpm.com.mx/?id=07F7CC1B-3B34-DA21-C54D-906AE1BD36CB&r=periodico%2Fview",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("Diario de los Altos de Jalisco", {
  "CVE_ENT": 14,
  "coverage.scope": "regional",
  "city.headq": 14,
  "owner.person": "Luis Jesús Ramírez Jiménez",
  "owner_group": "Diario de los Altos de Jalisco",
  ...centerUnclearLow,
  "ideology.source": "https://diariodelosaltos.com.mx/directorio/; https://diariodelosaltos.com.mx/aviso-de-privacidad/",
  "type.media": "periodico",
  "platform": "digital, social media",
});

setRowByName("El Informador", {
  "CVE_ENT": 14,
  "coverage.scope": "state",
  "address": "Independencia No. 300, Col. Centro, CP 44100, Guadalajara, Jalisco",
  "city.headq": 14,
  "legal_name": "Unión Editorialista, S.A. de C.V.",
  "owner.person": "Juan Carlos Álvarez del Castillo",
  "owner.family": "Familia Álvarez del Castillo",
  "owner_group": "El Informador",
  "founder.name": "Jesús Álvarez del Castillo",
  "year_founded": 1917,
  ...centerUnclearLow,
  "ideology.source": "https://www.informador.mx/pages/politicas-de-privacidad.html; https://www.informador.mx/Una-historia-en-cuatro-generaciones-Don-Jesus-l201710040010.html; https://www.informador.mx/El-Informador-testigo-y-participe-de-la-historia-de-Jalisco-Mexico-y-el-mundo-l202310050005.html",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

setRowByName("La Voz de Michoacán", {
  "CVE_ENT": 16,
  "coverage.scope": "state",
  "address": "Av. Periodismo José Tocavén Lavín No. 1270, Col. Agustín Arriaga Rivera, CP 58190, Morelia, Michoacán",
  "city.headq": 16,
  "legal_name": "La Voz de Michoacán, S.A. de C.V.",
  "owner.person": "Álvaro Medina González",
  "owner_group": "La Voz de Michoacán",
  "year_founded": 1948,
  ...centerUnclearLow,
  "ideology.source": "https://www.lavozdemichoacan.com.mx/aviso-legal/; https://www.mpm.com.mx/index.php?id=F6D25D88-9F8E-9074-E902-445654EB800C&r=periodico%2Fview; https://sd.lavozdemichoacan.com.mx/subscribe/impreso-digital-suplementos-digitales",
  "type.media": "periodico",
  "platform": "print, digital, social media",
});

await fs.mkdir("C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata", { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(outputPath);
