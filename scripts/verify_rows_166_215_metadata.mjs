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
const rows = values.slice(165, 215);
const allowedLeftRight = new Set(["left", "center", "right"]);
const allowedFourT = new Set(["aligned", "opp", "unclear"]);

const checks = {
  rowCount: rows.length,
  first: rows[0][col["name.page"]],
  last: rows[49][col["name.page"]],
  flagged: rows.filter((row) => row[col["needs.verification"]] === "yes").length,
  missingReasons: rows.filter((row) => row[col["needs.verification"]] === "yes" && !row[col["verification.reason"]]).length,
  missingIdeologySources: rows.filter((row) => !row[col["ideology.source"]]).map((row) => row[col["name.page"]]),
  invalidLeftRight: rows.filter((row) => !allowedLeftRight.has(row[col["ideology.leftright"]])).map((row) => row[col["name.page"]]),
  invalidFourT: rows.filter((row) => !allowedFourT.has(row[col["ideology.4t"]])).map((row) => row[col["name.page"]]),
  formulaErrorsInBatch: rows.flat().filter((value) => typeof value === "string" && /^#(REF!|DIV\/0!|VALUE!|NAME\?|N\/A|NUM!|NULL!|SPILL!|CALC!)$/.test(value)).length,
  sample: [166, 168, 175, 189, 198, 203, 207, 212, 215].map((number) => {
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
  "excelsior", "jaime_farias_informa", "siete24_noticias", "vittor_blogs", "sexta_w",
  "grupo_transmedia_la_chispa", "polemon", "sin_linea_mx", "medios_digitales_del_pacifico", "canal_14_spr",
  "grupo_acir", "pulso_saludable", "imer", "capital_21", "sin_censura", "reporte_indigo",
  "codigo_libre_mx", "grupo_larsa_comunicaciones", "el_quintana_roo_mx", "quadratin", "trafico_zmg",
  "el_centinela_informa", "nx_noticias", "sputnik", "rt_actualidad", "diario_presente", "la_hoguera",
  "quinto_poder", "bajo_palabra_noticias", "tijuana_comunica", "periodico_zocalo_tele_saltillo",
  "antitesis_periodismo", "xinhua", "eli_television", "diario_imagen", "ae_grupo_informativo",
  "agencia_obturador_mx_es_imagen", "diario_la_verdad_venezuela", "gaceta_del_aire",
  "la_opcion_de_chihuahua", "diario_plaza_juarez", "sonora_power", "vigilia_sonora",
  "grupo_audiorama", "perspectivas_mx", "noticieros_el_reloj_la_tlaxiaquena", "diario_del_yaqui",
  "zaachila_radio", "amarc_mexico", "oro_solido",
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
    length: note.length,
  });
}

console.log(JSON.stringify(checks, null, 2));

if (checks.rowCount !== 50 || checks.first !== "Excelsior" || checks.last !== "Oro Solido") throw new Error("Batch boundaries failed");
if (checks.flagged !== 50 || checks.missingReasons !== 0) throw new Error("Verification flags failed");
if (checks.formulaErrorsInBatch !== 0) throw new Error("Formula errors remain in edited batch");
if (checks.invalidLeftRight.length || checks.invalidFourT.length) throw new Error("Ideology label validation failed");
if (checks.notes.length !== 50 || checks.notes.some((note) => !note.hasSources || !note.hasIdeology || !note.hasVerification)) throw new Error("Markdown note validation failed");
