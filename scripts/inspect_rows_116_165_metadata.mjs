import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");

await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({
  sheetName: "Hoja1",
  range: "A116:AD165",
  scale: 1,
  format: "png",
});
await fs.writeFile(`${outputDir}/rows_116_165_before.png`, new Uint8Array(await preview.arrayBuffer()));

const values = sheet.getRange("A1:AD246").values;
const headers = values[0];
console.log(JSON.stringify({ headers }));
for (let excelRow = 116; excelRow <= 165; excelRow += 1) {
  const row = values[excelRow - 1];
  const record = Object.fromEntries(headers.map((header, index) => [header, row[index]]));
  console.log(JSON.stringify({ excelRow, ...record }));
}
