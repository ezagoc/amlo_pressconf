import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata";
await fs.mkdir(outputDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");
const values = sheet.getRange("A1:AD246").values;
console.log(JSON.stringify({ headers: values[0], rows: values.slice(215, 246).map((row, index) => ({ row: index + 216, values: row })) }, null, 2));

const preview = await workbook.render({ sheetName: "Hoja1", range: "A216:AD246", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_216_246_before.png`, new Uint8Array(await preview.arrayBuffer()));
