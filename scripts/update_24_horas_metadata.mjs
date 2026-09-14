import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputPath = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata/newspaper_metadata.xlsx";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");

const headers = sheet.getRange("A1:AB1").values[0];
const col = Object.fromEntries(headers.map((name, index) => [name, index]));
const data = sheet.getRange("A1:AB246").values;

function setRowByName(name, values) {
  const rowIndex = data.findIndex((row, index) => index > 0 && row[col["name.page"]] === name);
  if (rowIndex < 0) {
    throw new Error(`Row not found: ${name}`);
  }
  const row = [...data[rowIndex]];
  for (const [key, value] of Object.entries(values)) {
    if (!(key in col)) {
      throw new Error(`Column not found: ${key}`);
    }
    row[col[key]] = value;
  }
  sheet.getRangeByIndexes(rowIndex, 0, 1, headers.length).values = [row];
}

const legalName = "Información Integral 24/7, S.A.P.I. de C.V.";
const ownerGroup = "24 Horas";

setRowByName("24 Horas el Diario sin Límites", {
  "CVE_ENT": 9,
  "coverage.scope": "national",
  "address": "Ejército Nacional No. 216, Piso 13, Colonia Anzures, Alcaldía Miguel Hidalgo, CP 11590, CDMX",
  "city.headq": 9,
  "legal_name": legalName,
  "owner_group": ownerGroup,
  "founder.name": "Antonio Torrado Monge",
  "year_founded": 2011,
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
  "ideology.source": "https://24-horas.mx/directorio/; https://24-horas.mx/aviso-de-privacidad/; https://24-horas.mx/columnas/alhajero-el-dia-que-nacio-24-horas/",
  "type.media": "periodico",
  "platform": "print, digital, social media"
});

setRowByName("24 Horas el Diario sin Límites Puebla", {
  "CVE_ENT": 21,
  "coverage.scope": "state",
  "city.headq": 21,
  "legal_name": legalName,
  "owner_group": ownerGroup,
  "year_founded": 2015,
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
  "ideology.source": "https://24horaspuebla.com/directorio/; https://24horaspuebla.com/2020/07/24-horas-puebla-cierra-un-ciclo-y-en-breve-arranca-nuevo-proyecto-periodistico/; https://24-horas.mx/columnas/refundacion/",
  "type.media": "periodico",
  "platform": "print, digital, social media"
});

setRowByName("24 Horas el Diario sin Límites Quintana Roo", {
  "CVE_ENT": 23,
  "coverage.scope": "state",
  "address": "Plaza México, Local 309, SM 4, Mz. 16, lote 2 al 16, Avenida Tulum, CP 77500, Cancún, Quintana Roo",
  "city.headq": 23,
  "legal_name": legalName,
  "owner_group": ownerGroup,
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
  "ideology.source": "https://24horasqroo.mx/directorio/; https://24horasqroo.mx/category/videos/",
  "type.media": "periodico",
  "platform": "print, digital, social media"
});

setRowByName("24 Horas el Diario sin Límites Campeche", {
  "CVE_ENT": 4,
  "coverage.scope": "state",
  "city.headq": 4,
  "legal_name": legalName,
  "owner_group": ownerGroup,
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
  "ideology.source": "https://24horascampeche.mx/; https://24-horas.mx/columnas/refundacion/",
  "type.media": "periodico",
  "platform": "digital, social media"
});

setRowByName("24 Horas el Diario sin Límites Yucatan", {
  "CVE_ENT": 31,
  "coverage.scope": "state",
  "address": "Calle 15 del Fraccionamiento Altabrisa, piso 9 oficina 901, Mérida, Yucatán",
  "city.headq": 31,
  "legal_name": legalName,
  "owner_group": ownerGroup,
  "ideology.leftright": "center",
  "ideology.4t": "unclear",
  "ideology.confidence": "low",
  "ideology.source": "https://24horasyucatan.mx/directorio/; https://24horasyucatan.mx/contacto/",
  "type.media": "periodico",
  "platform": "print, digital, social media"
});

await fs.mkdir("C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata", { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
console.log(outputPath);
