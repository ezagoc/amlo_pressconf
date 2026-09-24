import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("Hoja1");

const range = sheet.getRange("A1:AB90");
const values = range.values;
const headers = values[0];

for (let i = 1; i < values.length; i++) {
  const row = values[i];
  const name = row[0];
  if (!name) continue;
  const obj = {
    excelRow: i + 1,
    name,
    url: row[1],
    state: row[2],
    municipality: row[3],
    legal_name: row[10],
    owner_person: row[11],
    owner_group: row[15],
    year_founded: row[21],
    ideology_lr: row[22],
    ideology_4t: row[23],
    confidence: row[24],
    type_media: row[26],
    platform: row[27],
  };
  console.log(JSON.stringify(obj));
  if (String(name).toLowerCase().includes("opinion") && String(name).toLowerCase().includes("veracruz")) {
    break;
  }
}
