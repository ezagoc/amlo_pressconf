import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata/newspaper_metadata.xlsx";
const notesDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/info_newspapers_gpt";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const sheet = workbook.worksheets.getItem("Hoja1");
const values = sheet.getRange("A1:AD246").values;
const headers = values[0];
const col = Object.fromEntries(headers.map((name, index) => [name, index]));
const rows = values.slice(115, 165);

const checks = {
  rowCount: rows.length,
  first: rows[0][col["name.page"]],
  last: rows[49][col["name.page"]],
  flagged: rows.filter((row) => row[col["needs.verification"]] === "yes").length,
  notFlagged: rows.filter((row) => row[col["needs.verification"]] === "no").length,
  formulaErrorsInBatch: rows.flat().filter((value) => typeof value === "string" && /^#(REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!|SPILL!|CALC!)$/.test(value)).length,
  sample: [116, 124, 132, 146, 156, 163, 165].map((number) => {
    const row = values[number - 1];
    return {
      row: number,
      name: row[col["name.page"]],
      legal: row[col.legal_name],
      ideology: row[col["ideology.leftright"]],
      fourT: row[col["ideology.4t"]],
      verify: row[col["needs.verification"]],
    };
  }),
};

const noteFiles = (await fs.readdir(notesDir)).filter((name) => name.endsWith(".md"));
const expectedSlugs = [
  "la_jornada_maya_yucatan", "grupo_formula", "adn40", "aristegui_noticias",
  "mexico_news_daily", "blank_row_157", "latitude_press", "los_reporteros_mx",
];
checks.notes = [];
for (const slug of expectedSlugs) {
  const file = path.join(notesDir, `${slug}.md`);
  const text = await fs.readFile(file, "utf8");
  checks.notes.push({ slug, hasSources: text.includes("## Sources"), hasIdeology: text.includes("## Ideology rationale"), length: text.length });
}
checks.totalMarkdownFilesInArchive = noteFiles.length;

console.log(JSON.stringify(checks, null, 2));

if (checks.rowCount !== 50 || checks.first !== "La Jornada Maya" || checks.last !== "Los Reporteros MX") throw new Error("Batch boundaries failed");
if (checks.flagged !== 49 || checks.notFlagged !== 1) throw new Error("Verification flag counts failed");
if (checks.formulaErrorsInBatch !== 0) throw new Error("Formula errors remain in edited batch");
if (checks.notes.some((note) => !note.hasSources || !note.hasIdeology)) throw new Error("Markdown note sections failed");
