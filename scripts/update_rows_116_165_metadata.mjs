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
    row: 116, slug: "la_jornada_maya_yucatan", title: "La Jornada Maya - Yucatan edition",
    updates: { state: "Yucatan", municipality: "Merida", CVE_ENT: 31, "coverage.scope": "regional / peninsular", address: "Calle 43 No. 299D, San Ramon Norte, C.P. 97119, Merida, Yucatan", "city.headq": 31, legal_name: "Medios del Caribe, S.A. de C.V.", owner_group: "La Jornada Maya / Medios del Caribe", conglomerate: "La Jornada", "founder.name": "Fabrizio Leon Diez; Sabina Leon Huacuja", year_founded: 2015, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "One peninsula-wide newspaper with state editions, founded on 6 July 2015 and headquartered in Merida.", ideology: "The La Jornada franchise, founders' account and editorial continuity support left/aligned coding, but the local company is coded with medium confidence.",
    uncertainty: "This is an edition, not a separately owned Yucatan outlet. The franchise and ownership relationship with national La Jornada is not fully public.",
    sources: ["https://www.lajornadamaya.mx/aviso-de-privacidad", "https://www.lajornadamaya.mx/directorio", "https://www.jornada.com.mx/noticia/2025/07/06/opinion/la-jornada-maya-cumple-10-anos", "https://www.lajornadamaya.mx/opinion/249282/la-jornada-maya-una-decada-10-aniversario-juan-carlos-perez-castaneda"]
  },
  {
    row: 117, slug: "la_jornada_maya_quintana_roo", title: "La Jornada Maya - Quintana Roo edition",
    updates: { state: "Quintana Roo", municipality: "Cancun", CVE_ENT: 23, "coverage.scope": "regional / peninsular", address: "Calle 43 No. 299D, San Ramon Norte, C.P. 97119, Merida, Yucatan", "city.headq": 31, legal_name: "Medios del Caribe, S.A. de C.V.", owner_group: "La Jornada Maya / Medios del Caribe", conglomerate: "La Jornada", "founder.name": "Fabrizio Leon Diez; Sabina Leon Huacuja", year_founded: 2015, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Quintana Roo edition of the same peninsula-wide La Jornada Maya operation headquartered in Merida.", ideology: "The La Jornada franchise and documented editorial lineage support left/aligned coding with medium confidence.",
    uncertainty: "The row should be treated as an edition rather than a separately owned outlet. The franchise and corporate-control relationship is not fully public.",
    sources: ["https://www.lajornadamaya.mx/aviso-de-privacidad", "https://www.lajornadamaya.mx/directorio", "https://www.jornada.com.mx/2015/07/06/opinion/022n1pol", "https://pdf.lajornadamaya.mx/LJM-Yuc-18112025.pdf"]
  },
  {
    row: 118, slug: "la_jornada_maya_campeche", title: "La Jornada Maya - Campeche edition",
    updates: { state: "Campeche", municipality: "Campeche", CVE_ENT: 4, "coverage.scope": "regional / peninsular", address: "Calle 43 No. 299D, San Ramon Norte, C.P. 97119, Merida, Yucatan", "city.headq": 31, legal_name: "Medios del Caribe, S.A. de C.V.", owner_group: "La Jornada Maya / Medios del Caribe", conglomerate: "La Jornada", "founder.name": "Fabrizio Leon Diez; Sabina Leon Huacuja", year_founded: 2015, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "Campeche edition of the same peninsula-wide La Jornada Maya operation headquartered in Merida.", ideology: "The La Jornada franchise and documented editorial lineage support left/aligned coding with medium confidence.",
    uncertainty: "The row should be treated as an edition rather than a separately owned outlet. The franchise and corporate-control relationship is not fully public.",
    sources: ["https://www.lajornadamaya.mx/aviso-de-privacidad", "https://www.lajornadamaya.mx/directorio", "https://www.lajornadamaya.mx/opinion/249271/10-anos-10-aniversario-la-jornada-maya", "https://pdf.lajornadamaya.mx/LJM-Yuc-18112025.pdf"]
  },
  {
    row: 119, slug: "sdpnoticias", title: "SDPNoticias",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Federico Arreola", owner_group: "SDPNoticias / Televisa (50% stake reported)", conglomerate: "Televisa (minority/equal stake reported)", "founder.name": "Federico Arreola", year_founded: "2011 digital newspaper; earlier Sendero del Peje", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "Digital outlet created from Federico Arreola's pro-Lopez Obrador blog El Sendero del Peje. Televisa publicly acquired a 50 percent interest.", ideology: "Its origin and recurring favorable treatment of Lopez Obrador support aligned, while center avoids treating a pro-AMLO commercial outlet as consistently ideological left.",
    uncertainty: "The current legal entity and ownership after Televisa's later restructuring require a current filing.",
    sources: ["https://www.sdpnoticias.com/columnas/sdpnoticias-federico-televisa-arreola.html", "https://www.sdpnoticias.com/local/cdmx/sdpnoticias-editorial-mantendra-linea-pese.html", "https://mexico.mom-gmr.org/es/propietarios/propietarios-individuales/detalles/owner/owner/show/federico-arreola/"]
  },
  {
    row: 120, slug: "tiempo_la_noticia_digital", title: "Tiempo La Noticia Digital",
    updates: { state: "Chihuahua", municipality: "Chihuahua", CVE_ENT: 8, "coverage.scope": "state", "city.headq": 8, owner_group: "Tiempo La Noticia Digital", year_founded: 1998, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Chihuahua digital news outlet online since 10 March 1998. Its site names Miguel Fierro Serna as director general and Pedro Fierro Serna as editorial director.", ideology: "No reliable evidence established a stable left-right or 4T position, so center/unclear is the least assumptive label.",
    uncertainty: "The legal entity, ultimate owner and street address were not identified. Directors are not entered as owners without ownership evidence.", sources: ["https://www.tiempo.com.mx/"]
  },
  {
    row: 121, slug: "angulo_7", title: "Angulo 7",
    updates: { state: "Puebla", municipality: "Puebla", CVE_ENT: 21, "coverage.scope": "state", address: "Calle Chopo 110, Interior 4, Col. Gonzalez Ortega, C.P. 72040, Puebla, Puebla", "city.headq": 21, "owner.person": "Tania Yonuhen Damian Jimenez", owner_group: "Angulo 7", "founder.name": "Tania Damian Jimenez; Miguel Hernandez", year_founded: 2013, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / radio web / social media" },
    assessment: "Puebla digital outlet founded on 16 May 2013 by Tania Damian and Miguel Hernandez. The privacy notice identifies Damian as responsible for personal data.", ideology: "No robust independent evidence supports a partisan classification; center/unclear is used with low confidence.",
    uncertainty: "The current legal entity and shareholding are not disclosed, and responsibility for privacy does not prove sole ownership.", sources: ["https://www.angulo7.com.mx/aviso-de-privacidad/", "https://www.angulo7.com.mx/2026/noticias-puebla/angulo-7-celebra-su-13-aniversario-compromiso-con-la-verdad-y-el-periodismo-social/695175/"]
  },
  {
    row: 122, slug: "avan_noticias_quatro_media", title: "Avan Noticias / Quatro Media",
    updates: { state: "Veracruz", municipality: "Xalapa", CVE_ENT: 30, "coverage.scope": "state", "city.headq": 30, "owner.person": "Carlos Ferraez", owner_group: "Quatro Media Telecomunicaciones / Avanradio", year_founded: 2022, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "The strongest match is Veracruz broadcaster Quatro Media Telecomunicaciones, linked in secondary station histories to the former Avanradio structure and Carlos Ferraez.", ideology: "No reliable outlet-specific political evidence was found; center/unclear is provisional.",
    uncertainty: "High priority: the workbook label may conflate Avan Noticias with Quatro Media, and the exact represented station or entity is unclear. Ownership evidence is secondary.",
    sources: ["https://centralelectoral.ine.mx/wp-content/uploads/2024/05/CGex202404-18-ip-16.pdf", "https://en.wikipedia.org/wiki/XHDQ-FM", "https://es.wikipedia.org/wiki/Radi%C3%B3polis"]
  },
  {
    row: 123, slug: "al_calor_politico", title: "Al Calor Politico",
    updates: { state: "Veracruz", municipality: "Xalapa", CVE_ENT: 30, "coverage.scope": "state", address: "Calle Azueta 11, Centro, C.P. 91000, Xalapa, Veracruz", "city.headq": 30, legal_name: "Opciones de Oriente, S.A. de C.V.", owner_group: "Al Calor Politico / Opciones de Oriente", "founder.name": "Joaquin Agustin Rosas Garces", year_founded: 2005, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / streaming / social media" },
    assessment: "Veracruz digital daily founded on 15 March 2005. The state media registry supplies its legal entity, address and founder.", ideology: "The outlet emphasizes an independent and sometimes uncomfortable editorial role, but that does not establish a consistent partisan direction.",
    uncertainty: "The registry's legal representative is not automatically the ultimate owner, and ideology remains unclear.", sources: ["https://pemc.veracruz.gob.mx/medio-comunicacion/al-calor-politico/", "https://www.alcalorpolitico.com/informacion/alcalorpolitico-llego-a-sus-17-anos-de-informar-con-la-verdad-a-los-veracruzanos-364776.html", "https://www.alcalorpolitico.com/informacion/mostrar-la-verdad-compromiso-de-al-calor-politico%3B-somos-y-seguiremos-siendo-incomodos-212435.html"]
  },
  {
    row: 124, slug: "grupo_formula", title: "Grupo Formula",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, legal_name: "Informula, S.A. de C.V.", "owner.family": "Familia Azcarraga Madero", owner_group: "Grupo Formula", conglomerate: "Grupo Formula", "founder.name": "Rogerio Azcarraga Vidaurreta", year_founded: 1930, "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "radio / television / digital / social media" },
    assessment: "National radio and digital group controlled historically by the Azcarraga Madero family. Informula appears as a legal vehicle in official media records.", ideology: "Its principal political programming includes sustained criticism of the 4T, supporting opposition coding, while its varied hosts make center more defensible than a uniform right label.",
    uncertainty: "The exact current controlling individual and the appropriate brand founding date require verification; this is a media group, not a newspaper.", sources: ["https://www.radioformula.com.mx/pages/corporativo.html", "https://especiales.radioformula.com.mx/corporativo_codigodetica/CodigodeEticaGrupoRadioFormula.pdf", "https://mexico.mom-gmr.org/es/propietarios/companias/detalles/company/company/show/grupo-formula/", "https://aplicaciones.iecm.mx/sine/admin/arch1vos/estr4dos/Estrado-2024-09-17_11_28_28-634.pdf"]
  },
  {
    row: 125, slug: "imagen_digital", title: "Imagen Digital",
    updates: { state: "Nacional", municipality: "Coyoacan", CVE_ENT: null, "coverage.scope": "national", address: "Av. Universidad 2014, Col. Copilco Universidad, C.P. 04360, Coyoacan, Ciudad de Mexico", "city.headq": 9, legal_name: "Grupo Imagen Medios de Comunicacion, S.A. de C.V.", "owner.person": "Olegario Vazquez Aldir", "owner.family": "Familia Vazquez Aldir", owner_group: "Grupo Imagen", conglomerate: "Grupo Vazol", year_founded: 2003, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "television / radio / digital / social media" },
    assessment: "Digital-news operation of Grupo Imagen, controlled by the Vazquez Aldir family within Grupo Vazol. The address and legal entity come from the group's privacy notice.", ideology: "Business-family ownership alone does not establish right-wing ideology. The group's mixed coverage supports center/unclear pending content evidence.",
    uncertainty: "The row names a brand rather than a standalone outlet; 2003 is the group's acquisition/relaunch period, not a verified Imagen Digital launch date.", sources: ["https://cdn2.imagen.com.mx/aviso-de-privacidad.html", "https://grupovazol.com/olegario-vazquez-aldir-presenta-la-vision-de-grupo-vazol-una-nueva-identidad-para-un-legado-que-mira-al-futuro/", "https://elpais.com/mexico/2025-03-28/muere-el-empresario-mexicano-olegario-vazquez-rana-a-los-89-anos.html"]
  },
  {
    row: 126, slug: "animal_politico", title: "Animal Politico",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Daniel Eilemberg", owner_group: "Grupo Animal", conglomerate: "Grupo Animal", "founder.name": "Daniel Eilemberg", year_founded: 2010, "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "Independent digital outlet launched in November 2010 and now the flagship of Grupo Animal. Daniel Eilemberg is identified as founder and president.", ideology: "Its sustained accountability investigations and critical coverage of the federal government support opposition coding, but not a right-wing label.",
    uncertainty: "The precise current shareholding, legal vehicle and funding structure need fuller verification.", sources: ["https://grupoanimal.mx/sociedad/jose-luis-anton-alvarado-direccion-general-grupo-animal", "https://grupoanimal.mx/", "https://es.wikipedia.org/wiki/Animal_Pol%C3%ADtico"]
  },
  {
    row: 127, slug: "mvs_noticias", title: "MVS Noticias",
    updates: { state: "Nacional", municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national", address: "Av. Mariano Escobedo 532, Col. Anzures, C.P. 11590, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9, "owner.person": "Joaquin Vargas Guajardo", "owner.family": "Familia Vargas", owner_group: "Grupo MVS", conglomerate: "Grupo MVS", "founder.name": "Joaquin Vargas Gomez", year_founded: 1967, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "National radio/digital news brand within the Vargas family's Grupo MVS, founded by Joaquin Vargas Gomez in 1967.", ideology: "MVS carries varied programs and commentators; no single stable 4T line was established for the brand.",
    uncertainty: "The exact publishing/concession legal entity for MVS Noticias and outlet-level ideology require verification.", sources: ["https://mvsnoticias.com/p/institucional/aviso-de-privacidad.html", "https://grupomvs.com/", "https://www.mexico.mom-gmr.org/es/propietarios/companias/detalles/company/company/show/grupo-mvs/"]
  },
  {
    row: 128, slug: "publimetro", title: "Publimetro Mexico",
    updates: { state: "Nacional", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national", address: "Av. Insurgentes Sur 716, Piso 10, Col. Del Valle, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Publicaciones Metropolitanas, S.A.P.I. de C.V.", owner_group: "Publimetro / Metro International", conglomerate: "Metro International", year_founded: 2006, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico gratuito / digital / social media" },
    assessment: "Mexican edition of the international free-newspaper brand, operating through Publicaciones Metropolitanas.", ideology: "No current evidence supports a consistent Mexican partisan line, so center/unclear is used.",
    uncertainty: "The ultimate ownership of the Mexican edition is opaque, and public sources disagree between 2005 and 2006 for its launch.", sources: ["https://www.publimetro.com.mx/aviso-legal/", "https://mexico.mom-gmr.org/es/medios/detalles/outlet/publimetro/"]
  },
  {
    row: 129, slug: "noticiero_en_redes", title: "Noticiero en Redes",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, owner_group: "Noticiero en Redes", year_founded: "2015 Chiapas; 2017 national", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Platform originating in Chiapas in 2015 and restructured as a national outlet in 2017. It streams the full presidential morning conference.", ideology: "Its own institutional history presents the morning conference and Lopez Obrador's transparency project favorably, supporting left/aligned coding.",
    uncertainty: "The owners, founders, legal entity, address and relationship among regional branches are not publicly identified.", sources: ["https://noticieroenredes.com/quienes-somos/", "https://noticieroenredes.com/informacion-del-equipo-editorial/"]
  },
  {
    row: 130, slug: "grupo_radio_centro", title: "Grupo Radio Centro",
    updates: { state: "Nacional", municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national", address: "Av. Constituyentes 1154, Col. Lomas Altas, C.P. 11950, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9, legal_name: "Grupo Radio Centro, S.A.B. de C.V.", "owner.person": "Francisco Aguirre Gomez", "owner.family": "Familia Aguirre Gomez", owner_group: "Grupo Radio Centro", conglomerate: "Grupo Radio Centro", "founder.name": "Francisco Aguirre Jimenez", year_founded: "1946 origins; 1952 Organizacion Radio Centro", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "Publicly listed radio group founded by Francisco Aguirre Jimenez and controlled by the Aguirre Gomez family, which its 2024 report says holds 69.22 percent.", ideology: "Multiple stations and programs have different editorial voices, so a single partisan label is not supported.",
    uncertainty: "Group-level ownership is clear, but outlet-level ideology cannot be generalized across its stations.", sources: ["https://radiocentro.com/corporativo/historia", "https://radiocentro.com/corporativo/perfil", "https://radiocentro.com/corporativo/privacidad", "https://editorial.radiocentro.com/wp-content/uploads/2025/06/corp_ReporteAnualGRC_2024.pdf"]
  },
  {
    row: 131, slug: "lord_molecula_oficial", title: "Lord Molecula Oficial",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Carlos Pozos Soto", owner_group: "LM Noticias / Lord Molecula", "founder.name": "Carlos Pozos Soto", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "individual commentator / digital / video / social media" },
    assessment: "Personal media brand of journalist and morning-conference participant Carlos Pozos Soto, also known as Lord Molecula.", ideology: "His public role and self-presentation are explicitly favorable to Lopez Obrador and the 4T, supporting left/aligned coding.",
    uncertainty: "This is an individual commentator rather than a newspaper and overlaps the workbook rows naming Lideres Mexicanos and Petroleo y Energia. Legal entity, start date and address remain unclear.", sources: ["https://lmnoticias.com.mx/Quien_es_Lord_Molecula/", "https://www.inep.org/images/2025/TXT/2022-Cortes-choque.pdf"]
  },
  {
    row: 132, slug: "adn40", title: "adn40 / ADN Noticias",
    updates: { state: "Nacional", municipality: "Tlalpan", CVE_ENT: null, "coverage.scope": "national", address: "Av. Insurgentes Sur 3579, Col. Tlalpan La Joya, C.P. 14000, Tlalpan, Ciudad de Mexico", "city.headq": 9, legal_name: "Operadora Mexicana de Television, S.A. de C.V.", "owner.person": "Ricardo Salinas Pliego", "owner.family": "Familia Salinas Pliego", owner_group: "TV Azteca / Grupo Salinas", conglomerate: "Grupo Salinas", year_founded: 2017, "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "high", "type.media": "television / digital / social media" },
    assessment: "National news channel of TV Azteca/Grupo Salinas. The adn40 brand began in March 2017 and has subsequently used ADN Noticias branding.", ideology: "Ricardo Salinas Pliego's sustained public opposition to Morena and the Mexican left, reflected across the group's news platforms, supports right/opposition coding.",
    uncertainty: "The row name may be outdated after a brand change, and this is a television brand rather than a newspaper.", sources: ["https://www.irtvazteca.com/es/estructura-corporativa", "https://www.irtvazteca.com/es/acerca-de-nosotros", "https://www.adn40.mx/especiales/adn40-que-significan-sus-siglas-y-donde-puedo-ver-el-canal-tv/"]
  },
  {
    row: 133, slug: "latinus", title: "Latinus",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Federico Madrazo Rojas; Alexis Nickin Gaxiola (reported financiers/owners)", owner_group: "Latinus Media Group / BCG Limited Consulting / Digital Beacon", "founder.name": null, year_founded: 2020, "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Digital video-news platform founded in 2020. Investigative reporting identifies Federico Madrazo Rojas and Alexis Nickin Gaxiola as central financiers/owners; Carlos Loret de Mola is its best-known journalist, not proven owner.", ideology: "Its editorial identity is strongly and consistently oppositional to the 4T, but opposition alone does not establish a coherent right ideology.",
    uncertainty: "Ownership and financing are politically disputed and split among Mexican and US-linked entities without a transparent official masthead.", sources: ["https://revistaespejo.com/2024/07/06/latinus-y-el-lavado-de-dinero-el-negocio-que-investiga-la-uif/", "https://journalismresearch.org/wp-content/uploads/2024/04/MEXICO-FINANCIAMIENTO-1.pdf", "https://latinus.us/"]
  },
  {
    row: 134, slug: "infobae_mexico", title: "Infobae Mexico",
    updates: { state: "Internacional / Mexico", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "international / national", address: "Calle Montecito 38, Piso 7, Oficina 20, Col. Napoles, C.P. 03810, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Infobae Mexico, S.A. de C.V.", "owner.person": "Daniel Hadad", owner_group: "Infobae / THX Medios", conglomerate: "Infobae", "founder.name": "Daniel Hadad", year_founded: "2002 parent; 2018 Mexico newsroom", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Mexican edition of the Argentine digital outlet founded by Daniel Hadad. Its Mexico terms identify the local company and address; Infobae reported establishing its Mexico newsroom in November 2018.", ideology: "A broad international outlet with varied authors cannot be assigned a reliable Mexico-specific partisan line from the available evidence.",
    uncertainty: "The parent and local corporate relationship is clear at a high level, but Mexico-edition shareholding and a distinct launch date need corporate confirmation.", sources: ["https://www.infobae.com/america/mexico/terminos-y-condiciones/", "https://www.infobae.com/terminos-y-condiciones/", "https://www.infobae.com/noticias/2016/11/17/18-definiciones-de-daniel-hadad-sobre-el-futuro-del-periodismo-digital-2/?outputType=amp-type", "https://www.infobae.com/noticias/2019/07/24/buenas-historias-big-data-y-periodismo-sip-connect-2019-comenzo-en-miami-con-el-caso-de-infobae/?outputType=amp-type"]
  },
  {
    row: 135, slug: "contralinea", title: "Contralinea",
    updates: { state: "Nacional", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national", address: "Jose Maria Velasco 31-2, Col. San Jose Insurgentes, C.P. 03900, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Difusion de Informacion, S.A. de C.V.", "owner.person": "Miguel Badillo", owner_group: "Contralinea / Difusion de Informacion", "founder.name": "Miguel Badillo", year_founded: "2002/2003", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "revista / digital / social media" },
    assessment: "National investigative magazine directed by Miguel Badillo; its current masthead supplies the legal publisher and address.", ideology: "Its long-running anti-neoliberal investigative line and generally favorable treatment of the 4T support left/aligned coding, though it is not entirely uncritical.",
    uncertainty: "Ultimate shareholding and the exact founding year remain unclear; the current masthead says year 23 in 2026 while earlier records vary.", sources: ["https://contralinea.com.mx/wp-content/uploads/2026/01/Contralinea-985.pdf", "https://www2.contralinea.com.mx/directorio/"]
  },
  {
    row: 136, slug: "el_soberano", title: "El Soberano",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, legal_name: "El Soberano RAFTH, S.A. de C.V.", owner_group: "El Soberano", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / social media" },
    assessment: "National digital political outlet operating through El Soberano RAFTH, S.A. de C.V.", ideology: "The outlet explicitly calls itself militant in support of the 4T and obradorista, making left/aligned a high-confidence self-description.",
    uncertainty: "Its ultimate owner, founders, start date and operating address are not disclosed in the sources reviewed.", sources: ["https://elsoberano.mx/aviso-de-privacidad/", "https://elsoberano.mx/2025/01/23/comunicado-nuestras-audiencias-renovacion-en-la-directoccion-editorial/", "https://elsoberano.mx/2024/02/12/el-soberano-el-medio-independiente-numero-uno-de-politica-popular-en-mexico/"]
  },
  {
    row: 137, slug: "unomasuno", title: "unomasuno",
    updates: { state: "Nacional", municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national", address: "Gabino Barreda 86, Col. San Rafael, C.P. 06470, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9, legal_name: "Impulsora de Periodismo Mexicano, S.A.", "owner.person": "Naim Libien Kaui / Naim Libien Tella", "owner.family": "Familia Libien", owner_group: "unomasuno", "founder.name": "Manuel Becerra Acosta", year_founded: 1977, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "Mexico City newspaper founded by Manuel Becerra Acosta in 1977 and sold in 2002 to Naim Libien Kaui.", ideology: "Its historical left identity should not be transferred automatically to the later Libien-owned paper; current ideology is therefore center/unclear.",
    uncertainty: "Current control after legal and financial controversies, the active legal vehicle and current ideology need verification.", sources: ["https://www.jornada.com.mx/2003/03/20/057n2soc.php?origen=soc-jus.html", "https://elpais.com/internacional/2016/09/03/mexico/1472866357_392628.html", "https://es.wikipedia.org/wiki/Unom%C3%A1suno"]
  },
  {
    row: 138, slug: "pie_de_pagina", title: "Pie de Pagina",
    updates: { state: "Nacional", municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national", address: "Milan 20, Col. Juarez, C.P. 06600, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9, legal_name: "Red de Periodistas Sociales - Periodistas de a Pie, A.C.", owner_group: "Periodistas de a Pie", "founder.name": "Periodistas de a Pie collective", year_founded: 2015, "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "Independent journalism project of the civil association Periodistas de a Pie, launched around 2015 with a social and human-rights reporting focus.", ideology: "Its social-justice and human-rights orientation supports left, while independent criticism of governments makes 4T alignment unclear.",
    uncertainty: "Current editorial leadership, funding composition and exact project launch date require confirmation.", sources: ["https://piedepagina.mx/aviso-de-privacidad/", "https://periodistasdeapie.org.mx/2025/04/01/comunicado-de-periodistas-de-a-pie-ante-el-uso-indebido-de-nuestro-nombre-logo-e-identidad-visual/", "https://es.wikipedia.org/wiki/Pie_de_P%C3%A1gina"]
  },
  {
    row: 139, slug: "multimedios", title: "Multimedios",
    updates: { state: "Nuevo Leon", municipality: "Monterrey", CVE_ENT: 19, "coverage.scope": "national / multistate", "city.headq": 19, legal_name: "Multimedios, S.A. de C.V.", "owner.person": "Francisco Dario Gonzalez Albuerne", "owner.family": "Familia Gonzalez", owner_group: "Grupo Multimedios", conglomerate: "Grupo Multimedios", "founder.name": "Jesus Dionisio Gonzalez", year_founded: "1940 group roots; 1968 television", "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "television / radio / digital / social media" },
    assessment: "Monterrey-based television, radio and digital group controlled by the Gonzalez family; it also owns Milenio.", ideology: "Group-level research supports comparatively government-amplifying coverage, coded center/aligned rather than ideological left.",
    uncertainty: "This is a multimedia group, not a newspaper. The political label is group-level and may not describe every program or station.", sources: ["https://mexico.mom-gmr.org/es/propietarios/propietarios-individuales/detalles/owner/owner/show/gonzalez-family-1/", "https://www.multimediostv.com/aviso-privacidad.html", "https://fundacionmultimedios.org/historia", "https://www.multimedios.com/deportes/festeja-multimedios-47-anos-transmision.html"]
  },
  {
    row: 140, slug: "meganoticias", title: "Meganoticias",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "national / multistate", "city.headq": 14, owner_group: "Megacable / Meganoticias", conglomerate: "Megacable Holdings", year_founded: "1997 lineage; 2008 national expansion", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "television / digital / social media" },
    assessment: "Regional television-news network within Megacable. The brand traces to Megacanal in 1997 and expanded/restored national operations in 2008.", ideology: "Its network structure and regional production do not support one stable partisan label.",
    uncertainty: "The precise publishing legal entity, ultimate individual control and relevant founding date for the present network need verification.", sources: ["https://www.meganoticias.mx/cdmx/nosotros", "https://www.meganoticias.mx/cdmx/politicas-de-privacidad", "https://inversionistas.megacable.com.mx/pdf/anual/reporte-anual-2025.pdf"]
  },
  {
    row: 141, slug: "w_radio", title: "W Radio Mexico",
    updates: { state: "Nacional", municipality: "Coyoacan", CVE_ENT: null, "coverage.scope": "national", address: "Calzada de Tlalpan 3000, Col. Espartaco, C.P. 04870, Coyoacan, Ciudad de Mexico", "city.headq": 9, legal_name: "Sistema Radiopolis, S.A. de C.V.", "owner.family": "Familia Aleman (Grupo Coral stake)", owner_group: "Radiopolis / PRISA / Grupo Coral", conglomerate: "Radiopolis", "founder.name": "Emilio Azcarraga Vidaurreta (XEW lineage)", year_founded: "1930 XEW lineage; modern W Radio brand later", "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "radio / digital / social media" },
    assessment: "National talk-radio and news brand operated by Sistema Radiopolis, with historic XEW lineage and ownership linked to PRISA and Grupo Coral.", ideology: "Prominent current-affairs programs include sustained criticism of the 4T, supporting opposition coding, while the network remains editorially mixed.",
    uncertainty: "The current ownership split and the modern W Radio brand launch date require confirmation; the 1930 date belongs to XEW lineage.", sources: ["https://wradio.com.mx/aviso-legal/", "https://wradio.com.mx/estaticos/politica-privacidad/", "https://www.prisa.com/uploads/2026/03/memoria-consolidada-2025.pdf"]
  },
  {
    row: 142, slug: "el_chamuco_media", title: "El Chamuco Media",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, owner_group: "El Chamuco", "founder.name": "Rius; El Fisgon; Hernandez; Helguera; Patricio", year_founded: 1996, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "revista satirica / television / digital / social media" },
    assessment: "Political-satire magazine and television/digital project founded by prominent left-wing cartoonists in 1996.", ideology: "Its founders, themes and sustained editorial posture place it clearly on the left and broadly aligned with the 4T.",
    uncertainty: "The active legal entity, current shareholding and ownership after changes in the founding team are not transparent; the row covers both magazine and show.", sources: ["https://es.wikipedia.org/wiki/El_Chamuco", "https://elchamuco.com.mx/"]
  },
  {
    row: 143, slug: "relax_104_5_fm", title: "Relax 104.5 FM",
    updates: { state: "Estado de Mexico", municipality: "Nezahualcoyotl", CVE_ENT: 15, "coverage.scope": "municipal / regional", "city.headq": 15, owner_group: "Relax 104.5 FM", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "community radio / digital / social media" },
    assessment: "The URL appears to correspond to Relax 104.5 FM in Ciudad Nezahualcoyotl, commonly identified as XHARO-FM.", ideology: "No reliable political-position evidence was found.",
    uncertainty: "High priority: 104.5 is used by other Mexican stations, and the concessionaire, legal entity, address, owners and start date were not verified from primary records.", sources: ["https://www.relax1045.com/contacto-y-detalles", "https://en.wikipedia.org/wiki/XHARO-FM"]
  },
  {
    row: 144, slug: "enfoque_noticias", title: "Enfoque Noticias",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "German Huesca", "owner.family": "Familia Huesca", owner_group: "NRM Comunicaciones", conglomerate: "NRM Comunicaciones", "founder.name": "Edilberto Huesca Perrotin (NRM)", year_founded: "1942 NRM lineage", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "News brand of NRM Comunicaciones, controlled by the Huesca family and currently led by German Huesca.", ideology: "No source reviewed establishes a stable outlet-wide left-right or 4T position.",
    uncertainty: "The date and founder refer to NRM, not necessarily Enfoque Noticias. Brand-level legal entity, address and launch date remain unverified.", sources: ["https://nrm.com.mx/", "https://enfoquenoticias.com.mx/noticias/estamos-siempre-pensando-en-hacer-un-mexico-mejor-sr-german-huesca-presidente-ejecutivo-y-del-consejo-de-administracion-de-nrm-comunicaciones", "https://mexico.mom-gmr.org/es/propietarios/propietarios-individuales/detalles/owner/owner/show/huesca-family-1/", "https://www.eleconomista.com.mx/empresas/Edilberto-Huesca-Perrotin-hereda-un-NRM-Comunicaciones-con-15-millones-de-escuchas-20240731-0105.html"]
  },
  {
    row: 145, slug: "el_chapucero", title: "Efectos Colaterales / El Chapucero",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Ignacio Nacho Rodriguez", owner_group: "El Chapucero", "founder.name": "Ignacio Nacho Rodriguez", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Personal digital political-media platform of Ignacio Nacho Rodriguez; the site states that El Chapucero is his registered trademark.", ideology: "Its commentary is consistently favorable to Lopez Obrador, Morena and the 4T, supporting left/aligned coding.",
    uncertainty: "The row may conflate a program title, Efectos Colaterales, with the parent platform. Legal entity, address and founding year remain unclear.", sources: ["https://www.elchapucero.com/nosotros/", "https://www.elchapucero.com/"]
  },
  {
    row: 146, slug: "aristegui_noticias", title: "Aristegui Noticias",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, legal_name: "SAIO Servicios, S.A. de C.V.", "owner.person": "Carmen Aristegui", owner_group: "Aristegui Noticias", "founder.name": "Carmen Aristegui", year_founded: 2012, "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "digital / radio / video / social media" },
    assessment: "Independent digital investigative outlet founded and directed by Carmen Aristegui; SAIO Servicios administers personal data for the site.", ideology: "Its accountability journalism has been materially critical of the 4T, supporting opposition coding, but its record does not justify a right-wing label.",
    uncertainty: "The administrator named in the privacy notice is not necessarily the owner, and the precise corporate ownership and launch date need confirmation.", sources: ["https://www.aristeguinoticias.com/aviso-de-privacidad/", "https://aristeguinoticias.com/"]
  },
  {
    row: 147, slug: "elefante_blanco", title: "Elefante Blanco",
    updates: { state: "Tamaulipas", municipality: "Ciudad Victoria", CVE_ENT: 28, "coverage.scope": "state", "city.headq": 28, owner_group: "Elefante Blanco", "founder.name": "Carlos Manuel Juarez; Oscar Ramos; Emmanuel Martinez", year_founded: 2021, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Independent Tamaulipas investigative outlet founded on 21 March 2021 by Carlos Manuel Juarez, Oscar Ramos and Emmanuel Martinez.", ideology: "Its human-rights and investigative focus does not by itself establish partisan ideology.",
    uncertainty: "The legal entity, ownership shares, street address and inferred Ciudad Victoria headquarters require confirmation.", sources: ["https://elefanteblanco.mx/quienes-somos/", "https://elefanteblanco.mx/directorio/", "https://territorialmedios.mx/elefante-blanco/"]
  },
  {
    row: 148, slug: "grupo_sol_campeche", title: "Grupo Sol Campeche",
    updates: { state: "Campeche", municipality: "Campeche", CVE_ENT: 4, "coverage.scope": "state", address: "Calle 50 No. 585, Local 24, entre 197 y 199, Col. Plan de Ayala Sur III, Merida, Yucatan", "city.headq": 31, "owner.person": "Pedro Daniel Rodriguez Hernandez", owner_group: "Grupo Sol Corporativo", conglomerate: "Grupo Sol Corporativo", "founder.name": "Pedro Daniel Rodriguez Hernandez", year_founded: "2019 digital; 2021 print", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "semanario impreso / digital / social media" },
    assessment: "Campeche weekly within Grupo Sol Corporativo. Its masthead lists Pedro Daniel Rodriguez Hernandez as director and a Merida office; company history says digital publication began in 2019 and print in 2021.", ideology: "Its stated nonpartisan/investigative posture and mixed coverage do not justify a stronger label.",
    uncertainty: "The office is outside Campeche, and the exact legal entity and ownership shares were not identified.", sources: ["https://campeche.solperiodicos.com.mx/wp-content/uploads/2026/01/EDICION-No199-CAMPECHE-12-18-ENE-026.pdf", "https://laopiniondemexico.mx/editorial-primera-edicion-impresa-en-campeche/", "https://campeche.solperiodicos.com.mx/tag/grupo-sol-corporativo/"]
  },
  {
    row: 149, slug: "el_sol_de_acapulco", title: "El Sol de Acapulco",
    updates: { state: "Guerrero", municipality: "Acapulco", CVE_ENT: 12, "coverage.scope": "regional / state", "city.headq": 12, legal_name: "Compania Periodistica del Sol de Acapulco, S.A. de C.V.", "owner.person": "Paquita Ramos de Vazquez", "owner.family": "Familia Vazquez Rana / Ramos", owner_group: "Organizacion Editorial Mexicana", conglomerate: "Organizacion Editorial Mexicana", "founder.name": "Mauro Jimenez Lazcano", year_founded: 1978, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "Acapulco daily within OEM. Its official page identifies the legal company and creation date of 26 October 1978.", ideology: "No outlet-specific evidence supports a stable partisan classification.",
    uncertainty: "Historical sources vary between 1978 and 1979 and founder details are not on the current official page; ideology is provisional.", sources: ["https://oem.com.mx/elsoldeacapulco/info/directrices-editoriales/", "https://sic.cultura.gob.mx/ficha.php?table=impresos&table_id=207", "https://tesiunamdocumentos.dgb.unam.mx/ptb2010/mayo/0657527/0657527_A1.pdf"]
  },
  {
    row: 150, slug: "agencia_efe", title: "Agencia EFE",
    updates: { state: "Internacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "international", "city.headq": 9, legal_name: "Agencia EFE, S.A.U., S.M.E.", owner_group: "SEPI / Spanish state", conglomerate: "Spanish state", year_founded: 1939, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "news agency / digital / social media" },
    assessment: "International Spanish news agency founded on 3 January 1939 and wholly owned by Spain's state holding company SEPI.", ideology: "Its public-service agency structure and neutrality standards do not support a Mexico-specific 4T position.",
    uncertainty: "This is an international state-owned agency, not a Mexican newspaper. The current Mexico bureau address and Mexico-specific legal registration were not verified.", sources: ["https://verifica.efe.com/que-es-efe-verifica/", "https://agenciaefe.es/historia-de-efe-2/", "https://agenciaefe.es/1939-efe-viene-al-mundo/"]
  },
  {
    row: 151, slug: "gaceta_business_energy", title: "Gaceta Business Energy",
    updates: { state: "Tabasco", municipality: "Villahermosa", CVE_ENT: 27, "coverage.scope": "sector / national", "city.headq": 27, owner_group: "Gaceta Business Energy", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "energy trade publication / digital / social media" },
    assessment: "Energy-sector publication associated publicly with Yesenia Peralta Midence and Tabasco; an alternative WordPress archive remains identifiable.", ideology: "Sector coverage and occasional reproduction of government material do not establish a political alignment.",
    uncertainty: "High priority: legal entity, ownership, founder, dates, address and current operating status were not verified; the original site has limited accessibility.", sources: ["http://www.gacetabusinessenergy.com/", "https://businessenergycom.wordpress.com/", "https://mx.linkedin.com/in/yesenia-peralta-midence-gaceta-petrolera-business-energy-1a450875"]
  },
  {
    row: 152, slug: "lideres_mexicanos_lord_molecula", title: "Lideres Mexicanos / Lord Molecula",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, legal_name: "Ferraez Comunicacion, S.A. de C.V.", "owner.person": "Raul Ferraez", "owner.family": "Familia Ferraez", owner_group: "FCO / Ferraez Comunicacion", conglomerate: "FCO", "founder.name": "Raul Ferraez; Jorge Ferraez", year_founded: 1991, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "revista / digital / social media" },
    assessment: "Business/leadership magazine founded by Raul and Jorge Ferraez around 1991. Carlos Pozos appeared in the morning conference under this publication's name.", ideology: "The magazine's business focus does not justify transferring Lord Molecula's pro-4T position to the outlet.",
    uncertainty: "High priority: the row conflates the outlet with a correspondent/personal brand, and the exact editorial or commercial credentialing relationship is unclear.", sources: ["https://lideresmexicanos.com/entrevistas/vivir-para-crear", "https://www.revistacentral.com.mx/actualidad-revista-central/especiales/notas/entrevista-con-raul-ferraez-presidente-ejecutivo-de-la-revista-lideres-mexicanos/?outputType=amp", "https://lideresmexicanos.com/tendencias/los-reyes-de-la-atencion", "https://www.inep.org/images/2025/TXT/2022-Cortes-choque.pdf"]
  },
  {
    row: 153, slug: "petroleo_y_energia_lord_molecula", title: "Petroleo y Energia / Lord Molecula",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "sector / national", "city.headq": 9, owner_group: "Petroleo y Energia / Ferraez Comunicacion", conglomerate: "FCO / Ferraez Comunicacion", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "trade magazine / digital / social media" },
    assessment: "Mexican energy-sector magazine associated in public records with the Ferraez publishing group. Carlos Pozos also appeared under its name in presidential conferences.", ideology: "Trade coverage and the correspondent's pro-4T personal posture are insufficient to classify the magazine itself as aligned.",
    uncertainty: "High priority: the row conflates the publication and Lord Molecula. Current ownership, legal entity, founder, start date and the credentialing relationship remain unclear.", sources: ["https://petroleoenergia.com/wp-content/uploads/2025/05/REVISTA-Pe_153_DIGITAL.pdf", "https://petroleoenergia.com/wp-content/uploads/2025/04/p326", "https://www.forosreforma.com/eoy/pdf/2015.pdf", "https://www.inep.org/images/2025/TXT/2022-Cortes-choque.pdf"]
  },
  {
    row: 154, slug: "el_astillero", title: "El Astillero",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national", "city.headq": null, "owner.person": "Julio Hernandez Lopez", owner_group: "Julio Astillero", "founder.name": "Julio Hernandez Lopez", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "individual commentator / digital / video / social media" },
    assessment: "Personal news and analysis portal of journalist Julio Hernandez Lopez, built around his longstanding Astillero column and video programming.", ideology: "The portal explicitly fits a critical-left tradition: broadly left but willing to criticize the 4T, so alignment is unclear rather than aligned.",
    uncertainty: "The legal entity, portal launch date and operating address were not identified; this is primarily a commentator-led platform.", sources: ["https://julioastillero.com/redes-sociales/", "https://julioastillero.com/quien-es-quien-en-las-mentiras-de-la-semana-y-julio-astillero-cuestion-de-metodo-autora-ivonne-acuna-murillo/"]
  },
  {
    row: 155, slug: "acustik_noticias", title: "Acustik Noticias",
    updates: { state: "Nacional", municipality: "Cuauhtemoc", CVE_ENT: null, "coverage.scope": "national", address: "Tlacotalpan 38, Col. Roma Sur, C.P. 06760, Cuauhtemoc, Ciudad de Mexico", "city.headq": 9, "owner.person": "Jose Gabriel Gutierrez Lavin", owner_group: "Grupo Acustik Media", conglomerate: "Grupo Acustik Media", "founder.name": "Jose Gabriel Gutierrez Lavin", year_founded: "2012/2015", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / television / digital / social media" },
    assessment: "Multimedia news operation within Grupo Acustik Media. A company article names Jose Gabriel Gutierrez Lavin as president, while directories supply the Mexico City address.", ideology: "No reliable source establishes a stable current partisan line.",
    uncertainty: "Sources conflict on a 2012 versus 2015 founding date, and current leadership and ownership are not transparent.", sources: ["https://acustiknoticias.com/2018/02/grupo-acustik-media-comprometido-la-audiencia-jose-gabriel-gutierrez/", "https://acustiknoticias.com/", "https://mpm.com.mx/?id=28B5F39B-B4AA-4D35-CDFD-9626953A60CE&r=representante%2Fview", "https://www.linkedin.com/company/acustik-noticias"]
  },
  {
    row: 156, slug: "mexico_news_daily", title: "Mexico News Daily",
    updates: { state: "Guanajuato", municipality: "San Miguel de Allende", CVE_ENT: 11, "coverage.scope": "national / international", "city.headq": 11, "owner.person": "Travis Bembenek; Tamanna Bembenek", owner_group: "Mexico News Daily", "founder.name": "Tony Richards", year_founded: 2014, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "English-language Mexican news outlet founded by Tony Richards in San Miguel de Allende on 5 June 2014 and sold in September 2022 to Travis and Tamanna Bembenek.", ideology: "The outlet presents itself as balanced and is not supported by evidence of a stable 4T alignment.",
    uncertainty: "No material uncertainty in the core ownership and history fields; legal entity and street address remain blank because they were not publicly verified.", verify: "no", sources: ["https://mexiconewsdaily.com/news/a-farewell-message-from-founder-tony-richards/", "https://mexiconewsdaily.com/news/introducing-our-new-ceo-travis-bembenek/", "https://mexiconewsdaily.com/ceo-corner/a-day-in-the-life-of-mexico-news-daily-with-our-ceo/"]
  },
  {
    row: 157, slug: "blank_row_157", title: "Blank workbook row 157",
    updates: { state: null, municipality: null, CVE_ENT: null, "coverage.scope": null, address: null, "city.headq": null, legal_name: null, "owner.person": null, "owner.family": null, owner_group: null, conglomerate: null, "founder.name": null, year_founded: null, "ideology.leftright": null, "ideology.4t": null, "ideology.confidence": null, "ideology.source": null, "type.media": null },
    assessment: "The row has no outlet name or URL. Its inherited periodico value has been cleared because there is no identifiable record.", ideology: "No ideology can be assigned without an outlet identity.",
    uncertainty: "High priority: identify the missing outlet from the original archive, or delete the row if it is an accidental blank.", sources: []
  },
  {
    row: 158, slug: "mexico_publica", title: "Mexico Publica",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national / regional editions", "city.headq": null, owner_group: "Grupo Mexico Publica", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / periodic PDF / social media" },
    assessment: "Digital news network producing regional material and periodic PDF editions. Recent editions identify Adolfo Ramos as director general.", ideology: "No independently verified evidence supports a stable partisan line.",
    uncertainty: "Legal entity, ultimate owner, founder, founding date, headquarters and address are not transparent. A director is not entered as owner.", sources: ["https://mexicopublica.mx/", "https://mexicopublica.mx/wp-content/uploads/2025/06/MEX06JUN.pdf"]
  },
  {
    row: 159, slug: "mexico_al_minuto", title: "Mexico al Minuto",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, owner_group: "Mexico al Minuto / Al Minuto network", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "National digital brand publicly described as part of the same network as Yucatan al Minuto and Campeche en Linea, with a Mexico City/WTC presence reported in anniversary coverage.", ideology: "No reliable outlet-level ideological evidence was found.",
    uncertainty: "The legal entity, current owner, founder, launch date and exact address remain unverified; the network relationship is based on associated-outlet reporting.", sources: ["https://mexicoalminuto.com/", "https://notirasa.com/noticia/celebra-yucatan-al-minuto-16-anos-como-lider-informativo-en-el-estado/49522"]
  },
  {
    row: 160, slug: "yucatan_al_minuto", title: "Yucatan al Minuto",
    updates: { state: "Yucatan", municipality: "Merida", CVE_ENT: 31, "coverage.scope": "state", "city.headq": 31, "owner.person": "Jose Miguel Rivero", owner_group: "Yucatan al Minuto / Operadora de Medios de Yucatan (reported)", "founder.name": "Jose Miguel Rivero", year_founded: 2010, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Yucatan digital outlet founded on 1 February 2010 by journalist Jose Miguel Rivero and linked to a network including Mexico al Minuto and Campeche en Linea.", ideology: "Political ownership allegations are disputed and insufficient to assign a partisan ideology.",
    uncertainty: "Critical reporting alleges undisclosed political ownership through Operadora de Medios de Yucatan, but this was not independently proven; current corporate ownership remains opaque.", sources: ["https://www.yucatanalminuto.com/", "https://notirasa.com/noticia/celebra-yucatan-al-minuto-16-anos-como-lider-informativo-en-el-estado/49522", "https://solyucatan.mx/yucatan-al-minuto-recibe-22-mdp/"]
  },
  {
    row: 161, slug: "a_tiempo_tv", title: "A Tiempo TV",
    updates: { state: "Coahuila", municipality: "Saltillo", CVE_ENT: 5, "coverage.scope": "state / national", address: "Prolongacion Irlanda 778-1, Col. Villa Olimpica, C.P. 25230, Saltillo, Coahuila", "city.headq": 5, "owner.person": "Guillermo Flores; Juan Cordova", owner_group: "A Tiempo TV", "founder.name": "Guillermo Flores; Juan Cordova", year_founded: 2017, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / video / social media" },
    assessment: "Coahuila digital platform founded in 2017 by Guillermo Flores and Juan Cordova; its site supplies the Saltillo address and identifies Flores as director.", ideology: "No reliable evidence establishes a stable political alignment.",
    uncertainty: "The site says it operates through a Mexican S.A. de C.V. but does not name it, and current shareholding is not disclosed.", sources: ["https://atiempo.tv/informacion-sobre-propiedad-y-financiacion-a-tiempo-tv/", "https://atiempo.tv/reportaje/la-historia-de-a-tiempo-tv-nuestra-historia/", "https://atiempo.tv/nosotros-2/"]
  },
  {
    row: 162, slug: "contrareplica", title: "ContraReplica",
    updates: { state: "Nacional", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national", address: "San Francisco 612, C.P. 03100, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Ediciones San Francisco, S.A. de C.V.", "owner.person": "Hector Serrano (reported shareholder)", owner_group: "ContraReplica / Ediciones San Francisco", "founder.name": "Ruben Cortes (editorial founder/leader reported)", year_founded: 2018, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico gratuito / digital / social media" },
    assessment: "Free print and digital newspaper operating through Ediciones San Francisco. Reporting at launch linked former politician Hector Serrano to a group of investors.", ideology: "Early political sponsorship reports and mixed subsequent coverage do not establish a durable 4T line.",
    uncertainty: "High priority: ownership is opaque and politically contested; public records show address variants, and the roles of shareholders and editorial founders need confirmation.", sources: ["https://www.contrareplica.mx/privacidad", "https://zacatecas.contrareplica.mx/quienessomos", "https://reposipot.imss.gob.mx/contratos/CABCS/CTPC/DC/Contratos-Convenios/050GYR019N12325-070-00/050GYR019N12325-070-00_Censurado.pdf", "https://www.lapoliticaonline.com/mexico/politica-mx/n-116165-serrano-confirmo-que-forma-parte-de-contrareplica-no-sera-un-medio-contra-morena/"]
  },
  {
    row: 163, slug: "latitude_press", title: "Latitude Press",
    updates: { "name.page": "Latitude Press", state: "Internacional", municipality: null, CVE_ENT: null, "coverage.scope": "international", "city.headq": null, legal_name: "Silo Teachings Collection (nonprofit literary trust)", owner_group: "Latitude Press / Silo Teachings Collection", "founder.name": "Paul Tooby", year_founded: 1992, "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "book publisher / volunteer nonprofit" },
    assessment: "The URL belongs to Latitude Press, a volunteer book publisher founded by Paul Tooby in 1992 and now the imprint of the Silo Teachings Collection.", ideology: "Its New Humanism and nonviolence mission supports a broad left/humanist classification, but it has no identifiable Mexico-specific 4T position.",
    uncertainty: "High priority: the workbook misspells the name as Latitudes press. This is not a Mexican newspaper or news service and may be an erroneous archive match.", sources: ["https://www.latitudepress.com/home", "https://www.latitudepress.com/catalog", "https://www.latitudepress.com/contact"]
  },
  {
    row: 164, slug: "noreste", title: "Noreste",
    updates: { state: "Veracruz", municipality: "Poza Rica", CVE_ENT: 30, "coverage.scope": "state", address: "Calle 16 Oriente s/n, Col. Obrera, C.P. 93260, Poza Rica, Veracruz", "city.headq": 30, legal_name: "Editorial Noreste, S.A. de C.V.", owner_group: "Grupo Noreste", year_founded: 2002, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico / digital / social media" },
    assessment: "Poza Rica newspaper founded on 28 November 2002. Veracruz's media registry provides the publisher, address and state coverage.", ideology: "No reliable evidence establishes a stable partisan position.",
    uncertainty: "The registry names a legal representative, not the ultimate owner; shareholders and ideology remain undisclosed.", sources: ["https://pemc.veracruz.gob.mx/medio-comunicacion/noreste-net/", "https://noreste.net/"]
  },
  {
    row: 165, slug: "los_reporteros_mx", title: "Los Reporteros MX",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Amir Ibrahim", owner_group: "Los Reporteros MX / El Quintana Roo MX", "founder.name": "Amir Ibrahim", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Digital political outlet founded and directed by Amir Ibrahim, who also founded El Quintana Roo MX.", ideology: "Its self-description, programming and participation in pro-4T media networks support left/aligned coding with high confidence.",
    uncertainty: "The legal entity, financing, founding date and address are not transparent; electoral records raise questions about political promotion and financing that require careful manual review.", sources: ["https://uaeh.edu.mx/ful/2023/semblanza/amir-ibrahim-23", "https://www.losreporteros.mx/el-periodista-amir-ibrahim-expone-red-de-empresas-factureras-en-conferencia-matutina-de-claudia-sheinbaum", "https://cms.losreporteros.mx/periodismo-en-redes-sociales/", "https://www.te.gob.mx/EE/SRE/2024/PSC/551/SRE_2024_PSC_551-1533629.pdf"]
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
  const sourceLines = outlet.sources.length ? outlet.sources.map((url, index) => `${index + 1}. ${url}`).join("\n") : "No reliable source can be assigned because the outlet identity is missing.";
  const md = `# ${outlet.title}\n\nResearch date: ${researchDate}\n\n## Proposed metadata\n\n| Field | Proposed value |\n|---|---|\n${mdRows}\n\n## Evidence summary\n\n${outlet.assessment}\n\n## Ideology rationale\n\n${outlet.ideology}\n\n## Verification note\n\n${outlet.uncertainty}\n\n## Sources\n\n${sourceLines}\n`;
  await fs.writeFile(path.join(notesDir, `${outlet.slug}.md`), md, "utf8");
}

sheet.getRange("AC1:AD165").format.wrapText = true;
sheet.getRange("AC1:AC165").format.columnWidth = 18;
sheet.getRange("AD1:AD165").format.columnWidth = 62;

const check = await workbook.inspect({ kind: "table", range: "Hoja1!A116:AD165", include: "values,formulas", tableMaxRows: 51, tableMaxCols: 30, tableMaxCellChars: 110 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "formula error scan after rows 116-165 update" });
console.log(errors.ndjson);

const after = await workbook.render({ sheetName: "Hoja1", range: "A116:AD165", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_116_165_after.png`, new Uint8Array(await after.arrayBuffer()));
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const flagged = outlets.filter((outlet) => (outlet.verify ?? "yes") === "yes").length;
console.log(JSON.stringify({ outputPath, notes: outlets.length, flagged, notFlagged: outlets.length - flagged }, null, 2));
