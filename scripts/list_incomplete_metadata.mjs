import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItem("Hoja1");
const values = sheet.getRange("A1:AB246").values;
const headers = values[0];
const col = Object.fromEntries(headers.map((name, index) => [name, index]));

for (let i = 1; i < values.length; i++) {
  const row = values[i];
  const name = row[col["name.page"]];
  if (!name) continue;
  const keyFields = [
    "coverage.scope",
    "legal_name",
    "owner.person",
    "owner_group",
    "year_founded",
    "ideology.leftright",
    "ideology.4t",
    "ideology.confidence",
    "ideology.source",
    "platform",
  ];
  const blanks = keyFields.filter((field) => row[col[field]] === null || row[col[field]] === "");
  if (blanks.length > 0) {
    console.log(JSON.stringify({
      row: i + 1,
      name,
      url: row[col["url"]],
      state: row[col["state"]],
      blanks,
      current: Object.fromEntries(keyFields.map((field) => [field, row[col[field]] ?? ""]))
    }));
  }
}
