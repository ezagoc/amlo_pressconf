import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata";
const outputPath = `${outputDir}/newspaper_metadata.xlsx`;
const notesDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/info_newspapers_gpt";
const researchDate = "2026-09-16";

const CUL = "center";
const UNC = "unclear";
const LOW = "low";

const outlets = [
  {
    row: 66, slug: "de_peso_yucatan", title: "De Peso Yucatan",
    updates: { municipality: "Merida", CVE_ENT: 31, "coverage.scope": "state", "city.headq": 31,
      "legal_name": "Servicios Informativos y Publicitarios del Sureste, S.A. de C.V.",
      "owner.person": "Gerardo Garcia Gamboa", "owner.family": "Familia Garcia Lavin / Garcia Gamboa",
      owner_group: "Grupo SIPSE", conglomerate: "Grupo SIPSE", "founder.name": "Andres Garcia Lavin",
      year_founded: 2004, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Tabloid brand of Grupo SIPSE. The Yucatan edition began in 2004 and operates in print, digital and social formats.",
    uncertainty: "Current control is inferred from the Grupo SIPSE corporate/family structure; no outlet-specific evidence establishes a current left-right or 4T position.",
    sources: ["https://depesoyucatan.com/especiales/aniversario-periodico-de-peso-yucatan-editorial/", "https://sipse.com/quienes-somos", "https://sipse.com/aviso-de-privacidad"]
  },
  {
    row: 67, slug: "sintesis_puebla", title: "Sintesis Puebla",
    updates: { "name.page": "Sintesis Puebla", municipality: "Puebla", CVE_ENT: 21, "coverage.scope": "state",
      address: "Av. Juarez 2915, Int. 301, Col. La Paz, C.P. 72160, Puebla, Puebla", "city.headq": 21,
      legal_name: "Asociacion Periodistica Sintesis, S.A. de C.V.", "owner.person": "Armando Prida Huerta",
      owner_group: "Sintesis", conglomerate: null, "founder.name": "Armando Prida Huerta", year_founded: 1992,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Puebla newspaper founded on 1 June 1992. Historical academic work described its editorial line as plural.",
    uncertainty: "The ownership and ideological evidence is older or indirect; current shareholding and a current political alignment were not independently established.",
    sources: ["https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=107", "https://sintesis.com.mx/hidalgo/aviso-de-privacidad/", "https://sintesis.com.mx/reportajes/", "https://tesiunamdocumentos.dgb.unam.mx/pdtestdf/0312022/0312022.pdf"]
  },
  {
    row: 68, slug: "esto", title: "Esto",
    updates: { municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national",
      address: "Guillermo Prieto 7, Col. San Rafael, C.P. 06470, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Organizacion Editorial Mexicana, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1941, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico deportivo / digital / social media" },
    assessment: "National sports daily founded on 2 September 1941 and now part of Organizacion Editorial Mexicana (OEM).",
    uncertainty: "This is primarily a sports title. Political ideology cannot be inferred reliably from historical OEM group behavior alone.",
    sources: ["https://letrashistoricas.cucsh.udg.mx/index.php/LH/article/download/7233/6488", "https://staging.esto.com.mx/558478-suscribete-al-esto/", "https://oem.com.mx/"]
  },
  {
    row: 69, slug: "el_sol_del_pacifico", title: "El Sol del Pacifico",
    updates: { municipality: "Mazatlan", CVE_ENT: 25, "coverage.scope": "regional", "city.headq": 25,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1947, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "historical newspaper title" },
    assessment: "Historical Mazatlan title founded in 1947 and later associated with OEM. The workbook URL currently resolves to El Sol de Mazatlan.",
    uncertainty: "The row appears to mix a discontinued or renamed title with the current El Sol de Mazatlan site. Verify whether it should be renamed, merged or retained as a historical outlet.",
    sources: ["https://letrashistoricas.cucsh.udg.mx/index.php/LH/article/download/7233/6488", "https://sinaloaenlinea.com/45-anos-en-el-periodismo/", "https://www.eumed.net/libros-gratis/2011b/960/LA%20CONSTITUCION%20DE%20EMPRESAS%20TURISTICAS%20EN%20MAZATLAN.html"]
  },
  {
    row: 70, slug: "el_sudcaliforniano", title: "El Sudcaliforniano",
    updates: { municipality: "La Paz", CVE_ENT: 3, "coverage.scope": "state",
      address: "Constitucion 706 entre Altamirano y Gomez Farias, Centro, C.P. 23000, La Paz, Baja California Sur", "city.headq": 3,
      legal_name: "Compania Editora Sudcaliforniana, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Tomas Limon Garcia", year_founded: 1967, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "La Paz daily that began as a weekly in May 1967 and became a daily on 6 November 1967; now part of OEM.",
    uncertainty: "The precise current legal entity and outlet-level ideology need confirmation; the ownership field names OEM leadership, not a demonstrated sole shareholder.",
    sources: ["https://sic.gob.mx/ficha.php?table=impresos&table_id=76", "https://colectivopericu.wordpress.com/2009/11/16/fundacion-del-periodico-el-sudcaliforniano/", "https://oem.com.mx/"]
  },
  {
    row: 71, slug: "diario_de_yucatan_duplicate_row", title: "Diario de Yucatan (duplicate row)",
    updates: { municipality: "Merida", CVE_ENT: 31, "coverage.scope": "regional",
      address: "Calle 60 No. 521 entre 65 y 67, Centro, C.P. 97000, Merida, Yucatan", "city.headq": 31,
      legal_name: "Compania Tipografica Yucateca, S.A. de C.V.", "owner.person": "Carlos R. Menendez Losa",
      "owner.family": "Familia Menendez", owner_group: "Grupo Megamedia", conglomerate: "Grupo Megamedia",
      "founder.name": "Carlos R. Menendez Gonzalez", year_founded: 1925, "ideology.leftright": "right", "ideology.4t": "opp",
      "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Duplicate workbook entry for the Merida daily founded in 1925. Historical research supports a conservative/Catholic editorial tradition and opposition-oriented posture.",
    uncertainty: "Verify whether this row should be merged with the earlier Diario de Yucatan record. Current 4T opposition is an inference from editorial history and coverage, and the named person is a family executive rather than a proven sole owner.",
    sources: ["https://www.yucatan.com.mx/directorio", "https://www.yucatan.com.mx/contacto", "https://www.yucatan.com.mx/aviso-de-privacidad", "https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=306", "https://www.scielo.org.mx/scielo.php?pid=S1870-719X2015000100007&script=sci_arttext"]
  },
  {
    row: 72, slug: "reforma", title: "Reforma",
    updates: { municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9,
      legal_name: "Editora El Sol, S.A. de C.V.", "owner.person": "Alejandro Junco de la Vega", "owner.family": "Familia Junco de la Vega",
      owner_group: "Grupo Reforma", conglomerate: "Grupo Reforma", "founder.name": "Alejandro Junco de la Vega", year_founded: 1993,
      "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "high", "type.media": "periodico / digital / social media" },
    assessment: "National daily of Grupo Reforma. Academic research identifies it as traditionally center-right and a central press opponent of AMLO and the 4T.",
    uncertainty: "No material outlet-level uncertainty found for the core ownership and ideology classification; the exact legal vehicle should still be checked against a current corporate filing.",
    verify: "no",
    sources: ["https://revistas.ucm.es/index.php/CIYC/es/article/view/64840", "https://academic.oup.com/anncom/article/49/2/61/8125714", "https://journalismresearch.org/wp-content/uploads/2024/06/Mexico-MIM-FULL-FINAL.pdf", "https://www.scielo.org.mx/scielo.php?pid=S0188-252X2016000100005&script=sci_arttext"]
  },
  {
    row: 73, slug: "el_norte", title: "El Norte",
    updates: { municipality: "Monterrey", CVE_ENT: 19, "coverage.scope": "regional", "city.headq": 19,
      legal_name: "Ediciones del Norte, S.A. de C.V.", "owner.person": "Alejandro Junco de la Vega", "owner.family": "Familia Junco de la Vega",
      owner_group: "Grupo Reforma", conglomerate: "Grupo Reforma", "founder.name": "Rodolfo Junco de la Vega", year_founded: 1938,
      "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Monterrey daily and founding title of the family media group now known as Grupo Reforma.",
    uncertainty: "The political classification is supported chiefly by group-level editorial behavior rather than a separate current content study of El Norte.",
    sources: ["https://www.fundacionbuendia.org.mx/Tables/FMB/foromex/norte.html", "https://academic.oup.com/anncom/article/49/2/61/8125714", "https://journalismresearch.org/wp-content/uploads/2024/06/Mexico-MIM-FULL-FINAL.pdf"]
  },
  {
    row: 74, slug: "mural", title: "Mural",
    updates: { municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "regional", "city.headq": 14,
      legal_name: "Editora El Sol, S.A. de C.V.", "owner.person": "Alejandro Junco de la Vega", "owner.family": "Familia Junco de la Vega",
      owner_group: "Grupo Reforma", conglomerate: "Grupo Reforma", "founder.name": "Alejandro Junco de la Vega", year_founded: 1998,
      "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Guadalajara daily launched by Grupo Reforma in 1998 and sharing the group's editorial and ownership structure.",
    uncertainty: "The ideology label is transferred from well-documented Grupo Reforma behavior; verify the precise current publishing entity for Mural.",
    sources: ["https://www.mural.com/", "https://academic.oup.com/anncom/article/49/2/61/8125714", "https://journalismresearch.org/wp-content/uploads/2024/06/Mexico-MIM-FULL-FINAL.pdf"]
  },
  {
    row: 75, slug: "revista_cuartoscuro", title: "Revista Cuartoscuro",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Juan Escutia 55, Col. Condesa, C.P. 06140, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Cuartoscuro, S.A. de C.V.", "owner.person": "Pedro Valtierra", owner_group: "Cuartoscuro",
      conglomerate: null, "founder.name": "Pedro Valtierra", year_founded: 1993,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "revista fotografica / digital / social media" },
    assessment: "National photojournalism agency and magazine founded by photographer Pedro Valtierra.",
    uncertainty: "The public sources identify Valtierra as founder/director but do not fully document current shareholding; no reliable evidence supports a partisan ideology label.",
    sources: ["https://revistacuartoscuro.com/aviso-de-privacidad/", "https://revistacuartoscuro.com/", "https://cuartoscuro.com/"]
  },
  {
    row: 76, slug: "cuarto_poder_chiapas", title: "Cuarto Poder (Chiapas)",
    updates: { municipality: "Tuxtla Gutierrez", CVE_ENT: 7, "coverage.scope": "state",
      address: "3a Poniente Norte 141, Centro, C.P. 29000, Tuxtla Gutierrez, Chiapas", "city.headq": 7,
      legal_name: null, "owner.person": "Conrado de la Cruz Jimenez", "owner.family": "Familia De la Cruz",
      owner_group: "Cuarto Poder", conglomerate: null, "founder.name": "Conrado de la Cruz Jimenez", year_founded: 1976,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Chiapas newspaper associated with Conrado de la Cruz Jimenez since his 1976 acquisition and relaunch of the title.",
    uncertainty: "The title existed before the 1976 acquisition. Current legal ownership and ultimate control were not independently verified.",
    sources: ["https://www.cuartopoder.mx/acercade", "https://www.cuartopoder.mx/chiapas/vision-empresarial-y-periodistica-unica/582466", "https://www.archivo.cuartopoder.mx/suplemento1976.pdf"]
  },
  {
    row: 77, slug: "mexico_informa", title: "Mexico Informa",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Insurgentes Centro 132, Despacho 406, Col. Tabacalera, C.P. 06030, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Ediciones Kukulcancun, S.A. de C.V.", "owner.person": null, owner_group: "Mexico Informa",
      conglomerate: null, "founder.name": null, year_founded: null, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "revista / digital / social media" },
    assessment: "National magazine and digital outlet. Its masthead names Jose Antonio Chavez as director general and Ediciones Kukulcancun as the publishing entity.",
    uncertainty: "No reliable evidence identified the ultimate owner or founding year. A director is not automatically an owner, so the owner-person field remains blank.",
    sources: ["https://www.mexicoinforma.mx/wp-content/uploads/2024/10/REVISTA-MXINF-187-2.pdf", "https://mexicoinforma.mx/"]
  },
  {
    row: 78, slug: "luces_del_siglo", title: "Luces del Siglo",
    updates: { municipality: "Cancun", CVE_ENT: 23, "coverage.scope": "state", "city.headq": 23,
      legal_name: null, "owner.person": null, "owner.family": "Familia Paredes / Madero", owner_group: "Luces del Siglo",
      conglomerate: null, "founder.name": "Joaquin Paredes", year_founded: 2003, "ideology.leftright": CUL,
      "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / revista / digital / social media" },
    assessment: "Quintana Roo outlet founded in 2003 as a weekly magazine, with daily print/digital publication from 2015. Norma Madero Jimenez was publicly identified as proprietor until her death in 2022.",
    uncertainty: "Current ownership after Norma Madero's death is not documented in the sources reviewed. Its critical record toward a former state government does not establish a present 4T or left-right position.",
    sources: ["https://lucesdelsiglo.com/nosotros/", "https://notatrasnota.com.mx/2022/07/31/fallece-norma-madero-propietaria-de-la-revista-luces-del-siglo/", "https://www.jornada.com.mx/2014/10/01/estados/035n1est"]
  },
  {
    row: 79, slug: "la_prensa", title: "La Prensa",
    updates: { municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national",
      address: "Guillermo Prieto 7, Col. San Rafael, C.P. 06470, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Organizacion Editorial Mexicana, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      year_founded: 1928, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico tabloide / digital / social media" },
    assessment: "Mexico City popular/tabloid daily established in 1928 and now part of OEM.",
    uncertainty: "The address is OEM's group address and should be checked as the outlet's operating address. Current political ideology is not demonstrated by outlet-specific evidence.",
    sources: ["https://oem.com.mx/la-prensa/", "https://oem.com.mx/", "https://sic.cultura.gob.mx/"]
  },
  {
    row: 80, slug: "el_heraldo_de_xalapa", title: "El Heraldo de Xalapa",
    updates: { municipality: "Xalapa", CVE_ENT: 30, "coverage.scope": "regional", "city.headq": 30,
      legal_name: null, "owner.person": "Ruben Pabello Rojas", "owner.family": "Familia Pabello",
      owner_group: "Grupo Editorial El Heraldo de Veracruz", conglomerate: "Grupo Editorial El Heraldo de Veracruz",
      "founder.name": null, year_founded: null, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Xalapa outlet within Grupo Editorial El Heraldo de Veracruz. Its site identifies Ruben Pabello Rojas as director general.",
    uncertainty: "The director was not proven to be the current ultimate owner. Legal entity, street address and founding year remain unverified.",
    sources: ["https://heraldodexalapa.com.mx/", "https://heraldodexalapa.com.mx/xalapa.html"]
  },
  {
    row: 81, slug: "el_noticiero_de_manzanillo", title: "El Noticiero de Manzanillo",
    updates: { municipality: "Manzanillo", CVE_ENT: 6, "coverage.scope": "regional", "city.headq": 6,
      legal_name: null, "owner.person": null, "owner.family": "Familia Valdez", owner_group: "El Noticiero",
      conglomerate: null, "founder.name": "Carlos Valdez Ramirez", year_founded: 1974,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Colima/Manzanillo newspaper founded by Carlos Valdez Ramirez; its 49th-anniversary account supports a 1974 origin.",
    uncertainty: "Current legal entity, exact owner and street address were not independently verified. The founding year is derived from an anniversary count.",
    sources: ["https://www.elnoticieroenlinea.com/49-aniversario-de-el-noticiero/", "https://www.elnoticieroenlinea.com/"]
  },
  {
    row: 82, slug: "el_porvenir", title: "El Porvenir",
    updates: { municipality: "Monterrey", CVE_ENT: 19, "coverage.scope": "regional",
      address: "Galeana Sur 344 y 5 de Mayo, Centro, Monterrey, Nuevo Leon", "city.headq": 19,
      legal_name: "Editorial El Porvenir, S.A. de C.V.", "owner.person": "Jose Gerardo Cantu Escalante",
      "owner.family": "Familia Cantu", owner_group: "Editorial El Porvenir", conglomerate: null,
      "founder.name": "Jesus Cantu Leal; Porfirio Barba Jacob; Federico Gomez; Eduardo Martinez Celis", year_founded: 1919,
      "ideology.leftright": "right", "ideology.4t": UNC, "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Monterrey daily founded on 31 January 1919. Official pages document the Cantu family leadership and legal publisher.",
    uncertainty: "The conservative/right label is supported partly by secondary characterization; no clear current 4T alignment was established.",
    sources: ["https://www.elporvenir.mx/directorio", "https://elporvenir.mx/quienessomos", "https://es.wikipedia.org/wiki/El_Porvenir_(M%C3%A9xico)"]
  },
  {
    row: 83, slug: "am_guanajuato", title: "AM (Guanajuato)",
    updates: { municipality: "Leon", CVE_ENT: 11, "coverage.scope": "state",
      address: "Calzada de los Heroes 708, Col. La Martinica, C.P. 37500, Leon, Guanajuato", "city.headq": 11,
      legal_name: "Editorial Martinica, S.A. de C.V.", "owner.person": "Enrique Gomez Orozco", "owner.family": "Familia Gomez",
      owner_group: "Grupo AM", conglomerate: "Grupo AM", "founder.name": "Roberto Suarez Nieto", year_founded: 1978,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Leon daily first published on 21 May 1978, now published by Editorial Martinica and controlled by the Gomez family/Grupo AM.",
    uncertainty: "The original company and current legal publisher differ, and no current content study supports a simple partisan classification.",
    sources: ["https://www.am.com.mx/nosotros-somos-usted", "https://www.am.com.mx/nuestros-principios", "https://www.am.com.mx/terminos-y-condiciones", "https://www.am.com.mx/nacional/2023/07/17/anuncia-grupo-am-a-su-nuevo-director-general-enrique-a-gomez-zermeno-668823.html"]
  },
  {
    row: 84, slug: "ovaciones", title: "Ovaciones",
    updates: { municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national",
      address: "Lago Zirahuen 279, Anahuac I Seccion, C.P. 11320, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Editorial Ovaciones, S.A. de C.V.", "owner.person": "Jose de Jesus Aguirre Campos",
      owner_group: "NTR Medios", conglomerate: "NTR Medios", year_founded: 1926,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Long-running sports/general daily founded in 1926. OEM sold the title to NTR Medios in January 2025.",
    uncertainty: "Recent ownership transition makes older ownership and ideology descriptions unreliable; no current political alignment was established.",
    sources: ["https://ovaciones.com/quienes-somos", "https://ovaciones.com/aviso-de-privacidad", "https://comunicacion.diputados.gob.mx/sintesis/LINKSIN3/10125_J_PROCESO_0_COMPADREDERICARDO_COMPRADIARIODEPORTIVODEOVACIONES_RM_.pdf", "https://miranda-intelligence.com/en/pulso-de-los-medios/el-pulso-de-los-medios-enero-2025/"]
  },
  {
    row: 85, slug: "televisa_nmas", title: "Televisa / N+",
    updates: { municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9,
      legal_name: "Grupo Televisa, S.A.B.", "owner.person": "Emilio Azcarraga Jean", "owner.family": "Familia Azcarraga",
      owner_group: "TelevisaUnivision / Grupo Televisa", conglomerate: "TelevisaUnivision",
      "founder.name": "Emilio Azcarraga Vidaurreta", year_founded: "1930 group origins; 2022 N+ brand",
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "television / digital / social media" },
    assessment: "The workbook row points to N+, the current Televisa news brand, not a newspaper. It is part of the Televisa/TelevisaUnivision structure controlled historically by the Azcarraga family.",
    uncertainty: "The row conflates the parent company, its news division and the N+ brand. Exact publishing entity, relevant founding date and current 4T alignment require outlet-specific verification.",
    sources: ["https://www.nmas.com.mx/politica-de-privacidad/", "https://www.televisair.com/", "https://www.sciencedirect.com/science/article/pii/S0185191817300442", "https://www.scielo.org.mx/scielo.php?lng=es&nrm=iso&pid=S1870-23332022000200007&script=sci_arttext_plus&tlng=es"]
  },
  {
    row: 86, slug: "el_economista", title: "El Economista",
    updates: { municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9,
      legal_name: "Periodico Especializado en Economia y Finanzas, S.A. de C.V.", "owner.person": "Jorge Nacer Gobera",
      owner_group: "Nacer Global", conglomerate: "Nacer Global", "founder.name": "Luis Enrique Mercado; Martin Casillas de Alba",
      year_founded: 1988, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico economico / digital / social media" },
    assessment: "National business newspaper founded on 5 December 1988 and acquired by the Nacer group in 2008.",
    uncertainty: "Business orientation does not by itself establish a right-wing or opposition label; the named person is group president and current shareholding should be checked.",
    sources: ["https://www.eleconomista.com.mx/edicion-digital/edicion_global", "https://www.eleconomista.com.mx/opinion/El-Economista-24-anos-20121007-0001.html", "https://www.eleconomista.com.mx/empresas/Entrevista-con-Jorge-Nacer-Gobera-para-PwC-20140514-0028.html"]
  },
  {
    row: 87, slug: "el_financiero", title: "El Financiero",
    updates: { municipality: "Alvaro Obregon", CVE_ENT: null, "coverage.scope": "national",
      address: "Guillermo Gonzalez Camarena 600, Planta Baja, Santa Fe, C.P. 01210, Alvaro Obregon, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Grupo Multimedia Lauman, S.A.P.I. de C.V.", "owner.person": "Manuel Arroyo Rodriguez",
      owner_group: "Grupo Lauman", conglomerate: "Grupo Lauman", "founder.name": "Rogelio Cardenas Sarmiento", year_founded: 1981,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico economico / television / digital / social media" },
    assessment: "National financial newspaper founded in 1981 and controlled by Manuel Arroyo Rodriguez through Grupo Lauman since 2012.",
    uncertainty: "No sufficiently robust current evidence supports a simple left-right or 4T alignment classification.",
    sources: ["https://elfinanciero-elfinanciero-prod.cdn.arcpublishing.com/aviso-de-privacidad/", "https://www.elfinanciero.com.mx/", "https://mexico.mom-gmr.org/"]
  },
  {
    row: 88, slug: "el_heraldo_de_aguascalientes", title: "El Heraldo de Aguascalientes",
    updates: { municipality: "Aguascalientes", CVE_ENT: 1, "coverage.scope": "state",
      address: "Jose Maria Chavez 120, Centro, C.P. 20000, Aguascalientes, Aguascalientes", "city.headq": 1,
      legal_name: "El Heraldo de Aguascalientes Cia. Editorial, S. de R.L. de C.V.", "owner.person": "Leon Mauricio Bercun Lopez",
      "owner.family": "Familia Bercun", owner_group: "El Heraldo de Aguascalientes", conglomerate: null,
      "founder.name": "Mauricio Bercun Melnic", year_founded: 1954, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Aguascalientes daily founded in 1954 by Mauricio Bercun Melnic and currently led by the Bercun family.",
    uncertainty: "Public sources vary in how they name the publishing company and do not establish a current ideological alignment.",
    sources: ["https://www.heraldo.mx/65-aniversario/", "https://www.heraldo.mx/septuagesimo-aniversario-de-el-heraldo/", "https://sic.gob.mx/ficha.php?table=impresos&table_id=5"]
  },
  {
    row: 89, slug: "el_horizonte", title: "El Horizonte",
    updates: { municipality: "Monterrey", CVE_ENT: 19, "coverage.scope": "regional",
      address: "Felix U. Gomez 405 Norte, Col. Obrera, C.P. 64010, Monterrey, Nuevo Leon", "city.headq": 19,
      legal_name: null, "owner.person": "Guillermo Salinas Pliego", owner_group: "Grupo Avalanz", conglomerate: "Grupo Avalanz",
      year_founded: 2013, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Monterrey news outlet launched in 2013 and associated with Grupo Avalanz, chaired by Guillermo Salinas Pliego.",
    uncertainty: "The exact publishing entity and ultimate shareholding were not verified. Business ownership alone does not justify a political ideology label.",
    sources: ["https://elhorizonte.mx/contacto", "https://www.elhorizonte.mx/nuevoleon/el-horizonte-10-anos-de-ser-contrapeso-en-nuevo-leon/vl1476619", "https://grupoavalanz.com/"]
  },
  {
    row: 90, slug: "el_sol_del_bajio", title: "El Sol del Bajio",
    updates: { municipality: "Celaya", CVE_ENT: 11, "coverage.scope": "regional", "city.headq": 11,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Celaya regional newspaper in the OEM network.",
    uncertainty: "Outlet-specific legal entity, street address, founding year and current ideology were not confirmed from reliable accessible sources.",
    sources: ["https://oem.com.mx/elsoldelbajio/", "https://oem.com.mx/"]
  },
  {
    row: 91, slug: "el_heraldo_de_chihuahua", title: "El Heraldo de Chihuahua",
    updates: { municipality: "Chihuahua", CVE_ENT: 8, "coverage.scope": "state", "city.headq": 8,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1944, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Chihuahua daily in the OEM network; the current title is historically linked to Jose Garcia Valseca's newspaper chain.",
    uncertainty: "Sources differ on whether 1944 is the founding date, acquisition date or relaunch date. Legal entity, address and current ideology need verification.",
    sources: ["https://oem.com.mx/elheraldodechihuahua/", "https://es.wikipedia.org/wiki/El_Heraldo_de_Chihuahua", "https://oem.com.mx/"]
  },
  {
    row: 92, slug: "el_occidental", title: "El Occidental",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "state", "city.headq": 14,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1942, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Guadalajara daily founded in 1942 and later incorporated into the Garcia Valseca/OEM chain.",
    uncertainty: "Exact current legal publisher and address were not verified. Current ideology is not established by the paper's historical chain affiliation.",
    sources: ["https://www.scielo.org.mx/scielo.php?pid=S2448-83722020000200167&script=sci_arttext", "https://es.wikipedia.org/wiki/El_Occidental", "https://oem.com.mx/eloccidental/"]
  },
  {
    row: 93, slug: "el_sol_de_mexico", title: "El Sol de Mexico",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Guillermo Prieto 7, Col. San Rafael, C.P. 06470, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Cia. Periodistica del Sol de Mexico, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1965, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "OEM's national Mexico City daily, founded in 1965 by Jose Garcia Valseca.",
    uncertainty: "Historical descriptions of the Garcia Valseca chain as officialist do not by themselves establish the outlet's current 4T alignment.",
    sources: ["https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=72", "https://mexico.mom-gmr.org/es/medios/detalles/outlet/el-sol-de-mexico/", "https://oem.com.mx/elsoldemexico/"]
  },
  {
    row: 94, slug: "el_sol_de_cuautla", title: "El Sol de Cuautla",
    updates: { municipality: "Cuautla", CVE_ENT: 17, "coverage.scope": "regional", "city.headq": 17,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana", year_founded: 1978,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Cuautla regional newspaper founded in 1978 and currently part of OEM.",
    uncertainty: "Outlet-specific legal entity, founder, street address and current ideology were not established.",
    sources: ["https://oem.com.mx/elsoldecuautla/local/el-sol-de-cuautla-cumple-45-anos-en-constante-evolucion-16141293", "https://oem.com.mx/elsoldecuautla/"]
  },
  {
    row: 95, slug: "el_sol_de_hidalgo", title: "El Sol de Hidalgo",
    updates: { municipality: "Pachuca", CVE_ENT: 13, "coverage.scope": "state", "city.headq": 13,
      legal_name: null, "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos",
      owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana", year_founded: 1949,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Pachuca newspaper in the OEM network; anniversary evidence points to a 1949 founding.",
    uncertainty: "The year is inferred from a 76th-anniversary reference. Legal publisher, exact address and outlet-specific ideology remain unverified.",
    sources: ["https://esto.com.mx/901362-carrera-el-sol-de-hidalgo-donde-es-y-cuando-empieza/", "https://oem.com.mx/elsoldehidalgo/"]
  },
  {
    row: 96, slug: "el_sol_de_puebla", title: "El Sol de Puebla",
    updates: { municipality: "Puebla", CVE_ENT: 21, "coverage.scope": "state",
      address: "Av. 3 Oriente 201, Centro, C.P. 72000, Puebla, Puebla", "city.headq": 21,
      legal_name: "Cia. Periodistica El Sol de Puebla", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "founder.name": "Jose Garcia Valseca", year_founded: 1944, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "periodico / digital / social media" },
    assessment: "Puebla daily founded on 5 May 1944 and now part of OEM.",
    uncertainty: "The abbreviated legal name should be checked against a current corporate filing; present ideology is not established by historical group affiliation.",
    sources: ["https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=77", "https://tesiunamdocumentos.dgb.unam.mx/pdtestdf/0312022/0312022.pdf", "https://oem.com.mx/elsoldepuebla/"]
  },
  {
    row: 97, slug: "diario_de_queretaro", title: "Diario de Queretaro",
    updates: { municipality: "Santiago de Queretaro", CVE_ENT: 22, "coverage.scope": "state", "city.headq": 22,
      legal_name: "Cia. Periodistica del Sol de Queretaro, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      year_founded: 1979, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Queretaro state daily founded in 1979 and part of OEM.",
    uncertainty: "Current street address, founder and outlet-specific political orientation were not confirmed.",
    sources: ["https://oem.com.mx/wp-content/uploads/2023/03/DIARIODEQUERETARO_MEDIAKIT_2023.pdf", "https://oem.com.mx/diariodequeretaro/"]
  },
  {
    row: 98, slug: "el_sol_de_tampico", title: "El Sol de Tampico",
    updates: { municipality: "Tampico", CVE_ENT: 28, "coverage.scope": "regional",
      address: "Alvaro Obregon 302 Poniente, Zona Centro, C.P. 89000, Tampico, Tamaulipas", "city.headq": 28,
      legal_name: "Compania Periodistica del Sol de Tampico, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      year_founded: 1950, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Tampico regional daily founded on 23 November 1950 and part of OEM.",
    uncertainty: "The founder and outlet-specific current ideology were not established; the named owner-person is OEM leadership rather than a proven sole owner.",
    sources: ["https://nosotros.oem.com.mx/wp-content/uploads/2024/06/SOMOS-INDUSTRIA-2024.pdf", "https://oem.com.mx/elsoldetampico/"]
  },
  {
    row: 99, slug: "el_sol_de_tlaxcala", title: "El Sol de Tlaxcala",
    updates: { municipality: "Tlaxcala", CVE_ENT: 29, "coverage.scope": "state",
      address: "Calle 3 No. 815, La Loma Xicotencatl, C.P. 90062, Tlaxcala, Tlaxcala", "city.headq": 29,
      legal_name: "Cia. Periodistica del Sol de Tlaxcala", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Tlaxcala state daily in the OEM network.",
    uncertainty: "Founding year, founder, complete current legal name and outlet-specific ideology remain unverified.",
    sources: ["https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=264", "https://oem.com.mx/wp-content/uploads/2023/03/ELSOLDETLAXCALA_MEDIAKIT_2023.pdf", "https://oem.com.mx/elsoldetlaxcala/"]
  },
  {
    row: 100, slug: "el_sol_de_veracruz", title: "El Sol de Veracruz",
    updates: { municipality: "Veracruz", CVE_ENT: 30, "coverage.scope": "state",
      address: "Blvd. Manuel Avila Camacho 210 Altos, Depto. 2, Col. Centro, Veracruz, Veracruz", "city.headq": 30,
      legal_name: null, "owner.person": null, owner_group: "El Sol de Veracruz", conglomerate: null,
      "founder.name": null, year_founded: null, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "digital / social media; print status unverified" },
    assessment: "Veracruz news site directed by Alan Couturier Prigadaa. Despite its name, the evidence reviewed does not connect it to OEM.",
    uncertainty: "The workbook's OEM classification was incorrect. Legal owner, founding year and whether a current print edition exists remain unverified.",
    sources: ["https://elsoldeveracruz.com/quienes-somos/", "https://elsoldeveracruz.com/"]
  },
  {
    row: 101, slug: "el_sol_de_zacatecas", title: "El Sol de Zacatecas",
    updates: { municipality: "Zacatecas", CVE_ENT: 32, "coverage.scope": "state", "city.headq": 32,
      legal_name: "Cia. Periodistica del Sol de Zacatecas, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez",
      "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana",
      year_founded: 1964, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Zacatecas state daily founded on 19 June 1964 and part of OEM. Its published guidelines declare pluralism and editorial standards.",
    uncertainty: "The declared standards do not establish a current partisan alignment; street address and founder were not confirmed.",
    sources: ["https://oem.com.mx/elsoldezacatecas/info/directrices-editoriales/app.json", "https://oem.com.mx/elsoldezacatecas/"]
  },
  {
    row: 102, slug: "el_universal", title: "El Universal",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Bucareli 8, Col. Centro, C.P. 06040, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "El Universal Compania Periodistica Nacional, S.A. de C.V.", "owner.person": "Juan Francisco Ealy Ortiz",
      "owner.family": "Familia Ealy", owner_group: "El Universal", conglomerate: "El Universal",
      "founder.name": "Felix F. Palavicini", year_founded: 1916, "ideology.leftright": CUL, "ideology.4t": "opp",
      "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "National daily founded on 1 October 1916 and controlled for decades by the Ealy family. Its 4T classification is opposition-oriented, while the broader left-right label remains center because the paper hosts diverse voices.",
    uncertainty: "The left-right label is intrinsically mixed and should not be read as ideological neutrality. Current shareholding details beyond family control merit verification.",
    sources: ["https://oaxaca.eluniversal.com.mx/directorio/", "https://api.ieeg.mx/repoinfo/Uploads/269-el-universal-gubernatura-28-may-24.pdf", "https://academic.oup.com/anncom/article/49/2/61/8125714", "https://mexico.mom-gmr.org/"]
  },
  {
    row: 103, slug: "el_heraldo_de_tuxpan", title: "El Heraldo de Tuxpan",
    updates: { municipality: "Tuxpan", CVE_ENT: 30, "coverage.scope": "regional", "city.headq": 30,
      legal_name: null, "owner.person": "Ruben Pabello Rojas", "owner.family": "Familia Pabello",
      owner_group: "Grupo Editorial El Heraldo de Veracruz", conglomerate: "Grupo Editorial El Heraldo de Veracruz",
      year_founded: 2004, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "periodico / digital / social media" },
    assessment: "Tuxpan regional newspaper founded in 2004 and listed within Grupo Editorial El Heraldo de Veracruz; the state registry reports print publication Monday through Saturday plus digital presence.",
    uncertainty: "Current legal owner, publishing entity, street address and ideology were not independently verified; the named person is group director.",
    sources: ["https://pemc.veracruz.gob.mx/medio-comunicacion/el-heraldo-de-tuxpan/", "https://elheraldodetuxpan.com.mx/"]
  },
  {
    row: 104, slug: "eje_central", title: "Eje Central",
    updates: { municipality: "Cuajimalpa", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Santa Fe 443, Piso 35, Cuajimalpa, C.P. 05000, Ciudad de Mexico", "city.headq": 9,
      legal_name: "OFEM Media Group OMG, S.A. de C.V.", "owner.person": "Oliver Fernandez Mena",
      owner_group: "OFEM Media Group", conglomerate: "OFEM Media Group", "founder.name": "Raymundo Riva Palacio", year_founded: 2009,
      "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "medium",
      "type.media": "semanario / digital / social media" },
    assessment: "Digital outlet founded by Raymundo Riva Palacio in 2009, with a weekly print edition launched in 2016; now associated with OFEM Media Group and Oliver Fernandez Mena. Current coverage is strongly opposition-oriented toward the 4T.",
    uncertainty: "The ownership transition is recent and ultimate shareholding is not fully transparent in public sources.",
    sources: ["https://www.ejecentral.com.mx/aviso-de-privacidad", "https://www.elfinanciero.com.mx/nacional/raymundo-riva-palacio-lanza-este-jueves-edicion-impresa-de-eje-central/", "https://directorio.sembramedia.org/eje-central/", "https://biblioteca.uaa.mx/dib/docs/Zocalo/2024/Zocalo_296_2024_10.pdf", "https://ofemg.com/"]
  },
  {
    row: 105, slug: "azteca_noticias", title: "Azteca Noticias",
    updates: { municipality: "Tlalpan", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Insurgentes Sur 3579, Col. Tlalpan La Joya, C.P. 14000, Tlalpan, Ciudad de Mexico", "city.headq": 9,
      legal_name: "TV Azteca, S.A.B. de C.V.", "owner.person": "Ricardo Salinas Pliego", "owner.family": "Familia Salinas Pliego",
      owner_group: "TV Azteca / Grupo Salinas", conglomerate: "Grupo Salinas", "founder.name": "Ricardo Salinas Pliego", year_founded: 1993,
      "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "high",
      "type.media": "television / digital / social media" },
    assessment: "National TV and digital news brand within TV Azteca/Grupo Salinas, controlled by Ricardo Salinas Pliego. The owner's sustained public campaigning against the Mexican left and Morena supports right/opposition coding.",
    uncertainty: "This is a news brand inside a broadcaster, not a standalone newspaper; the legal entity is the parent broadcaster.",
    sources: ["https://www.irtvazteca.com/es/estructura-corporativa", "https://www.tvazteca.com/aztecanoticias/tv-azteca-que-ano-ricardo-b-salinas-pliego-compro-la-televisora", "https://www.aztecaveracruz.com/politicas.html", "https://www.lemonde.fr/en/international/article/2025/11/22/the-ambiguities-of-the-generation-z-movement-in-mexico_6747717_4.html"]
  },
  {
    row: 106, slug: "expansion", title: "Expansion",
    updates: { municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Constituyentes 956, Col. Lomas Altas, C.P. 11950, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9,
      legal_name: "5M2 Holding, S.A.P.I. de C.V.", "owner.person": null, owner_group: "Grupo Expansion / Cinco M Dos",
      conglomerate: "Grupo Expansion", "founder.name": "Harvey Popell; Gustavo Romero Kolbeck; John Christman", year_founded: 1969,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "revista / digital / social media" },
    assessment: "National business magazine/digital outlet in Grupo Expansion, acquired by Cinco M Dos in 2017.",
    uncertainty: "Ultimate individual ownership is opaque, and the founding date/founder list relies partly on secondary histories. It is not a newspaper.",
    sources: ["https://expansion.mx/aviso-legal-y-privacidad", "https://grupoexpansion.com/terminos-y-condiciones/", "https://grupoexpansion.com/contacto/", "https://expansion.mx/empresas/2017/07/13/la-comision-de-competencia-aprueba-la-venta-de-grupo-expansion", "https://es.wikipedia.org/wiki/Expansi%C3%B3n_(revista)"]
  },
  {
    row: 107, slug: "tribuna_de_tlalpan", title: "Tribuna de Tlalpan",
    updates: { state: "Ciudad de Mexico", municipality: "Tlalpan", CVE_ENT: 9, "coverage.scope": "municipal", "city.headq": 9,
      legal_name: null, "owner.person": null, owner_group: null, conglomerate: null, "founder.name": null, year_founded: null,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW, "type.media": "unverified outlet" },
    assessment: "No sufficiently reliable public record or identifiable current website was found for an outlet with this exact name.",
    uncertainty: "High-priority manual check: this may be a clipping/source label, a defunct hyperlocal title, or a misnamed outlet. Ownership, address, dates, format and ideology are all unverified.",
    sources: []
  },
  {
    row: 108, slug: "mundo_ejecutivo", title: "Mundo Ejecutivo",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Rio Nazas 34, Col. Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Grupo Internacional Editorial, S.A. de C.V.", "owner.person": "Jessyca Cervantes Bolanos",
      owner_group: "Grupo Mundo Ejecutivo", conglomerate: "Grupo Mundo Ejecutivo", "founder.name": "Walter Coratella Marano",
      year_founded: 1975, "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "revista / digital / social media" },
    assessment: "Business-media group and magazine founded by Walter Coratella Marano, currently led by executive president Jessyca Cervantes Bolanos. GINgroup acquired a 46% participation in 2018.",
    uncertainty: "Current shareholding after later changes is not transparent; legal-name evidence is older and public sources show address variants. This is a magazine/group, not a newspaper.",
    sources: ["https://grupomundoejecutivo.com/", "https://grupomundoejecutivo.com/contactanos-ahora/", "https://pasaporteinformativo.mx/2018/06/07/compra-gingroup-46-de-grupo-mundo-ejecutivo/", "https://mundoejecutivo.com.mx/actualidad/grupo-mundo-ejecutivo-anuncia-el-nombramiento-de-jessyca-cervantes-como-presidenta-ejecutiva-del-grupo/", "https://www.cndh.org.mx/sites/default/files/doc/Informes/Contratos/CGCP/2015/2015_4trim_oct.pdf"]
  },
  {
    row: 109, slug: "nota_nayarit_la_serpentina", title: "Nota Nayarit: La Serpentina",
    updates: { municipality: "Tepic", CVE_ENT: 18, "coverage.scope": "state", "city.headq": 18,
      legal_name: null, "owner.person": null, owner_group: "Nota Nayarit", conglomerate: null,
      "founder.name": null, year_founded: null, "ideology.leftright": CUL, "ideology.4t": UNC,
      "ideology.confidence": LOW, "type.media": "opinion column / digital" },
    assessment: "La Serpentina is an opinion column by Guillermo Aguirre, carried by Nota Nayarit and also reproduced in Meridiano de Nayarit materials. It is not an independent newspaper.",
    uncertainty: "High-priority normalization issue: decide whether the row should represent the parent outlet Nota Nayarit, the columnist, or be removed from an outlet-level dataset.",
    sources: ["https://notanayarit.mx/nn/author/guillermoaguirre/", "https://meridiano.mx/wp-content/uploads/2025/11/Meridiano-18_11_2025.pdf", "https://meridiano.mx/wp-content/uploads/2025/12/MERIDIANO2025-12-31.pdf"]
  },
  {
    row: 110, slug: "alto_nivel", title: "Alto Nivel",
    updates: { municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Ejercito Nacional 425, Piso 9, Col. Granada, C.P. 11520, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Impresiones Aereas, S.A. de C.V. / Alto Nivel, S.A. de C.V.", "owner.person": null,
      owner_group: "G21 Comunicacion", conglomerate: "G21 Comunicacion", "founder.name": null, year_founded: null,
      "ideology.leftright": CUL, "ideology.4t": UNC, "ideology.confidence": LOW,
      "type.media": "revista / digital / social media" },
    assessment: "National management/business magazine and digital site associated with G21 Comunicacion.",
    uncertainty: "Current ultimate owner, founder, founding year and the applicable legal entity need verification. It is not a newspaper.",
    sources: ["https://www.altonivel.com.mx/aviso-de-privacidad/", "https://www.altonivel.com.mx/"]
  },
  {
    row: 111, slug: "inmediata_publicidad", title: "Inmediata Publicidad",
    updates: { state: null, municipality: null, CVE_ENT: null, "coverage.scope": "national", address: null, "city.headq": null,
      legal_name: null, "owner.person": null, owner_group: "Inmediata Publicidad", conglomerate: null,
      "founder.name": null, year_founded: null, "ideology.leftright": null, "ideology.4t": null,
      "ideology.confidence": null, "ideology.source": null, "type.media": "advertising / media-placement agency" },
    assessment: "The identified entity is an advertising and publication-placement agency with more than four decades of activity, not a journalistic outlet.",
    uncertainty: "High-priority classification issue: this row should likely be excluded from the newspaper archive or reclassified as a service provider.",
    sources: ["https://inmediatapublicidad.com/"]
  },
  {
    row: 112, slug: "tecnologia_ambiental", title: "Tecnologia Ambiental",
    updates: { state: null, municipality: null, CVE_ENT: null, "coverage.scope": null, address: null, "city.headq": null,
      legal_name: null, "owner.person": null, owner_group: null, conglomerate: null, "founder.name": null, year_founded: null,
      "ideology.leftright": null, "ideology.4t": null, "ideology.confidence": null, "ideology.source": null,
      "type.media": "unverified" },
    assessment: "No unique newspaper or news outlet could be tied confidently to this generic name. Search results refer to unrelated companies, journals and environmental-technology topics.",
    uncertainty: "High-priority identity check: a URL, city, clipping image or publisher name is needed before metadata can be assigned.",
    sources: []
  },
  {
    row: 113, slug: "milenio", title: "Milenio",
    updates: { municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national",
      address: "Morelos 16, Col. Centro, C.P. 06040, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Milenio Diario, S.A. de C.V.", "owner.person": "Francisco D. Gonzalez Albuerne",
      "owner.family": "Familia Gonzalez", owner_group: "Grupo Milenio / Grupo Multimedios", conglomerate: "Grupo Multimedios",
      "founder.name": "Jesus Dionisio Gonzalez", year_founded: "1974 lineage; 2000 national Milenio",
      "ideology.leftright": CUL, "ideology.4t": "aligned", "ideology.confidence": "medium",
      "type.media": "periodico / television / digital / social media" },
    assessment: "National multimedia news brand of the Gonzalez family's Grupo Multimedios. The newspaper lineage begins with Diario de Monterrey in 1974; the national Milenio title launched in 2000. Coding is center/aligned because research finds source-dependent, government-amplifying coverage rather than a coherent left ideology.",
    uncertainty: "The correct founding year depends on whether the dataset tracks the corporate lineage or the national title. Alignment should be interpreted as comparatively government-amplifying, not as ideological leftism.",
    sources: ["https://www.milenio.com/aviso-de-privacidad", "https://www.milenio.com/quienes-somos", "https://www.milenio.com/politica/25-anos-de-periodismo-con-calidad-inteligencia-y-caracter", "https://mexico.mom-gmr.org/es/propietarios/propietarios-individuales/detalles/owner/owner/show/gonzalez-family-1/", "https://academic.oup.com/anncom/article/49/2/61/8125714"]
  },
  {
    row: 114, slug: "la_jornada_de_morelos", title: "La Jornada de Morelos",
    updates: { municipality: "Cuernavaca", CVE_ENT: 17, "coverage.scope": "state", "city.headq": 17,
      legal_name: "Al Fin Verde, S.A. de C.V.", "owner.person": null, owner_group: "La Jornada Morelos / Demos",
      conglomerate: "La Jornada", "founder.name": null, year_founded: 2022, "ideology.leftright": "left",
      "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Morelos edition using the La Jornada brand and naming Carmen Lira Saade as director general. Its left/aligned coding follows the national brand and editorial leadership.",
    uncertainty: "The ownership/licensing relationship between Al Fin Verde and national La Jornada is not fully public, and 2022 may represent the current edition rather than an earlier local lineage.",
    sources: ["https://www.lajornadamorelos.mx/directorio/", "https://www.lajornadamorelos.mx/", "https://www.jornada.com.mx/pagina/quienes-somos"]
  },
  {
    row: 115, slug: "la_jornada", title: "La Jornada",
    updates: { municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national",
      address: "Av. Cuauhtemoc 1236, Col. Santa Cruz Atoyac, C.P. 03310, Benito Juarez, Ciudad de Mexico", "city.headq": 9,
      legal_name: "Demos, Desarrollo de Medios, S.A. de C.V.", "owner.person": null,
      owner_group: "Demos / La Jornada", conglomerate: "La Jornada",
      "founder.name": "Carlos Payan Velver; Carmen Lira Saade; Miguel Angel Granados Chapa and founding collective", year_founded: 1984,
      "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high",
      "type.media": "periodico / digital / social media" },
    assessment: "National daily founded on 19 September 1984 by a journalist-led collective. Its stated social-justice and sovereignty orientation, historical favorable treatment of Lopez Obrador and scholarship on lopezobradorismo support left/aligned coding.",
    uncertainty: "No material uncertainty for the requested high-level classification. Carmen Lira is director, not entered as a sole owner because the company is journalist/shareholder controlled.",
    verify: "no",
    sources: ["https://www.jornada.com.mx/pagina/aviso-de-privacidad", "https://www.jornada.com.mx/pagina/aviso-legal", "https://www.jornada.com.mx/pagina/quienes-somos", "https://www.jornada.com.mx/pages/la-jornada-aniversario-38/", "https://revistas.ucm.es/index.php/ESMP/article/download/58022/52207/118069", "https://www.researchgate.net/publication/354907174_El_ajuste_ideologico_al_lopezobradorismo_de_la_prensa_de_opinion_mexicana"]
  }
];

if (outlets.length !== 50) throw new Error(`Expected 50 outlets, got ${outlets.length}`);

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(notesDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");

sheet.getRange("AC1:AD1").copyFrom(sheet.getRange("AA1:AB1"), "all");
sheet.getRange("AC1:AD1").values = [["needs.verification", "verification.reason"]];
sheet.getRange("AC2:AD246").copyFrom(sheet.getRange("AA2:AB246"), "all");
sheet.getRange("AC2:AD246").clear({ applyTo: "contents" });

const allValues = sheet.getRange("A1:AD246").values;
const headers = allValues[0];
const col = Object.fromEntries(headers.map((name, index) => [name, index]));

for (const outlet of outlets) {
  const rowIndex = outlet.row - 1;
  const row = [...allValues[rowIndex]];
  for (const [key, value] of Object.entries(outlet.updates)) {
    if (!(key in col)) throw new Error(`Column not found: ${key}`);
    row[col[key]] = value;
  }
  const verify = outlet.verify ?? "yes";
  row[col["needs.verification"]] = verify;
  row[col["verification.reason"]] = verify === "yes" ? outlet.uncertainty : "";
  row[col["ideology.source"]] = outlet.sources.join("; ");
  sheet.getRangeByIndexes(rowIndex, 0, 1, headers.length).values = [row];
  allValues[rowIndex] = row;

  const metadata = [
    ["Workbook row", outlet.row],
    ["Outlet", row[col["name.page"]]],
    ["State", row[col.state] ?? ""],
    ["Municipality / headquarters", row[col.municipality] ?? ""],
    ["Coverage", row[col["coverage.scope"]] ?? ""],
    ["Address", row[col.address] ?? ""],
    ["Legal name", row[col.legal_name] ?? ""],
    ["Owner / controlling person", row[col["owner.person"]] ?? ""],
    ["Owner family", row[col["owner.family"]] ?? ""],
    ["Owner group", row[col.owner_group] ?? ""],
    ["Founder", row[col["founder.name"]] ?? ""],
    ["Year founded", row[col.year_founded] ?? ""],
    ["Ideology (left-right)", row[col["ideology.leftright"]] ?? ""],
    ["4T relationship", row[col["ideology.4t"]] ?? ""],
    ["Ideology confidence", row[col["ideology.confidence"]] ?? ""],
    ["Media type / platforms", row[col["type.media"]] ?? ""],
    ["Needs verification", verify],
  ];
  const rows = metadata.map(([k, v]) => `| ${k} | ${String(v).replaceAll("|", "\\|")} |`).join("\n");
  const sourceLines = outlet.sources.length
    ? outlet.sources.map((url, index) => `${index + 1}. ${url}`).join("\n")
    : "No reliable source specific to this exact outlet identity was found. This absence is itself the reason for the verification flag.";
  const md = `# ${outlet.title}\n\nResearch date: ${researchDate}\n\n## Proposed metadata\n\n| Field | Proposed value |\n|---|---|\n${rows}\n\n## Evidence summary\n\n${outlet.assessment}\n\n## Ideology rationale\n\nThe workbook uses the deliberately simple labels shown above. A center/unclear/low entry means the available evidence did not justify a stronger partisan inference; it does not claim the outlet has no editorial tendencies.\n\n## Verification note\n\n${outlet.uncertainty}\n\n## Sources\n\n${sourceLines}\n`;
  await fs.writeFile(path.join(notesDir, `${outlet.slug}.md`), md, "utf8");
}

sheet.getRange("AC1:AD115").format.wrapText = true;
sheet.getRange("AC1:AC115").format.columnWidth = 18;
sheet.getRange("AD1:AD115").format.columnWidth = 62;

const check = await workbook.inspect({
  kind: "table", range: "Hoja1!A66:AD115", include: "values,formulas",
  tableMaxRows: 51, tableMaxCols: 30, tableMaxCellChars: 110,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 300 }, summary: "formula error scan after rows 66-115 update",
});
console.log(errors.ndjson);

const after = await workbook.render({ sheetName: "Hoja1", range: "A66:AD115", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_66_115_after.png`, new Uint8Array(await after.arrayBuffer()));

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const flagged = outlets.filter((outlet) => (outlet.verify ?? "yes") === "yes").length;
console.log(JSON.stringify({ outputPath, notes: outlets.length, flagged, notFlagged: outlets.length - flagged }, null, 2));
