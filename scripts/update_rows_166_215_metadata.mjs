import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = "C:/Users/Dell/Dropbox/Media/data/00-newspaper_data/newspaper_metadata.xlsx";
const outputDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/outputs/newspaper_metadata";
const outputPath = `${outputDir}/newspaper_metadata.xlsx`;
const notesDir = "C:/Users/Dell/Documents/GitHub/amlo_pressconf/info_newspapers_gpt";
const researchDate = "2026-09-16";

const outlets = [
  {
    row: 166, slug: "excelsior", title: "Excelsior",
    updates: { state: "Nacional", municipality: "Coyoacan", CVE_ENT: null, "coverage.scope": "national", address: "Av. Universidad 2014, Col. Copilco Universidad, C.P. 04360, Coyoacan, Ciudad de Mexico", "city.headq": 9, legal_name: "GIM Compania Editorial, S.A. de C.V.", "owner.person": "Olegario Vazquez Aldir", "owner.family": "Familia Vazquez Aldir", owner_group: "Grupo Imagen", conglomerate: "Grupo Vazol", "founder.name": "Rafael Alducin", year_founded: 1917, "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "National newspaper founded on 18 March 1917 by Rafael Alducin and relaunched by Grupo Imagen after its 2006 acquisition. Official and state records identify the publisher and Mexico City address.",
    ideology: "Its current political coverage and opinion pages are regularly critical of the 4T, supporting opposition coding. Center is more defensible than right because the paper carries a broad range of news and columnists.",
    uncertainty: "The legal notice names the broader Grupo Imagen entity while the Veracruz registry names GIM Compania Editorial. Current shareholding is inferred from the controlling group rather than a fresh corporate filing.",
    sources: ["https://www.excelsior.com.mx/aviso-privacidad-integral", "https://pemc.veracruz.gob.mx/medio-comunicacion/periodico-excelsior/", "https://www.excelsior.com.mx/nacional/2017/03/18/1152681", "https://mexico.mom-gmr.org/es/medios/detalles/outlet/excelsior-1/"]
  },
  {
    row: 167, slug: "jaime_farias_informa", title: "Jaime Farias Informa",
    updates: { state: "Quintana Roo", municipality: "Cancun", CVE_ENT: 23, "coverage.scope": "state / regional", "city.headq": 23, "owner.person": "Jaime Farias", owner_group: "JF Informa", "founder.name": "Jaime Farias", year_founded: 2016, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Personal news outlet centered on Cancun and Quintana Roo. Its February 2026 tenth-anniversary column supports a 2016 start date and identifies the project with Jaime Farias.",
    ideology: "No reliable evidence established a stable left-right or 4T position, so center/unclear is used.",
    uncertainty: "The legal entity, street address, financing and formal ownership are not disclosed; personal identification does not substitute for a corporate record.",
    sources: ["https://jaimefariasinforma.com/", "https://jaimefariasinforma.com/2026/02/08/columna-paradigmas-jf-informa-10-anos-con-credibilidad/"]
  },
  {
    row: 168, slug: "siete24_noticias", title: "Siete24 Noticias",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, owner_group: "Siete24", "ideology.leftright": "right", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "National digital news outlet whose privacy notice identifies Siete24.mx as the data controller but does not disclose a legal company or owner.",
    ideology: "Its own mission emphasizes dignity at every stage of life and family-centered values. That sustained conservative social framing supports a simple right label, while its relationship to the 4T remains unclear.",
    uncertainty: "High priority: ownership, legal entity, address, founders and launch date remain undisclosed. The ideology label rests on the outlet's stated editorial values, not evidence of party affiliation.",
    sources: ["https://siete24.mx/aviso-de-privacidad/", "https://siete24.mx/noticias-con-sentido-humano/", "https://siete24.mx/ecos/", "https://www.scielo.org.mx/scielo.php?pid=S0187-73722023000100112&script=sci_arttext"]
  },
  {
    row: 169, slug: "vittor_blogs", title: "Vittor Blogs",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "individual commentator / digital / video / social media" },
    assessment: "The archive label appears to identify a personal digital commentator, but no stable official website, legal entity or independently verifiable biography was located.",
    ideology: "No verifiable evidence supports a directional or 4T label, so center/unclear is used as the least assumptive classification.",
    uncertainty: "High priority: no URL is recorded and the exact person/account, ownership, location and operating status could not be verified.",
    sources: []
  },
  {
    row: 170, slug: "sexta_w", title: "Sexta W",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Luis Guillermo Hernandez", owner_group: "Sexta W", "founder.name": "Luis Guillermo Hernandez", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / streaming / social media" },
    assessment: "Independent multimedia outlet directed by Luis Guillermo Hernandez. Its about page says it is financed through its own resources, streaming, courses and crowdfunding.",
    ideology: "Sexta W explicitly describes its tendency as progressive, and its current editorial framing is favorable to the 4T. That supports left/aligned with high confidence.",
    uncertainty: "The legal entity, exact launch date, street address and formal ownership shares are not disclosed.",
    sources: ["https://sextaw.com.mx/nosotros/", "https://sextaw.com.mx/"]
  },
  {
    row: 171, slug: "grupo_transmedia_la_chispa", title: "Grupo Transmedia La Chispa",
    updates: { state: "Yucatan / Quintana Roo / Campeche / Tabasco", municipality: "Merida", CVE_ENT: 31, "coverage.scope": "regional / southeast", "city.headq": 31, legal_name: "Centro de Estudios e Investigacion y Gobernabilidad, S.A. de C.V. (reported)", owner_group: "Grupo Transmedia La Chispa", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / print editions / social media" },
    assessment: "Regional southeastern network operating state editions. Its terms name Grupo Transmedia La Chispa, while electoral records connect the operation to Centro de Estudios e Investigacion y Gobernabilidad and members of the Cruz Ulin network.",
    ideology: "Current political coverage and the pre-existing archive assessment support left/aligned, but the multi-edition structure warrants medium confidence.",
    uncertainty: "High priority: the precise legal relationship, ultimate shareholders, founders and headquarters remain unclear; Merida is a best-supported operational center, not a confirmed corporate domicile.",
    sources: ["https://lachispa.mx/terminos-y-condiciones/", "https://www.iepac.mx/public/documentos-del-consejo-general/resoluciones/2022/resolucion-expediente-utce-se-so-001-2022.pdf", "https://www.te.gob.mx/media/SentenciasN/pdf/especializada/SRE-PSC-0365-2024.pdf"]
  },
  {
    row: 172, slug: "polemon", title: "Polemon",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, owner_group: "Polemon", "founder.name": "Jorge Gomez Naredo; Jaime Aviles; Cesar Huerta", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / social media" },
    assessment: "National digital outlet co-founded by Jorge Gomez Naredo, Jaime Aviles and Cesar Huerta. Academic research describes it as favorable to the federal government and supported through donations and advertising.",
    ideology: "Its founders, editorial content and independent academic description support left/aligned with high confidence.",
    uncertainty: "The legal entity, launch date, headquarters, address and ownership shares are not publicly established.",
    sources: ["https://polemon.mx/author/jgnaredo/", "https://biblioteca-repositorio.clacso.edu.ar/bitstream/CLACSO/253159/1/2023_978-607-581-018-8.pdf", "https://regeneracion.mx/relanzan-el-periodico-impreso-regeneracion/"]
  },
  {
    row: 173, slug: "sin_linea_mx", title: "Sin Linea MX",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, "owner.person": "Benjamin Paz Moreno (president); Jazmina Dorles Perez (vice president)", owner_group: "Sin Linea MX", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / magazine / video / social media" },
    assessment: "Citizen media initiative that describes itself as self-financed. A 2025 magazine names Benjamin Paz Moreno as president and Jazmina Dorles Perez as vice president.",
    ideology: "The outlet explicitly supports Mexico's transformation and rejects neoliberalism. Its self-description and public participation support left/aligned with high confidence.",
    uncertainty: "The legal entity, founders, exact launch date, ownership shares and physical address were not verified.",
    sources: ["https://sinlineamx.com/quienes-somos/", "https://sinlineamx.com/wp-content/uploads/2025/06/Revista-SL-Vol-16-web.pdf", "https://www.gob.mx/amlo/articulos/version-estenografica-plenaria-primer-encuentro-continental-de-comunicador-s-independientes-informar-es-liberar"]
  },
  {
    row: 174, slug: "medios_digitales_del_pacifico", title: "Medios Digitales del Pacifico",
    updates: { state: "Sinaloa", municipality: null, CVE_ENT: 25, "coverage.scope": "regional / national politics", "city.headq": 25, "owner.person": "Julio Omar Gomez (public representative)", owner_group: "Medios Digitales del Pacifico / Ni Puntos Ni Comas", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / blog / social media" },
    assessment: "Small digital operation represented at presidential conferences by Julio Omar Gomez and associated in electoral records with the name Ni Puntos Ni Comas.",
    ideology: "Conference access and issue selection do not establish a durable ideology; center/unclear is therefore used.",
    uncertainty: "High priority: the row's WordPress site, brand names, legal identity, ownership, address and founding date could not be reconciled.",
    sources: ["https://mediosdigitalesdelpacifico.wordpress.com/", "https://www.te.gob.mx/EE/SUP/2024/REP/409/SUP_2024_REP_409-1376465.pdf", "https://liberalmetropolitano.com.mx/2026/04/08/las-censuras-del-cadenero-en-la-mananera/"]
  },
  {
    row: 175, slug: "canal_14_spr", title: "Canal 14 SPR",
    updates: { state: "Nacional", municipality: "Alvaro Obregon", CVE_ENT: null, "coverage.scope": "national", address: "Camino de Santa Teresa 1679, Col. Jardines del Pedregal, C.P. 01900, Alvaro Obregon, Ciudad de Mexico", "city.headq": 9, legal_name: "Sistema Publico de Radiodifusion del Estado Mexicano", owner_group: "Mexican federal state / SPR", conglomerate: "Mexican federal state", year_founded: "2012 channel lineage; 2017 Canal 14 brand", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "public television / digital / social media" },
    assessment: "Federal public television channel operated by the SPR. The channel began in 2012 under an earlier identity and adopted the Canal 14 brand in 2017.",
    ideology: "Center avoids assigning a partisan left-right ideology to a state broadcaster. Aligned records its institutional relationship to the federal executive and government public-media system.",
    uncertainty: "This is a state broadcaster, not a newspaper. The founding date depends on whether the channel lineage or current brand is measured.",
    sources: ["https://www.canalcatorce.tv/?a=Index&c=QuienesSomos&m1=1&p=q", "https://canalcatorce.tv/docs/pdf/aviso_privacidad/aviso_privacidad_20200101.pdf", "https://www.canalcatorce.tv/cantera14/"]
  },
  {
    row: 176, slug: "grupo_acir", title: "Grupo ACIR",
    updates: { state: "Nacional", municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national / multistate", address: "Boulevard de los Virreyes 1030, Col. Lomas de Chapultepec, C.P. 11000, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9, legal_name: "Grupo ACIR, S.A. de C.V.", "owner.family": "Familia Ibarra", owner_group: "Grupo ACIR", conglomerate: "Grupo ACIR", "founder.name": "Francisco Ibarra Lopez", year_founded: 1965, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "National radio group founded by Francisco Ibarra Lopez in 1965. Its official privacy notice supplies the Mexico City address.",
    ideology: "The group operates multiple music and news formats; no evidence supports one stable group-wide 4T position.",
    uncertainty: "The current controlling individual and detailed shareholding were not verified from a current filing. This is a radio group, not one editorial outlet.",
    sources: ["https://grupoacir.com.mx/nuestra-historia/", "https://grupoacir.com.mx/aviso-de-privacidad-2024/", "https://mexico.mom-gmr.org/es/propietarios/companias/detalles/company//grupo-acir-sa-de-cv-1/"]
  },
  {
    row: 177, slug: "pulso_saludable", title: "Pulso Saludable",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "health sector / national", "city.headq": null, owner_group: "Pulso Saludable", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "health publication / digital / social media" },
    assessment: "Health-focused digital publication covering public health, medicine, tourism, sports and general information.",
    ideology: "The outlet stated publicly that it had decided to support the federal government and created a recurring section around that support. This supports aligned, while center avoids inferring a broader economic ideology from a health outlet.",
    uncertainty: "The owner, legal entity, founder, launch date, address and financing remain undisclosed.",
    sources: ["https://www.pulsosaludable.com/", "https://www.pulsosaludable.com/cvpulsosaludable", "https://funsalud.org.mx/wp-content/uploads/2021/10/Salud-en-la-Prensa-Digital-del-12-de-octubre-de-2021.pdf"]
  },
  {
    row: 178, slug: "imer", title: "Instituto Mexicano de la Radio",
    updates: { state: "Nacional", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national", address: "Mayorazgo 83, Col. Xoco, C.P. 03330, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Instituto Mexicano de la Radio", owner_group: "Mexican federal state / IMER", conglomerate: "Mexican federal state", year_founded: 1983, "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "public radio / digital / social media" },
    assessment: "Federal public-radio institute created in 1983 and operating a national network of stations and digital services.",
    ideology: "Center avoids a partisan ideology label for a public institution. Aligned records its structural control by the federal government during the 4T period.",
    uncertainty: "This is a public radio institution rather than a newspaper; alignment is institutional, not a claim that every program supports the government.",
    sources: ["https://www.imer.mx/secciontransparencia/", "https://noticias.imer.mx/quienes-somos/", "https://www.imer.mx/"]
  },
  {
    row: 179, slug: "capital_21", title: "Capital 21",
    updates: { state: "Ciudad de Mexico", municipality: "Benito Juarez", CVE_ENT: 9, "coverage.scope": "city / metropolitan", address: "Moras 533, Col. Del Valle Sur, C.P. 03104, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Servicio de Medios Publicos de la Ciudad de Mexico", owner_group: "Government of Mexico City", conglomerate: "Government of Mexico City", year_founded: "2010 channel; 2021 current public-media entity", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "public television / digital / social media" },
    assessment: "Public television and digital outlet of the Mexico City government. The current public-media service was created in 2021, while the channel dates to 2010.",
    ideology: "Center is used for a government public-service channel; aligned reflects its direct institutional relationship to a 4T-aligned city executive.",
    uncertainty: "The row combines the original channel and its newer legal operator. It is not a newspaper, and alignment is structural rather than a judgment about every program.",
    sources: ["https://www.capital21.cdmx.gob.mx/transparencia", "https://www.capital21.cdmx.gob.mx/asi-renovara-cdmx-su-flota-de-rtp/"]
  },
  {
    row: 180, slug: "sin_censura", title: "Sin Censura",
    updates: { state: "Nacional / Estados Unidos", municipality: null, CVE_ENT: null, "coverage.scope": "national / diaspora", "city.headq": null, "owner.person": "Vicente Serrano", owner_group: "Sin Censura Media", "founder.name": "Vicente Serrano; Enrique Garcia Fuentes", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital television / video / social media" },
    assessment: "Personal digital television project founded by Vicente Serrano with Enrique Garcia Fuentes for Mexican and US-based audiences.",
    ideology: "Serrano's openly favorable coverage of Lopez Obrador and the outlet's sustained editorial line support left/aligned with high confidence.",
    uncertainty: "The legal entity, exact start date, ownership shares and current operating address were not verified; the project has a cross-border footprint.",
    sources: ["https://laopinion.com/2020/07/09/vicente-serrano-un-periodista-sin-censura-en-las-redes-sociales/", "https://www.zonadocs.mx/2024/08/20/militar-desde-el-periodismo/", "https://sincensuratv.com/"]
  },
  {
    row: 181, slug: "reporte_indigo", title: "Reporte Indigo",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, owner_group: "Grupo Capital Media", conglomerate: "Grupo Capital Media", "founder.name": "Ramon Alberto Garza", year_founded: "2006 digital; 2012 print", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / revista / digital / social media" },
    assessment: "Digital publication founded by Ramon Alberto Garza in 2006 and later expanded into print. Its privacy notice identifies Grupo Capital Media as the responsible group.",
    ideology: "The outlet has changed corporate context and carries mixed political coverage; no stable 4T line was established.",
    uncertainty: "High priority: the current ultimate owner, legal publisher, address and ownership transition into Grupo Capital Media require fresh verification.",
    sources: ["https://www.reporteindigo.com/pages/aviso-de-privacidad.html", "https://editorial.iteso.mx/index.php/PI/es/catalog/download/54/52/1974?inline=1", "https://es.wikipedia.org/wiki/Ram%C3%B3n_Alberto_Garza_Garc%C3%ADa"]
  },
  {
    row: 182, slug: "codigo_libre_mx", title: "Codigo Libre MX",
    updates: { state: "Ciudad de Mexico", municipality: "Ciudad de Mexico", CVE_ENT: 9, "coverage.scope": "national", "city.headq": 9, owner_group: "Codigo Libre MX", year_founded: 2020, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / audio-video / social media" },
    assessment: "Small self-described multimedia news and analysis platform. Its public company profile reports a 2020 founding and Mexico City headquarters.",
    ideology: "No reliable evidence establishes a durable partisan position, so center/unclear is used.",
    uncertainty: "The website was intermittently inaccessible, and the legal entity, owner, founders and street address were not verified. Do not confuse it with the separate Baja California outlet El Codigo Libre.",
    sources: ["https://www.linkedin.com/company/codigo-libre-mx", "https://www.iecm.mx/www/ut/ucs/INFORMA/marzo24m/INFOM160324/A1.pdf"]
  },
  {
    row: 183, slug: "grupo_larsa_comunicaciones", title: "Grupo Larsa Comunicaciones",
    updates: { state: "Sonora", municipality: "Ciudad Obregon", CVE_ENT: 26, "coverage.scope": "regional / multistate", "city.headq": 26, "owner.person": "Luis Antonio Ramos Mendez", owner_group: "Grupo Larsa Comunicaciones", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "Regional radio group centered in Sonora and publicly led by Luis Antonio Ramos Mendez. Its stations have longer individual histories than the group brand.",
    ideology: "No reliable evidence supports a group-wide political alignment across its music and news formats.",
    uncertainty: "The legal entity, ownership shares, exact group founding date, address and current station portfolio need verification.",
    sources: ["https://www.worldradiohistory.com/INTERNATIONAL/Medios-Publicitarios/mpm-2017-12.pdf"]
  },
  {
    row: 184, slug: "el_quintana_roo_mx", title: "El Quintana Roo MX",
    updates: { state: "Quintana Roo", municipality: "Cancun", CVE_ENT: 23, "coverage.scope": "state / national politics", "city.headq": 23, "owner.person": "Amir Ibrahim", owner_group: "El Quintana Roo MX / Los Reporteros MX", "founder.name": "Amir Ibrahim", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Quintana Roo digital outlet founded and directed by Amir Ibrahim, who also founded Los Reporteros MX.",
    ideology: "The shared network, programming and editorial coverage support left/aligned with high confidence.",
    uncertainty: "The legal entity, financing, founding date, street address and ownership shares remain undisclosed.",
    sources: ["https://uaeh.edu.mx/ful/2023/semblanza/amir-ibrahim-23", "https://elquintanaroo.mx/", "https://www.te.gob.mx/EE/SRE/2024/PSC/551/SRE_2024_PSC_551-1533629.pdf"]
  },
  {
    row: 185, slug: "quadratin", title: "Quadratin",
    updates: { state: "Michoacan", municipality: "Morelia", CVE_ENT: 16, "coverage.scope": "national / franchise network", address: "Jacarandas 137, Col. Jardines del Rincon, Morelia, Michoacan", "city.headq": 16, legal_name: "Quadratin, Agencia Mexicana de Informacion y Analisis", "owner.person": "Francisco Garcia Davish", owner_group: "Quadratin", "founder.name": "Francisco Garcia Davish", year_founded: 2002, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "news agency / digital / social media" },
    assessment: "Mexican news agency and franchise network founded in Michoacan in 2002 by Francisco Garcia Davish. A state-edition privacy notice supplies the Morelia address.",
    ideology: "The decentralized franchise structure and mixed reporting do not support one stable national 4T position.",
    uncertainty: "Different state editions may have distinct operators and editorial practices; the displayed legal name may be a trade name rather than the complete corporate style.",
    sources: ["https://queretaro.quadratin.com.mx/aviso-de-privacidad/", "https://oaxaca.quadratin.com.mx/quadratin-pionero-y-lider-nacional-surgido-fuera-del-centro/", "https://www.quadratin.com.mx/politicas/quadratin-crecera-volviendo-a-los-origenes-francisco-garcia-davish/"]
  },
  {
    row: 186, slug: "trafico_zmg", title: "Trafico ZMG",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "metropolitan / state", address: "Avenida Americas 170, Col. Santa Teresita, C.P. 44600, Guadalajara, Jalisco", "city.headq": 14, legal_name: "TZMG Media, S.A. de C.V.", owner_group: "Trafico ZMG / TZMG Media", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / traffic service / social media" },
    assessment: "Guadalajara metropolitan traffic and local-news service. Its terms identify TZMG Media and provide a Guadalajara address.",
    ideology: "Its service-oriented local coverage does not establish a political alignment.",
    uncertainty: "The ultimate owner, founders, founding date and shareholding were not disclosed.",
    sources: ["https://traficozmg.com/nosotros/", "https://traficozmg.com/terminos-y-condiciones/"]
  },
  {
    row: 187, slug: "el_centinela_informa", title: "El Centinela Informa",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Ramon Flores", owner_group: "El Centinela Informa", "founder.name": "Ramon Flores", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "individual commentator / video / social media" },
    assessment: "Personal political-news platform of journalist Ramon Flores, who appears at presidential press conferences under the outlet's name.",
    ideology: "Flores has explicitly written that he is proudly left-wing, and the platform's coverage is broadly favorable to the 4T.",
    uncertainty: "No official website, legal entity, address or launch date was identified; this is primarily a personal social-video outlet.",
    sources: ["https://elsoberano.mx/plumas-patrioticas/periodista-o-palero/", "https://elsoberano.mx/plumas-patrioticas/la-patria-es-primero/", "https://www.infobae.com/mexico/2024/10/18/reportero-revela-en-la-mananera-que-el-juez-brian-cogan-no-comparo-a-garcia-luna-con-el-chapo-guzman-esto-fue-lo-que-le-dijo/?outputType=amp-type"]
  },
  {
    row: 188, slug: "nx_noticias", title: "NX Noticias",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, owner_group: "NX Noticias", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "National digital outlet with extensive federal politics coverage. No transparent masthead, ownership statement or legal notice was located.",
    ideology: "The current homepage and political story selection are consistently favorable to Morena and the 4T, supporting left/aligned with medium rather than high confidence.",
    uncertainty: "High priority: owner, legal entity, founder, start date, address and financing are opaque; ideology is based on observed output rather than institutional disclosure.",
    sources: ["https://nxnoticias.com/"]
  },
  {
    row: 189, slug: "sputnik", title: "Sputnik",
    updates: { state: "Internacional", municipality: "Moscow", CVE_ENT: null, "coverage.scope": "international / Latin America", "city.headq": null, legal_name: "Rossiya Segodnya", owner_group: "Russian government / Rossiya Segodnya", conglomerate: "Russian government", year_founded: 2014, "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "state news agency / radio / digital / social media" },
    assessment: "International Russian state media brand launched in 2014 and operated by Rossiya Segodnya.",
    ideology: "A Mexican left-right label does not map cleanly onto Kremlin state media, so center is used. Its Latin American coverage is generally favorable to the 4T, supporting aligned with medium confidence.",
    uncertainty: "This is foreign state media, not a Mexican newspaper. The 4T label is content-based and should not be read as organizational affiliation.",
    sources: ["https://docs.house.gov/meetings/JU/JU00/20240604/117383/HHRG-118-JU00-20240604-SD017.pdf", "https://www.ofcom.org.uk/make-a-complaint/complain-about-a-video-sharing-platform-vsp/content-or-services-provided-by-tv-novosti-or-rossiya-segodnya?language=en", "https://www.cidob.org/sites/default/files/2024-11/61-68_NICOL%C3%81S%20DE%20PEDRO%20AND%20DANIEL%20IRIARTE_ANG.pdf"]
  },
  {
    row: 190, slug: "rt_actualidad", title: "RT Actualidad",
    updates: { state: "Internacional", municipality: "Moscow", CVE_ENT: null, "coverage.scope": "international / Latin America", "city.headq": null, legal_name: "ANO TV-Novosti", owner_group: "Russian government / TV-Novosti", conglomerate: "Russian government", year_founded: "2005 RT; 2009 Spanish service", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "state television / digital / social media" },
    assessment: "International Russian state-funded television and digital network operated by TV-Novosti; its Spanish service began in 2009.",
    ideology: "Center is used because Kremlin state media does not map cleanly to Mexico's left-right scale. Its Spanish-language treatment of the 4T is generally favorable, supporting aligned with medium confidence.",
    uncertainty: "This is foreign state media, not a Mexican newspaper. The 4T label is content-based, and the parent-brand versus Spanish-service founding dates differ.",
    sources: ["https://www.ofcom.org.uk/make-a-complaint/complain-about-a-video-sharing-platform-vsp/content-or-services-provided-by-tv-novosti-or-rossiya-segodnya?language=en", "https://apnews.com/article/abd51ba03af439cf272888556f424d38", "https://es.wikipedia.org/wiki/RT"]
  },
  {
    row: 191, slug: "diario_presente", title: "Diario Presente",
    updates: { state: "Tabasco", municipality: "Villahermosa", CVE_ENT: 27, "coverage.scope": "state", address: "Av. Pages Llergo 116, esq. Sanchez Magallanes, Col. Nueva Villahermosa, C.P. 86070, Villahermosa, Tabasco", "city.headq": 27, legal_name: "Sistema Informativo de Tabasco, S.A. de C.V.", owner_group: "Grupo Presente Multimedios", "founder.name": "Jorge Calles Broca", year_founded: 1959, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "Tabasco daily founded on 12 February 1959 by Jorge Calles Broca. Its legal page supplies the publisher and Villahermosa address.",
    ideology: "No reliable evidence establishes a durable outlet-wide 4T position.",
    uncertainty: "The current ultimate owner and shareholding are not public; the named group and directors do not by themselves establish individual ownership.",
    sources: ["https://www.diariopresente.mx/terminos", "https://www.diariopresente.mx/amp/tabasco/diario-presente-60-anos-un-puente-entre-sectores-y-generaciones/228596", "https://www.mpm.com.mx/?id=8089B95B-A822-BE3D-9EE5-937966073BB9&r=periodicoInternet%2Fview"]
  },
  {
    row: 192, slug: "la_hoguera", title: "La Hoguera",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, legal_name: "La Hoguera, S. de R.L. de C.V.", owner_group: "La Hoguera", year_founded: 2017, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "National digital outlet whose legal notice identifies La Hoguera, S. de R.L. de C.V.; its site copyright history begins in 2017.",
    ideology: "Current political coverage is consistently favorable to Morena and the 4T, supporting left/aligned with medium confidence.",
    uncertainty: "Owners, founders, shareholding and street address are not disclosed; 2017 is inferred from the site's own copyright history.",
    sources: ["https://lahoguera.mx/aviso-legal/", "https://lahoguera.mx/"]
  },
  {
    row: 193, slug: "quinto_poder", title: "Quinto Poder",
    updates: { state: "Nacional", municipality: "Cuajimalpa", CVE_ENT: null, "coverage.scope": "national", address: "Paseo de los Tamarindos 400-A, Torre 1, Piso 3, Bosques de las Lomas, C.P. 05120, Cuajimalpa, Ciudad de Mexico", "city.headq": 9, legal_name: "Proabri, S.A.P.I. de C.V.", owner_group: "Prowell Media", conglomerate: "Prowell Media", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "National digital outlet operated through Proabri/Prowell Media. Its privacy notice provides the legal company and Mexico City address.",
    ideology: "No reliable evidence establishes a consistent 4T alignment across its news output.",
    uncertainty: "The ultimate owners, founders, start date and shareholding of Proabri/Prowell Media remain undisclosed.",
    sources: ["https://quinto-poder.mx/p/institucional/staff.html", "https://quinto-poder.mx/p/institucional/aviso-de-privacidad.html"]
  },
  {
    row: 194, slug: "bajo_palabra_noticias", title: "Bajo Palabra Noticias",
    updates: { state: "Guerrero", municipality: "Acapulco", CVE_ENT: 12, "coverage.scope": "state / national politics", "city.headq": 12, owner_group: "Bajo Palabra", "founder.name": "Collective of journalists", year_founded: 2015, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "Guerrero digital outlet founded in Acapulco on 9 April 2015 by a group of journalists, with an explicit human-rights and democratic mission.",
    ideology: "Its rights-oriented mission and current favorable treatment of the 4T support left/aligned with medium confidence.",
    uncertainty: "The legal entity, individual owners, exact founder names, financing and street address are not disclosed.",
    sources: ["https://www.bajopalabra.mx/quienes-somos-y-que-hacemos-en-bajopalabra-mx/", "https://www.bajopalabra.mx/"]
  },
  {
    row: 195, slug: "tijuana_comunica", title: "Tijuana Comunica",
    updates: { state: "Baja California", municipality: "Tijuana", CVE_ENT: 2, "coverage.scope": "regional / state", "city.headq": 2, "owner.person": "Victor Lagunas Penalosa", owner_group: "TJ Comunica", "founder.name": "Victor Lagunas Penalosa", year_founded: 2019, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / video / social media" },
    assessment: "Tijuana digital outlet founded on 13 June 2019 by CEO Victor Lagunas Penalosa.",
    ideology: "No reliable evidence establishes a stable partisan or 4T position.",
    uncertainty: "The legal entity, formal ownership shares and street address were not verified; founder/CEO status is not a complete corporate record.",
    sources: ["https://tjcomunica.com/conocenos/", "https://tjcomunica.com/"]
  },
  {
    row: 196, slug: "periodico_zocalo_tele_saltillo", title: "Periodico Zocalo / Tele Saltillo",
    updates: { state: "Coahuila", municipality: "Saltillo", CVE_ENT: 5, "coverage.scope": "regional / multistate", address: "Blvd. Venustiano Carranza 5280, Col. Rancho de Pena, C.P. 25210, Saltillo, Coahuila", "city.headq": 5, legal_name: "Zocalo de Saltillo, S.A. de C.V.", "owner.person": "Francisco Juaristi Santos", "owner.family": "Familia Juaristi", owner_group: "Grupo Zocalo", conglomerate: "Grupo Zocalo", "founder.name": "Francisco Juaristi Septien", year_founded: "1965 group; 2008 Saltillo edition", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / television / radio / digital / social media" },
    assessment: "Family-controlled Coahuila media group founded with Zocalo Piedras Negras in 1965. The Saltillo newspaper edition began in 2008 and the group later expanded into television.",
    ideology: "No reliable evidence supports one stable 4T position across the newspaper editions, radio and television operations.",
    uncertainty: "High priority: the row combines Grupo Zocalo's newspaper and Tele Saltillo. The television operation may have a different legal vehicle, and current shareholding needs confirmation.",
    sources: ["https://www3.zocalo.com.mx/directorio/", "https://www.zocalo.com.mx/entrevista-a-francisco-juaristi-santos-con-el-periodismo-en-la-sangre/", "https://www.zocalo.com.mx/somos-el-esfuerzo-impreso-18-anos-de-zocalo-saltillo/", "https://sic.gob.mx/ficha.php?table=impresos&table_id=129"]
  },
  {
    row: 197, slug: "antitesis_periodismo", title: "Antitesis Periodismo",
    updates: { state: null, municipality: null, CVE_ENT: null, "coverage.scope": "social media", "city.headq": null, owner_group: "Antitesis Periodismo", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "social media page / digital" },
    assessment: "The recorded outlet appears to be a Facebook-centered news page, but no reliable official site, corporate record or independently verified profile was located.",
    ideology: "No evidentiary basis supports a directional label; center/unclear is used as a placeholder rather than a substantive finding.",
    uncertainty: "High priority: confirm the exact Facebook page URL and outlet identity. Location, owner, legal entity, founder, date and operating status are all unresolved.",
    sources: ["https://www.facebook.com/AntitesisPeriodismo/"]
  },
  {
    row: 198, slug: "xinhua", title: "Xinhua",
    updates: { state: "Internacional", municipality: "Beijing", CVE_ENT: null, "coverage.scope": "international", "city.headq": null, legal_name: "Xinhua News Agency", owner_group: "People's Republic of China / State Council", conglomerate: "Chinese state", "founder.name": "Chinese Communist Party", year_founded: 1931, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "state news agency / digital / social media" },
    assessment: "Official Chinese state news agency founded in 1931 and operating an international Spanish-language service.",
    ideology: "Its institutional communist-party lineage supports left on the simple scale. Spanish-language coverage of Mexico is generally favorable to the 4T, supporting aligned with medium confidence.",
    uncertainty: "This is foreign state media, not a Mexican newspaper. The 4T label is content/diplomatic-position based rather than evidence of formal affiliation.",
    sources: ["https://www.xinhuanet.com/company/", "https://english.scio.gov.cn/m/topnews/2021-11/06/content_77856071.htm", "https://www.justice.gov/nsd-fara/letters-determination/xinhua/download"]
  },
  {
    row: 199, slug: "eli_television", title: "Eli Television",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, owner_group: "Eli Television", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "low", "type.media": "individual video channel / social media" },
    assessment: "The row appears to identify a personal video channel represented by a single YouTube link, but the channel owner and stable outlet identity could not be independently verified.",
    ideology: "The recorded video and archive context suggest a pro-4T commentator, but the unresolved identity requires low confidence.",
    uncertainty: "High priority: confirm the channel name, person behind it, canonical URL, location and current activity. No corporate or biographical data were verified.",
    sources: ["https://www.youtube.com/watch?v=rTzfcZC_uXA"]
  },
  {
    row: 200, slug: "diario_imagen", title: "Diario Imagen",
    updates: { state: "Nacional / Quintana Roo edition", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national / regional editions", "city.headq": 9, "owner.person": "Jose Luis Montanez Aguilar", owner_group: "Diario Imagen", "founder.name": "Jose Luis Montanez Aguilar", year_founded: 2005, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "National newspaper with regional editions, founded by director and president Jose Luis Montanez Aguilar. Its twentieth-anniversary coverage supports a 2005 start.",
    ideology: "No reliable evidence establishes a stable left-right or 4T line for the whole publication.",
    uncertainty: "High priority: the workbook listed only Quintana Roo, but the URL is the national outlet. The legal publisher, headquarters address, ownership shares and edition relationship remain unverified.",
    sources: ["https://www.diarioimagen.net/?p=684644", "https://www.diarioimagen.net/?p=217617", "https://www.diarioimagen.net/"]
  },
  {
    row: 201, slug: "ae_grupo_informativo", title: "AE Grupo Informativo",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, owner_group: "AE Grupo Informativo", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / video / social media" },
    assessment: "Digital political-news outlet whose homepage prominently republishes federal government and Morena material and embeds the presidential morning conference.",
    ideology: "The sustained favorable selection and framing of 4T content support left/aligned with medium confidence.",
    uncertainty: "High priority: no legal notice, masthead, owner, founder, launch date, address or financing disclosure was located; ideology rests on observable output.",
    sources: ["https://aegrupoinformativo.com/"]
  },
  {
    row: 202, slug: "agencia_obturador_mx_es_imagen", title: "Agencia Obturador MX / Es Imagen",
    updates: { state: "Puebla / Ciudad de Mexico", municipality: "Puebla", CVE_ENT: 21, "coverage.scope": "multistate / national", "city.headq": 21, owner_group: "Es Imagen / Obturador MX", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "photo agency / digital / social media" },
    assessment: "The recorded URL belongs to Es Imagen, a photo and video agency with state sections. Other media credits use Obturador MX as a contributor or social account.",
    ideology: "A photo-agency role does not establish a stable political alignment; center/unclear is used.",
    uncertainty: "High priority: the row likely conflates Obturador MX with Es Imagen. Confirm whether the intended record is a photographer/account, a partner brand or the agency itself.",
    sources: ["https://esimagen.mx/", "https://esimagen.mx/estado/cdmx/", "https://esimagen.mx/media_album/alianza-enderezando-curvas-y-triple-a/", "https://noticiaslatam.lat/20210613/el-misterioso-socavon-de-puebla-mexico-finalmente-se-traga-la-casa--1113176266.html"]
  },
  {
    row: 203, slug: "diario_la_verdad_venezuela", title: "Diario La Verdad (Venezuela)",
    updates: { state: "Internacional / Venezuela", municipality: "Maracaibo", CVE_ENT: null, "coverage.scope": "regional / Zulia", "city.headq": null, legal_name: "Diario La Verdad Maracaibo Venezuela, C.A.", "owner.person": "Jorge Abudei Marcos (founder)", owner_group: "Diario La Verdad", "founder.name": "Jorge Abudei Marcos", year_founded: 1998, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital newspaper / social media; formerly print" },
    assessment: "The recorded URL resolves to the regional Venezuelan newspaper La Verdad of Maracaibo, founded on 19 April 1998 by Jorge Abudei Marcos and now digital-only.",
    ideology: "A Mexico-specific left-right and 4T position is not established, so center/unclear is used.",
    uncertainty: "Critical mismatch: this URL is not a Mexican outlet. Confirm whether the archive intended a different Diario La Verdad before retaining it in a Mexican-newspaper dataset.",
    sources: ["https://laverdad.com/", "https://laverdad.com/nosotros/"]
  },
  {
    row: 204, slug: "gaceta_del_aire", title: "Gaceta del Aire",
    updates: { state: "Sinaloa", municipality: "Ahome / Los Mochis", CVE_ENT: 25, "coverage.scope": "regional / presidential press coverage", "city.headq": 25, "owner.person": "Mirsa Delia Lopez Rodriguez (director)", owner_group: "Gaceta del Aire", "founder.name": "Hector Francisco Uribe Leon", year_founded: "1960s (reported)", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / radio lineage / social media" },
    assessment: "Los Mochis media project founded by broadcaster Hector Francisco Uribe Leon and currently directed by Mirsa Delia Lopez Rodriguez, known as Mirsa de Uribe.",
    ideology: "Government transcripts document repeated praise for Lopez Obrador and Morena-aligned Sinaloa officials. Combined with consistent pro-4T framing, this supports left/aligned with high confidence.",
    uncertainty: "The current legal entity, ownership transfer, launch year, active address and relationship to the earlier radio service remain unclear; the old radio address is not entered as current.",
    sources: ["https://www.gob.mx/amlo/prensa/version-estenografica-de-la-conferencia-de-prensa-matutina-lunes-29-de-julio-2019", "https://www.gob.mx/amlo/prensa/version-estenografica-de-la-conferencia-de-prensa-matutina-miercoles-3-de-julio-de-2019", "https://fredalvarez.blogspot.com/2023_08_25_archive.html?m=0", "https://www.worldradiohistory.com/INTERNATIONAL/Medios-Publicitarios/MPM-2000-09.pdf"]
  },
  {
    row: 205, slug: "la_opcion_de_chihuahua", title: "La Opcion de Chihuahua",
    updates: { state: "Chihuahua", municipality: "Chihuahua", CVE_ENT: 8, "coverage.scope": "state", address: "Cristobal de Olid 313, Col. San Felipe I, C.P. 31203, Chihuahua, Chihuahua", "city.headq": 8, legal_name: "La Opcion de Chihuahua, S. de R.L. de C.V.", owner_group: "La Opcion de Chihuahua", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Chihuahua digital news outlet. Government and electoral documents identify its legal company, address and representative Manuel Osbaldo Salvador Ang.",
    ideology: "No reliable evidence establishes a stable partisan or 4T position.",
    uncertainty: "The representative is not entered as owner because ultimate ownership, founders and launch date were not verified.",
    sources: ["https://www.laopcion.com.mx/", "https://chihuahua.gob.mx/atach2/sf/uploads/indtfisc/PADRONPROV2015.pdf", "https://portalanterior.ine.mx/archivos3/portal/historico/recursos/IFE-v2/DS/DS-CG/DS-SesionesCG/CG-resoluciones/2013/Mayo/CGext201305-28/CGe280513rp1-3.pdf"]
  },
  {
    row: 206, slug: "diario_plaza_juarez", title: "Diario Plaza Juarez",
    updates: { state: "Hidalgo", municipality: "Pachuca", CVE_ENT: 13, "coverage.scope": "state", address: "Diamante 400, Fracc. Colosio I, C.P. 42088, Pachuca, Hidalgo", "city.headq": 13, legal_name: "Comunicacion Colectiva de Hidalgo, S.A. de C.V.", "owner.family": "Familia Peralta Sanchez", owner_group: "Grupo Editorial Aljibe", "founder.name": "Adalberto Peralta Sanchez; Martin Peralta Sanchez; Javier Peralta Sanchez", year_founded: 2005, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / web radio / social media" },
    assessment: "Hidalgo newspaper founded on 8 February 2005 within Grupo Editorial Aljibe. Anniversary and directory sources identify the Peralta Sanchez brothers and the Pachuca address.",
    ideology: "No reliable evidence supports a stable partisan or 4T position.",
    uncertainty: "Ultimate shareholding is not public, and family/editorial leadership does not prove each brother's current ownership share.",
    sources: ["https://plazajuarez.mx/historico/sobre-nosotros/", "https://plazajuarez.mx/historico/ingles-es-posible-v/", "https://www.mpm.com.mx/?id=8D437E2F-78EA-C0D2-6671-03970AA4E93E&r=periodico%2Fview", "https://plazajuarez.mx/tdb_templates/footer-world-matters/"]
  },
  {
    row: 207, slug: "sonora_power", title: "Sonora Power",
    updates: { state: "Sonora", municipality: "Hermosillo", CVE_ENT: 26, "coverage.scope": "state / national politics", "city.headq": 26, "owner.person": "Demian Duarte", owner_group: "Sonora Power", "founder.name": "Demian Duarte", year_founded: "2024 approximately", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / multimedia / social media" },
    assessment: "Personal editorial and multimedia project of Sonora journalist Demian Duarte, operating between Hermosillo and Mexico City.",
    ideology: "Duarte explicitly identifies with the left, says he covered and supported the Lopez Obrador project, and states that he supports President Sheinbaum. This is direct evidence for left/aligned.",
    uncertainty: "The legal entity, exact launch date, financing, ownership shares and street address are not disclosed; 2024 is inferred from the founder's own chronology.",
    sources: ["https://pxnweb.com/2026/01/23/el-compromiso-del-sonorapower-ayudar-a-construir-un-mejor-futuro/", "https://pxnweb.com/"]
  },
  {
    row: 208, slug: "vigilia_sonora", title: "Vigilia Sonora",
    updates: { state: "Sonora", municipality: null, CVE_ENT: 26, "coverage.scope": "state", "city.headq": 26, "owner.person": "Cayetano Lucero", owner_group: "Vigilia Sonora", "founder.name": "Cayetano Lucero", year_founded: 2011, "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "individual journalism project / Facebook / social media" },
    assessment: "Personal Sonora journalism project founded by Cayetano Lucero on Facebook in 2011, with reporting on social movements, environmental issues and state politics.",
    ideology: "Its long focus on labor, social and environmental movements supports a broad left label, but there is not enough evidence for a stable 4T relationship.",
    uncertainty: "No legal entity, official website, street address or formal ownership record was located; municipality and current operating status need confirmation.",
    sources: ["https://pepesobrevilla.com/2020/05/23/cayetano-lucero-una-historia-desde-las-mananeras/", "https://mediosobson.com/wp-content/uploads/2021/11/edicion-08.pdf"]
  },
  {
    row: 209, slug: "grupo_audiorama", title: "Grupo Audiorama Comunicaciones",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national / multistate", "city.headq": 9, owner_group: "Grupo Audiorama Comunicaciones / Radiorama network", conglomerate: "Radiorama network", year_founded: 2013, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "Private radio and digital group formed around 2013 from stations associated with the wider Radiorama network and operating in multiple states.",
    ideology: "Its many music and news formats do not support a single group-wide political classification.",
    uncertainty: "High priority: Audiorama's corporate separation from Radiorama, ultimate owners, legal entities and station-by-station concession structure are complex and not fully transparent.",
    sources: ["https://www.audiorama.mx/quienes-somos/807", "https://mx.linkedin.com/company/gacom", "https://es.wikipedia.org/wiki/Grupo_Radiorama"]
  },
  {
    row: 210, slug: "perspectivas_mx", title: "Perspectivas MX",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Arturo Suarez Ramirez (director general)", owner_group: "Perspectivas MX", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "National digital outlet whose directory names Arturo Suarez Ramirez as director general and Rafael Lulet as editorial director.",
    ideology: "No reliable evidence establishes a durable partisan position.",
    uncertainty: "A director is not necessarily an owner. The legal entity, shareholders, founder, launch date and street address remain unverified.",
    sources: ["https://perspectivas.mx/directorio/", "https://perspectivas.mx/"]
  },
  {
    row: 211, slug: "noticieros_el_reloj_la_tlaxiaquena", title: "Noticieros El Reloj / La Tlaxiaquena",
    updates: { state: "Oaxaca", municipality: "Heroica Ciudad de Tlaxiaco", CVE_ENT: 20, "coverage.scope": "community / regional", "city.headq": 20, "owner.person": "Ramon Ramirez Gutierrez (director)", owner_group: "La Tlaxiaquena 91.5 FM / Noticieros El Reloj", "founder.name": "Ramon Ramirez Gutierrez", year_founded: "2014 approximately", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "community radio / digital / social media" },
    assessment: "Regional news program and website attached to community station La Tlaxiaquena 91.5 FM, directed by Ramon Ramirez Gutierrez. The station marked roughly ten years of operation in 2024/2025.",
    ideology: "Its community-rights history and direct supportive statements about Lopez Obrador support left/aligned, while its prior watchdog work warrants medium confidence.",
    uncertainty: "The exact launch date is inconsistent in anniversary copy, and the legal concessionaire, ownership structure and address were not verified. The row combines a program and a station.",
    sources: ["https://latlaxiaquena.mx/quienes-somos/", "https://noticieroselreloj.com/la-tlaxiaquena-91-5-celebro-su-decimo-aniversario-con-grandes-eventos-que-fomentan-la-economia-en-tlaxiaco/", "https://www.gob.mx/amlo/articulos/version-estenografica-conferencia-de-prensa-del-presidente-andres-manuel-lopez-obrador-del-24-de-septiembre-de-2024-378697", "https://www.jornada.com.mx/2016/09/05/politica/010n1pol"]
  },
  {
    row: 212, slug: "diario_del_yaqui", title: "Diario del Yaqui",
    updates: { state: "Sonora", municipality: "Ciudad Obregon", CVE_ENT: 26, "coverage.scope": "regional / state", address: "Calle Sinaloa 418 Sur, Col. Centro, C.P. 85000, Ciudad Obregon, Sonora", "city.headq": 26, legal_name: "Editorial Diario del Yaqui, S.A. de C.V.", "owner.person": "Hugo Camou Rodriguez", "owner.family": "Familia Camou", owner_group: "Diario del Yaqui", "founder.name": "Jesus Corral Ruiz", year_founded: 1942, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "Ciudad Obregon daily founded on 9 April 1942 by Jesus Corral Ruiz and acquired in 2017 by businessman Hugo Camou Rodriguez. The current directory names Hugo Camou as board president.",
    ideology: "Historical criticism of state governments and current mixed news coverage do not establish a durable 4T position.",
    uncertainty: "The exact current shareholding and the relationship to Hugo Camou's other businesses require confirmation; ideology is provisional.",
    sources: ["https://diariodelyaqui.mx/directorio", "https://diariodelyaqui.mx/ciudadobregon/arriba-diario-del-yaqui-a-sus-81-anos-de-existencia/64941", "https://www.infocajeme.com/general/2017/12/diario-del-yaqui-tendria-nuevo-propietario/", "https://mpm.sizq.net/?id=1AD53C04-CCDB-CB94-E080-CFDEDF5B27E6&r=periodico%2Fview"]
  },
  {
    row: 213, slug: "zaachila_radio", title: "Zaachila Radio",
    updates: { state: "Oaxaca", municipality: "Villa de Zaachila", CVE_ENT: 20, "coverage.scope": "community / municipal", address: "Tiboot 216, interior H, Barrio San Jacinto, Villa de Zaachila, Oaxaca", "city.headq": 20, "owner.person": "Adan Lopez Santiago (director)", owner_group: "Zaachila Radio 96.3 FM", "founder.name": "Adan Lopez Santiago (community leadership)", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "community radio / social media" },
    assessment: "Community radio station in Villa de Zaachila directed by Adan Lopez Santiago. A university directory provides the station address and contact data.",
    ideology: "Academic research links its leadership to community organizing and the PRD, supporting a broad left label. That history does not establish a current 4T alignment.",
    uncertainty: "The concessionaire/legal entity, formal ownership, precise founding date and current relationship between the director and station governance need verification.",
    sources: ["https://www.umar.mx/servicios_escolares/estancias/Directorio_Huatulco.pdf", "https://ciesas.repositorioinstitucional.mx/jspui/bitstream/1015/513/1/TE%20C.G.%202012%20Andrea%20Calderon%20Garcia.pdf", "https://www.nvinoticias.com/politica/oaxaca/con-permiso-solo-4-radios-comunitarias-en-oaxaca/72917"]
  },
  {
    row: 214, slug: "amarc_mexico", title: "AMARC Mexico / Red de Radios Comunitarias de Mexico",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national network", "city.headq": null, legal_name: "Red de Radios Comunitarias de Mexico, A.C.", owner_group: "AMARC Mexico", conglomerate: "World Association of Community Radio Broadcasters", year_founded: "1992 Mexico work; 2007 current legal entity", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "community-radio association / network" },
    assessment: "National association and network of community and Indigenous radio stations. AMARC began work in Mexico in 1992 and adopted its current Mexican legal entity in 2007.",
    ideology: "Its human-rights, gender, Indigenous communication and alternative-media commitments support a broad left label. It is a plural association, so no 4T alignment is assigned.",
    uncertainty: "This is an association, not a newspaper or single broadcaster. Member stations are editorially autonomous, and a current headquarters address was not verified.",
    sources: ["https://www.amarcmexico.org/es/qu%C3%ADenes-somos", "https://amarcmexico.org/pdf/nacional/01-Informe.pdf"]
  },
  {
    row: 215, slug: "oro_solido", title: "Oro Solido",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Nancy Rodriguez (public owner/representative reported)", owner_group: "Oro Solido", "founder.name": "Nancy Rodriguez", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "personal digital outlet / blog / social media" },
    assessment: "Small personal digital outlet represented at presidential conferences by Nancy Rodriguez. Reporting describes her as its owner, while contract reporting cites Rossana Guadalupe Diaz Avendano as the registered contracting identity.",
    ideology: "Its content, conference interventions and independent descriptions consistently position it as pro-Lopez Obrador and pro-4T, supporting left/aligned with high confidence.",
    uncertainty: "High priority: reconcile Nancy Rodriguez's public identity with the reported contracting name Rossana Guadalupe Diaz Avendano. The legal entity, address, start date and ownership documentation remain unclear.",
    sources: ["https://orosolidomx.wordpress.com/", "https://www.desdelacuna.net/quien/reporteros-periodistas-mananera-presidencia-amlo/", "https://noticaribe.com.mx/2021/11/08/youtubers-asiduos-a-la-mananera-cobran-por-servicios-de-publicidad-en-el-congreso/", "https://www.eluniversal.com.mx/opinion/nestor-ojeda/mas-pobres-mexico-4t-y-amlo-victimas-de-la-desigualdad/"]
  }
];

if (outlets.length !== 50) throw new Error(`Expected 50 outlets, got ${outlets.length}`);

await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(notesDir, { recursive: true });

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("Hoja1");
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
    ["Workbook row", outlet.row], ["Outlet", row[col["name.page"]]], ["State", row[col.state] ?? ""],
    ["Municipality / headquarters", row[col.municipality] ?? ""], ["Coverage", row[col["coverage.scope"]] ?? ""],
    ["Address", row[col.address] ?? ""], ["Legal name", row[col.legal_name] ?? ""],
    ["Owner / controlling person", row[col["owner.person"]] ?? ""], ["Owner family", row[col["owner.family"]] ?? ""],
    ["Owner group", row[col.owner_group] ?? ""], ["Founder", row[col["founder.name"]] ?? ""],
    ["Year founded", row[col.year_founded] ?? ""], ["Ideology (left-right)", row[col["ideology.leftright"]] ?? ""],
    ["4T relationship", row[col["ideology.4t"]] ?? ""], ["Ideology confidence", row[col["ideology.confidence"]] ?? ""],
    ["Media type / platforms", row[col["type.media"]] ?? ""], ["Needs verification", verify]
  ];
  const mdRows = metadata.map(([key, value]) => `| ${key} | ${String(value).replaceAll("|", "\\|")} |`).join("\n");
  const sourceLines = outlet.sources.length ? outlet.sources.map((url, index) => `${index + 1}. ${url}`).join("\n") : "No reliable public source could be assigned because the outlet identity remains unresolved.";
  const md = `# ${outlet.title}\n\nResearch date: ${researchDate}\n\n## Proposed metadata\n\n| Field | Proposed value |\n|---|---|\n${mdRows}\n\n## Evidence summary\n\n${outlet.assessment}\n\n## Ideology rationale\n\n${outlet.ideology}\n\n## Verification note\n\n${outlet.uncertainty}\n\n## Sources\n\n${sourceLines}\n`;
  await fs.writeFile(path.join(notesDir, `${outlet.slug}.md`), md, "utf8");
}

sheet.getRange("AC1:AD215").format.wrapText = true;
sheet.getRange("AC1:AC215").format.columnWidth = 18;
sheet.getRange("AD1:AD215").format.columnWidth = 62;

const check = await workbook.inspect({ kind: "table", range: "Hoja1!A166:AD215", include: "values,formulas", tableMaxRows: 51, tableMaxCols: 30, tableMaxCellChars: 110 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "formula error scan after rows 166-215 update" });
console.log(errors.ndjson);

const after = await workbook.render({ sheetName: "Hoja1", range: "A166:AD215", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_166_215_after.png`, new Uint8Array(await after.arrayBuffer()));
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const flagged = outlets.filter((outlet) => (outlet.verify ?? "yes") === "yes").length;
console.log(JSON.stringify({ outputPath, notes: outlets.length, flagged, notFlagged: outlets.length - flagged }, null, 2));
