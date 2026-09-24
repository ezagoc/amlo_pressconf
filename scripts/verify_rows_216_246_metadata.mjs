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
const rows = values.slice(215, 246);
const allowedLeftRight = new Set(["left", "center", "right"]);
const allowedFourT = new Set(["aligned", "opp", "unclear"]);

const checks = {
  rowCount: rows.length,
  first: rows[0][col["name.page"]],
  last: rows[30][col["name.page"]],
  flagged: rows.filter((row) => row[col["needs.verification"]] === "yes").length,
  missingReasons: rows.filter((row) => row[col["needs.verification"]] === "yes" && !row[col["verification.reason"]]).length,
  missingIdeologySources: rows.filter((row) => !row[col["ideology.source"]]).map((row) => row[col["name.page"]]),
  invalidLeftRight: rows.filter((row) => !allowedLeftRight.has(row[col["ideology.leftright"]])).map((row) => row[col["name.page"]]),
  invalidFourT: rows.filter((row) => !allowedFourT.has(row[col["ideology.4t"]])).map((row) => row[col["name.page"]]),
  formulaErrorsInBatch: rows.flat().filter((value) => typeof value === "string" && /^#(REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!|SPILL!|CALC!)$/.test(value)).length,
  sample: [216, 218, 221, 224, 228, 232, 236, 239, 241, 243, 245, 246].map((number) => {
    const row = values[number - 1];
    return {
      row: number,
      name: row[col["name.page"]],
      state: row[col.state],
      legal: row[col.legal_name],
      ideology: row[col["ideology.leftright"]],
      fourT: row[col["ideology.4t"]],
      confidence: row[col["ideology.confidence"]],
      verify: row[col["needs.verification"]],
    };
  }),
};

const expectedSlugs = [
  "revista_etcetera", "el_pais_mexico", "sinembargo", "es_ahora_am", "frecuencia_cad",
  "nacion_14", "tiempo_la_noticia_digital_duplicate_row_222", "the_mexico_news_meme_yamel",
  "politica_y_rock_and_roll_radio", "proyecto_puente_sonora", "grupo_radiorama",
  "informando_la_transformacion", "el_lead_de_mexico", "la_grillotina_politica",
  "movimiento_consciencia", "puente_libre_mx", "marco_olvera_oficial", "portal_guanajuato",
  "el_defensor_de_la_verdad", "el_charro_politico", "on_noticias", "rompeviento_tv",
  "iztaccihuatl_en_el_sendero_de_la_luna", "alianza_de_medios_periodistas_de_a_pie",
  "despierta_quintana_roo", "debate_sinaloa", "elias_medina_en_las_redes", "impacto_diario",
  "ahora_tabasco", "radio_sonora", "telemax",
];

checks.notes = [];
for (const slug of expectedSlugs) {
  const file = path.join(notesDir, `${slug}.md`);
  const note = await fs.readFile(file, "utf8");
  checks.notes.push({
    slug,
    hasSources: note.includes("## Sources"),
    hasIdeology: note.includes("## Ideology rationale"),
    hasVerification: note.includes("## Verification note"),
    hasUrl: /https:\/\//.test(note),
    length: note.length,
  });
}

console.log(JSON.stringify(checks, null, 2));

if (checks.rowCount !== 31 || checks.first !== "Revista Etcétera" || checks.last !== "Telemax") throw new Error("Batch boundaries failed");
if (checks.flagged !== 31 || checks.missingReasons !== 0) throw new Error("Verification flags failed");
if (checks.missingIdeologySources.length) throw new Error("Ideology sources missing");
if (checks.formulaErrorsInBatch !== 0) throw new Error("Formula errors remain in edited batch");
if (checks.invalidLeftRight.length || checks.invalidFourT.length) throw new Error("Ideology label validation failed");
if (checks.notes.length !== 31 || checks.notes.some((note) => !note.hasSources || !note.hasIdeology || !note.hasVerification || !note.hasUrl)) throw new Error("Markdown note validation failed");

const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "final workbook formula error scan" });
console.log(errors.ndjson);

const render = await workbook.render({ sheetName: "Hoja1", range: "A216:AD246", scale: 1, format: "png" });
await fs.writeFile("C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata/rows_216_246_verified.png", new Uint8Array(await render.arrayBuffer()));
