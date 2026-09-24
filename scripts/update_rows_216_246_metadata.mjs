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
    row: 216, slug: "revista_etcetera", title: "Revista Etcetera",
    updates: { state: "Nacional", municipality: "Benito Juarez", CVE_ENT: null, "coverage.scope": "national", address: "Peten 94, Col. Narvarte, C.P. 03020, Benito Juarez, Ciudad de Mexico", "city.headq": 9, legal_name: "Editora Periodistica y Analisis de Contenidos, S.A. de C.V.", owner_group: "Revista Etcetera", "founder.name": "Raul Trejo Delarbre; Julio Chavez; Jesus Murillo; Ana Luisa Galvan; Marco Levario Turcott", year_founded: "1993 original weekly; 2000 current specialist era", "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "high", "type.media": "digital / former print magazine / social media" },
    assessment: "Mexico City publication devoted to media criticism and national affairs. It began as a political and cultural weekly in 1993, entered a specialist media-analysis era in 2000 and ended regular print circulation in 2018.",
    ideology: "The outlet describes itself as institution-oriented and non-factional, which supports center. Its sustained books, covers and editorials portraying the 4T as deceptive or authoritarian support opposition coding with high confidence.",
    uncertainty: "The legal entity and address are verified, but current shareholders and the distinction between the 1993 title and the 2000 specialist enterprise still need confirmation.",
    sources: ["https://etcetera.com.mx/aviso-de-privacidad/", "https://etcetera.com.mx/codigo-etica/", "https://etcetera.com.mx/editorial/la-revista-etcetera-cumple-17-anos-gracias-ustedes/", "https://www.milenio.com/opinion/rogelio-villarreal/columna-rogelio-villareal/etcetera-la-revista", "https://etcetera.com.mx/opinion/etcetera-periodismo-independiente-prensa-medios-comunicacion/"]
  },
  {
    row: 217, slug: "el_pais_mexico", title: "El Pais Mexico",
    updates: { state: "Nacional / Internacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "Mexico edition / international", "city.headq": 9, legal_name: "Ediciones El Pais, S.L. / PRISA Media", owner_group: "PRISA Media", conglomerate: "PRISA", "founder.name": "Jose Ortega Spottorno", year_founded: "1976 global; 1994 Mexico presence; 2020 Mexico edition", "ideology.leftright": "center", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "periodico / digital / social media" },
    assessment: "The Spanish newspaper was founded in 1976, established a Mexico print presence in 1994 and launched a dedicated Mexico edition in 2020. The brand is operated by PRISA Media.",
    ideology: "Its liberal and plural international profile fits the simple center label. The Mexico edition has regularly scrutinized AMLO and the 4T, supporting opposition coding, although it also publishes diverse contributors.",
    uncertainty: "The row mixes the global title, its Mexico bureau and its dedicated Mexico edition. A current Mexican legal publisher, local office address and ultimate public-company control were not established.",
    sources: ["https://elpais.com/mexico/2026-05-12/32-anos-de-echar-raices-en-mexico-la-primera-edicion-de-el-pais.html", "https://www.prisa.com/marcas/el-pais/", "https://www.prisa.com/nosotros/", "https://elpais.com/mexico/opinion/2024-06-02/lopez-obrador-el-presidente-predicador-estadista-y-agitador.html"]
  },
  {
    row: 218, slug: "sinembargo", title: "SinEmbargo",
    updates: { state: "Nacional", municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national", address: "Ingenieros 31, Col. Escandon II Seccion, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9, legal_name: "Sin Embargo, S. de R.L. de C.V.", "owner.person": "Miguel Valladares; Pablo Valladares (reported owners)", "owner.family": "Familia Valladares", owner_group: "SinEmbargo", "founder.name": "Jorge Zepeda Patterson; Alejandro Paez Varela (reported)", year_founded: 2011, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital news / video / social media" },
    assessment: "National digital outlet operating since 28 April 2011. Its privacy notice identifies the legal entity and Mexico City address, while Media Ownership Monitor attributes ownership to the Valladares brothers.",
    ideology: "Its leadership, commentary and programming consistently approach politics from the left and generally defend the obradorista project while allowing criticism on militarization, security and implementation. The dominant relationship is aligned.",
    uncertainty: "Current equity and the exact founder roles should be checked against corporate records; public profiles differ in how they describe the original management team.",
    sources: ["https://www.sinembargo.mx/aviso-de-privacidad/", "https://www.sinembargo.mx/directorio/", "https://mexico.mom-gmr.org/es/medios/detalles/outlet/sinembargomx/", "https://www.sinembargo.mx/4076464/tres-anos-de-lopez-obrador/", "https://www.sinembargo.mx/alaire/obradorismo-corrupcion-narcos-y-eu-por-alejandro-paez-varela/"]
  },
  {
    row: 219, slug: "es_ahora_am", title: "Es Ahora AM",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national politics", "city.headq": 9, "owner.person": "Alberto Marroquin Espinoza (director/public representative)", owner_group: "Es Ahora AM", "founder.name": "Alberto Marroquin Espinoza", year_founded: "2019 approximately", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / social media" },
    assessment: "Personal digital news and commentary project led by journalist Alberto Marroquin Espinoza. The site marked seven years of Es Ahora AM and coverage of the AMLO-Sheinbaum morning conferences in 2026.",
    ideology: "The brand name, sustained favorable coverage of the transformation and its framing of the presidential conferences support left/aligned with high confidence.",
    uncertainty: "The legal entity, formal ownership, street address and exact start date are not disclosed; the 2019 date is inferred from its anniversary statement.",
    sources: ["https://esahoraam.com/", "https://esahoraam.com/marroquin-interroga-al-presidente-sobre-libertad-sindical-y-politica-juvenil/", "https://reachranking.com/es-ES/youtube/UCQg4DAQmL9pDj7cw_gZL9fA"]
  },
  {
    row: 220, slug: "frecuencia_cad", title: "Frecuencia CAD",
    updates: { state: "Queretaro", municipality: "Queretaro", CVE_ENT: 22, "coverage.scope": "educational / digital", "city.headq": 22, "owner.person": "Alfredo Farias (public representative)", owner_group: "Frecuencia CAD", year_founded: 2019, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "educational podcast / digital" },
    assessment: "A small nonprofit knowledge-diffusion podcast and digital project. Public profiles connect it to Alfredo Farias and Queretaro, and Apple Podcasts lists activity from 2019 to 2022.",
    ideology: "No reliable evidence supports a stable political ideology or relationship to the 4T, so center/unclear is used.",
    uncertainty: "High priority: this appears to be an educational podcast rather than a news outlet. Its current operating status, legal entity, ownership, address and connection to the archive record require confirmation.",
    sources: ["https://podcasts.apple.com/us/podcast/frecuencia-cad/id1470848358", "https://mx.linkedin.com/in/alfredo-far%C3%ADas-42b2115"]
  },
  {
    row: 221, slug: "nacion_14", title: "Nacion 14",
    updates: { state: "Nacional / Tamaulipas / San Luis Potosi", municipality: null, CVE_ENT: null, "coverage.scope": "national / state politics", "city.headq": null, "owner.person": "Carlos Dominguez (director/public representative)", owner_group: "Nacion 14", "founder.name": "Carlos Dominguez (to verify)", year_founded: "2019 approximately", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / social media" },
    assessment: "National and state-politics digital outlet directed and represented by Carlos Dominguez, with roots in Tamaulipas and later reporting in San Luis Potosi.",
    ideology: "Academic analysis describes Nacion 14 as favorable to the 4T, and Dominguez's own opinion writing explicitly rejects the PRIAN and defends the transformation. This supports left/aligned with high confidence.",
    uncertainty: "The legal entity, formal owner, address and exact launch date remain undisclosed. Carlos Dominguez is verified as director, but founder and shareholder status require confirmation.",
    sources: ["https://nacion14.com/", "https://nacion14.com/author/cdomingueznacion14-com/", "https://nacion14.com/estan-desesperados-oposicion-pensaba-que-5-anos-olvidariamos-sus-malos-gobiernos/", "https://mvsnoticias.com/entrevistas/2026/6/5/acusan-hector-serrano-de-ir-contra-periodistas-por-ley-ia-742077.html", "https://www.inep.org/images/2025/TXT/2022-Cortes-choque.pdf"]
  },
  {
    row: 222, slug: "tiempo_la_noticia_digital_duplicate_row_222", title: "Tiempo La Noticia Digital",
    updates: { state: "Chihuahua", municipality: "Chihuahua", CVE_ENT: 8, "coverage.scope": "state", "city.headq": 8, owner_group: "Tiempo La Noticia Digital", year_founded: 1998, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Chihuahua digital news outlet online since 10 March 1998. Its site names Miguel Fierro Serna as director general and Pedro Fierro Serna as editorial director.",
    ideology: "No reliable evidence established a stable left-right or 4T position, so center/unclear is the least assumptive label.",
    uncertainty: "This is a duplicate of workbook row 120. The legal entity, ultimate owner and street address remain unidentified; directors are not entered as owners without ownership evidence.",
    sources: ["https://www.tiempo.com.mx/"]
  },
  {
    row: 223, slug: "the_mexico_news_meme_yamel", title: "The Mexico News / Meme Yamel",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national politics", "city.headq": 9, "owner.person": "Meme Yamel Contreras Abraham (director/public representative)", owner_group: "The Mexico News", "founder.name": "Meme Yamel Contreras Abraham (to verify)", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "digital / video / podcast / social media" },
    assessment: "Digital outlet directed and publicly represented by Meme Yamel Contreras Abraham, who also operates the Al Chile program and personal social channels.",
    ideology: "UNAM's PUEDJS describes her as a voice that promotes the transformation from alternative media, while her public programming repeatedly defends AMLO and the 4T. This supports left/aligned with high confidence.",
    uncertainty: "The legal entity, formal ownership, street address, founder status and exact launch date were not verified; the outlet overlaps substantially with Meme Yamel's personal brand.",
    sources: ["https://themexico.news/", "https://puedjs.unam.mx/presentacion-goooya-3-2/", "https://puedjs.unam.mx/la-transformacion-de-democratica-en-disputa/", "https://www.gob.mx/segob/prensa/version-estenografica-palacio-nacional-1-de-febrero-de-2021-conferencia-de-prensa-encabezada-por-la-secretaria-de-gobernacion-olga-sanchez-cordero", "https://centralelectoral.ine.mx/2022/03/31/version-estenografica-del-segundo-foro-nacional-de-discusion-sobre-la-revocacion-de-mandato/"]
  },
  {
    row: 224, slug: "politica_y_rock_and_roll_radio", title: "Politica y Rock and Roll Radio",
    updates: { state: "Sonora", municipality: "Hermosillo", CVE_ENT: 26, "coverage.scope": "community / local", address: "Av. Nayarit 149-A, Col. San Benito, Hermosillo, Sonora", "city.headq": 26, legal_name: "Autogestion Comunicativa, A.C.", owner_group: "Politica y Rock and Roll Radio / XHSILL-FM", "founder.name": "Alejandro Cabral Porchas and community collective (reported)", year_founded: "2012 project; 2016 licensed FM", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "community radio / digital / social media" },
    assessment: "Hermosillo community radio project that evolved from a program into XHSILL-FM 106.7. Public records identify Autogestion Comunicativa, A.C. and its Hermosillo address.",
    ideology: "Its community-radio model and political/cultural programming support a broad left label. Available evidence does not establish a stable relationship with the 4T.",
    uncertainty: "The founding team, current governance, exact transition dates and editorial position toward the 4T need confirmation. The row combines the program, web brand and licensed station.",
    sources: ["https://sisa.unison.mx/constancias/22290_30_4335_6967_0.pdf", "https://en.wikipedia.org/wiki/XHSILL-FM", "https://www.comecso.com/wp-content/uploads/2018/02/PROGRAMA-SIMPOSIO-VERSION-13-FEB-18.pdf"]
  },
  {
    row: 225, slug: "proyecto_puente_sonora", title: "Proyecto Puente de Sonora",
    updates: { state: "Sonora", municipality: "Hermosillo", CVE_ENT: 26, "coverage.scope": "state / regional", address: "Garmendia 202-D, esquina Coahuila, Col. Centro, C.P. 83000, Hermosillo, Sonora", "city.headq": 26, legal_name: "Sistema Estatal de Informacion Web, S.A. de C.V.", owner_group: "Proyecto Puente", "founder.name": "Luis Alberto Medina", year_founded: 2010, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / radio / video / social media" },
    assessment: "Sonora news project founded by journalist Luis Alberto Medina on 16 November 2010. Its official directory and privacy notice identify its director, legal entity and Hermosillo address.",
    ideology: "The outlet publishes broad local reporting and interviews across political camps. No reliable evidence supports a stable left-right or 4T position.",
    uncertainty: "Luis Alberto Medina is verified as founder and director, not as shareholder. The current ultimate owner and equity structure remain unverified.",
    sources: ["https://proyectopuente.com.mx/directorio/", "https://proyectopuente.com.mx/privacidad/", "https://proyectopuente.com.mx/quienes-somos-proyecto-puente/"]
  },
  {
    row: 226, slug: "grupo_radiorama", title: "Grupo Radiorama",
    updates: { state: "Nacional", municipality: "Miguel Hidalgo", CVE_ENT: null, "coverage.scope": "national / multistate", address: "Paseo de la Reforma 2620, Piso 2, Col. Lomas Altas, C.P. 11950, Miguel Hidalgo, Ciudad de Mexico", "city.headq": 9, legal_name: "Grupo Radiorama, S.A. de C.V. (to verify by station)", "owner.family": "Familias Perez de Anda y Pereda", owner_group: "Grupo Radiorama", conglomerate: "Grupo Radiorama", "founder.name": "Javier Perez de Anda; Adrian Pereda Lopez", year_founded: 1970, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "radio / digital / social media" },
    assessment: "National radio network founded on 9 December 1970 by Javier Perez de Anda and Adrian Pereda Lopez. Its official site provides the Mexico City headquarters address.",
    ideology: "The network contains many music, talk and news stations with local affiliations, so one group-wide ideological or 4T classification is not defensible.",
    uncertainty: "High priority: ownership and concession structures vary by station, affiliates may not be controlled uniformly, and current family shareholding needs corporate verification.",
    sources: ["https://www.radiorama.mx/", "https://www.radiorama.mx/privacidad.php", "https://tesiunamdocumentos.dgb.unam.mx/ptd2021/junio/0812688/0812688.pdf", "https://es.wikipedia.org/wiki/Grupo_Radiorama"]
  },
  {
    row: 227, slug: "informando_la_transformacion", title: "Informando la Transformacion",
    updates: { state: "Baja California Sur / Nacional", municipality: "La Paz", CVE_ENT: 3, "coverage.scope": "state / national politics", "city.headq": 3, "owner.person": "Julio Omar Gomez Sanchez", owner_group: "Informando la Transformacion / Medios Digitales del Pacifico / Sin Puntos Ni Comas", "founder.name": "Julio Omar Gomez Sanchez", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "personal digital outlet / video / social media" },
    assessment: "Personal digital operation run by Julio Omar Gomez Sanchez, who identifies with Medios Digitales del Pacifico and Sin Puntos Ni Comas and reports extensively on Baja California Sur and the presidential conferences.",
    ideology: "The explicit slogan Informando la Transformacion, its government-forward content and sustained participation in AMLO's conferences support left/aligned with high confidence.",
    uncertainty: "The legal entity, formal ownership of the related brands, street address and launch date remain unknown. Several names may describe one personal operation rather than separate outlets.",
    sources: ["https://julioomargs.com/", "https://www.te.gob.mx/EE/SUP/2024/REP/409/SUP_2024_REP_409-1376465.pdf", "https://www.te.gob.mx/media/SentenciasN/pdf/especializada/SRE-PSC-0062-2022.pdf", "https://www.publimetro.com.mx/nacional/2024/09/30/quien-es-el-periodista-que-gano-el-reloj-de-amlo-en-su-ultima-mananera/"]
  },
  {
    row: 228, slug: "el_lead_de_mexico", title: "El Lead de Mexico",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national politics", "city.headq": 9, "owner.person": "Verenice Tellez (public representative)", owner_group: "El Lead de Mexico", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "digital / social media" },
    assessment: "Small Mexico City digital outlet publicly represented at presidential conferences by Verenice Tellez. Electoral judgments and government transcripts verify the brand and her representation.",
    ideology: "Her conference interventions repeatedly framed the opposition through the 4T's political language and enabled favorable responses from AMLO. This supports aligned; left is provisional because a full editorial archive was not available.",
    uncertainty: "High priority: no stable official ownership page, legal entity, founder, address or launch date was located. Verenice Tellez is a representative, not a verified owner.",
    sources: ["https://www.te.gob.mx/sentenciasHTML/convertir/expediente/SUP-REP-0008-2025", "https://www.te.gob.mx/EE/SRE/2024/PSC/236/SRE_2024_PSC_236-1441790.pdf", "https://www.inm.gob.mx/gobmx/word/index.php/columnas-de-opinion-101123/", "https://www.elleaddemexico.mx/category/el-lead-de-hoy/portada/politica"]
  },
  {
    row: 229, slug: "la_grillotina_politica", title: "La Grillotina Politica",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "state / national politics", "city.headq": 14, "owner.person": "Maria Luisa Estrada Hernandez", owner_group: "La Grillotina Politica", "founder.name": "Maria Luisa Estrada Hernandez", year_founded: "2020 approximately", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "personal digital / video / social media" },
    assessment: "Independent Guadalajara digital and video outlet led by journalist Maria Luisa Estrada Hernandez, who is repeatedly identified as its owner or director and public representative.",
    ideology: "Its anti-establishment and earlier pro-AMLO interventions support a broad left label, but later criticism and issue-specific conflicts make its 4T relationship unclear.",
    uncertainty: "The legal entity, address, formal ownership record and exact start date remain unverified; the 2020 date is based on the public account timeline.",
    sources: ["https://www.te.gob.mx/media/SentenciasN/pdf/especializada/SRE-PSC-0062-2022.pdf", "https://documentos.intelicast.net/pdfs/26062025Excelsior5.pdf", "https://fiplatina.press/nota/mexico-la-periodista-maria-luisa-estrada-sufrio-un-ataque-armado-en-guadalajara"]
  },
  {
    row: 230, slug: "movimiento_consciencia", title: "Movimiento Consciencia",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "advocacy / national", "city.headq": null, legal_name: "Fundacion Internacional por el Reconocimiento de la Consciencia y de los Derechos de los Animales", owner_group: "Movimiento Consciencia", "asociacion.name": "Movimiento Consciencia", "asociacion.legal": "Fundacion Internacional por el Reconocimiento de la Consciencia y de los Derechos de los Animales", year_founded: 2012, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "advocacy organization / digital / social media" },
    assessment: "Animal-rights advocacy organization established on 24 October 2012. It publishes news and campaign material but is not primarily a newspaper.",
    ideology: "Its rights-based advocacy fits a broad left label, and its account of working through AMLO's morning conference to obtain a constitutional animal-protection reform supports aligned with medium confidence.",
    uncertainty: "The exact legal form, board, founders, headquarters and ownership do not map cleanly onto newspaper metadata. Current governance should be confirmed with association records.",
    sources: ["https://movimientoconsciencia.com/quienes-somos/", "https://movimientoconsciencia.com/category/noticias/movimiento-consciencia/", "https://movimientoconsciencia.com/entre-a-la-mananera-para-pedirle-al-presidente-que-salvara-la-vida-de-un-guajolote-y-sali-con-una-reforma-constitucional-de-proteccion-animal/"]
  },
  {
    row: 231, slug: "puente_libre_mx", title: "PuenteLibreMX",
    updates: { state: "Chihuahua", municipality: "Ciudad Juarez", CVE_ENT: 8, "coverage.scope": "regional / state", "city.headq": 8, owner_group: "Puente Libre", year_founded: 2008, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Ciudad Juarez digital news outlet online since 16 June 2008, with regional coverage of Chihuahua and the border.",
    ideology: "No robust evidence supports a durable left-right or 4T relationship, so center/unclear is used.",
    uncertainty: "High priority: the legal entity, owner, founder, street address and any relationship to similarly named Chihuahua media remain unresolved.",
    sources: ["https://puentelibre.mx/local/es-", "https://ieechihuahua.org.mx/estrados/0/2/11626.pdf"]
  },
  {
    row: 232, slug: "marco_olvera_oficial", title: "Marco Olvera Oficial",
    updates: { state: "Hidalgo / Nacional", municipality: "San Agustin Tlaxiaca", CVE_ENT: 13, "coverage.scope": "national politics / personal", "city.headq": 13, "owner.person": "Marco Antonio Olvera", owner_group: "Marco Olvera Oficial", "founder.name": "Marco Antonio Olvera", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "personal digital / video / social media" },
    assessment: "Personal channel and site of journalist Marco Antonio Olvera, who has represented several outlets at presidential conferences and has ties to Hidalgo reporting.",
    ideology: "Repeated defenses of AMLO, attacks on perceived opponents and independent descriptions of Olvera as an especially pro-4T conference participant support left/aligned with high confidence.",
    uncertainty: "The recorded website is unavailable, and the legal entity, address, launch date and relationship among Marco Olvera Oficial, Enfasis, Bajo Palabra and Hidalgo News are unresolved.",
    sources: ["https://lalupa.mx/2025/07/02/marco-olvera-quien-cuestiono-a-sheinbaum-sobre-el-batan-sin-credibilidad-periodistica/", "https://www.infobae.com/mexico/2023/08/17/reportero-defiende-a-amlo-tras-criticas-por-caso-lagos-de-moreno-llama-verduleros-a-sus-colegas-perro-con-hueso-ni-muerde-ni-ladra/", "https://www.inep.org/images/2025/TXT/2022-Cortes-choque.pdf", "https://funsalud.org.mx/wp-content/uploads/2020/09/Salud-en-la-Prensa-Digital-del-29-de-septiembre-de-2020.pdf"]
  },
  {
    row: 233, slug: "portal_guanajuato", title: "Portal Guanajuato",
    updates: { state: "Guanajuato", municipality: "Guanajuato", CVE_ENT: 11, "coverage.scope": "state / local", "city.headq": 11, "owner.person": "Jorge Olmos Fuentes (director; ownership not established)", owner_group: "Portal Guanajuato / i-geteo", year_founded: 2010, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / social media" },
    assessment: "Guanajuato digital news project created in early 2010 as part of i-geteo. Its official about page names Jorge Olmos Fuentes as director general and Carlos Olvera as editorial coordinator.",
    ideology: "No reliable evidence establishes a stable partisan or 4T editorial line, so center/unclear is used.",
    uncertainty: "A director is not necessarily an owner. The legal entity, shareholder structure, founders, address and current relationship to i-geteo remain unverified.",
    sources: ["https://portalguanajuato.mx/acerca/", "https://portalguanajuato.mx/"]
  },
  {
    row: 234, slug: "el_defensor_de_la_verdad", title: "El Defensor de la Verdad",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "national politics / personal", "city.headq": 14, "owner.person": "Fernando Carmona (host/public representative)", owner_group: "Grupo Brolan (reported incubator)", "founder.name": "Fernando Carmona / Grupo Brolan (to verify)", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "personal digital / video / social media" },
    assessment: "Pro-4T video and social-media channel associated with host Fernando Carmona and reported as part of the Guadalajara-based Grupo Brolan network.",
    ideology: "Independent reporting places the channel in an explicitly pro-AMLO media network, supporting left/aligned with high confidence.",
    uncertainty: "High priority: Fernando Carmona is the public face, but legal ownership, the exact role of Grupo Brolan, launch date, address and current status need confirmation.",
    sources: ["https://www.am.com.mx/opinion/2019/05/13/los-youtubers-el-debate-publico-383234.html", "https://raichali.com/2021/05/17/youtubers-en-pandemia/"]
  },
  {
    row: 235, slug: "el_charro_politico", title: "El Charro Politico",
    updates: { state: "Jalisco", municipality: "Guadalajara", CVE_ENT: 14, "coverage.scope": "national politics / personal", "city.headq": 14, "owner.person": "Juncal Solano (host/public representative)", owner_group: "Grupo Brolan (reported)", "founder.name": "Juncal Solano / Grupo Brolan (reported)", year_founded: 2016, "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "personal digital / video / social media" },
    assessment: "Political YouTube and social-media channel fronted by Juncal Solano. Academic research dates the channel to 7 March 2016, and reporting links it to Grupo Brolan.",
    ideology: "Academic and press sources identify Solano as a defender of AMLO's government and later a Morena candidate, supporting left/aligned with high confidence.",
    uncertainty: "The formal owner, legal entity, revenue structure, street address and exact corporate relationship to Grupo Brolan remain unverified.",
    sources: ["https://www.scielo.org.mx/scielo.php?pid=S2448-64422022000300693&script=sci_arttext", "https://www.eluniversal.com.mx/estados/morena-premia-con-candidaturas-estos-5-youtubers-afines-la-4t/", "https://www.am.com.mx/opinion/2019/05/13/los-youtubers-el-debate-publico-383234.html"]
  },
  {
    row: 236, slug: "on_noticias", title: "ON Noticias",
    updates: { state: "San Luis Potosi", municipality: "Rioverde", CVE_ENT: 24, "coverage.scope": "state / regional", "city.headq": 24, "owner.person": "Omar Alejandro Nino Perez (director/public representative)", owner_group: "ON Noticias / ON San Luis", "founder.name": "Omar Alejandro Nino Perez (to verify)", year_founded: "2017 or earlier", "ideology.leftright": "left", "ideology.4t": "aligned", "ideology.confidence": "high", "type.media": "periodico impreso / digital / social media" },
    assessment: "San Luis Potosi outlet directed by Omar Alejandro Nino Perez. The CNDH verifies that ON Noticias operates in print and digital form and distributed a free print edition in Rioverde.",
    ideology: "Nino and collaborator Carlos Dominguez have been independently described as favorable to AMLO, and Nino publicly characterized the morning conferences as formative. This supports left/aligned despite strong local criticism of the state government.",
    uncertainty: "The legal publisher, owner, address, exact launch date and relationship among ON Noticias, ON San Luis and Omar Nino Noticias remain unverified. Director status does not prove ownership.",
    sources: ["https://hist.cndh.org.mx/documento/cndh-brinda-apoyo-al-periodista-omar-alejandro-nino-perez-director-del-medio-noticias", "https://www.jornada.com.mx/2017/08/31/sociedad/038n1soc", "https://onsanluis.mx/", "https://www.infobae.com/mexico/2024/07/19/youtuber-asegura-que-ir-a-la-mananera-de-amlo-fue-como-una-segunda-universidad-fue-mucho-mejor-que-una-maestria/"]
  },
  {
    row: 237, slug: "rompeviento_tv", title: "Rompeviento TV",
    updates: { state: "Nacional", municipality: "Ciudad de Mexico", CVE_ENT: null, "coverage.scope": "national", "city.headq": 9, "owner.person": "Ernesto Ledesma (director; ownership not established)", owner_group: "Rompeviento TV", "founder.name": "Multidisciplinary founding collective", year_founded: 2011, "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "nonprofit digital television / video / podcast / social media" },
    assessment: "Nonprofit internet television outlet founded in 2011 by a multidisciplinary collective and directed by Ernesto Ledesma. It focuses on human rights, corruption, violence and social issues.",
    ideology: "Its progressive, rights-oriented agenda supports a broad left label. It has aired both sympathetic and sharply critical assessments of AMLO and directly challenged him on violence, so unclear is the best 4T label.",
    uncertainty: "The legal entity, governing board, founders' names, physical address and current ownership structure were not identified. SembraMedia's profile should be cross-checked with the outlet.",
    sources: ["https://www.rompeviento.tv/", "https://directorio.sembramedia.org/rompeviento-tv/", "https://www.rompeviento.tv/author/ernesto-ledesma/", "https://www.eluniversal.com.mx/nacion/video-amlo-tiene-encontronazo-con-reportero-en-la-mananera-y-lo-acusa-de-hacer-politiqueria/"]
  },
  {
    row: 238, slug: "iztaccihuatl_en_el_sendero_de_la_luna", title: "Iztaccihuatl en el Sendero de la Luna",
    updates: { state: "Estado de Mexico", municipality: "Amecameca", CVE_ENT: 15, "coverage.scope": "community / regional", "city.headq": 15, legal_name: "La Voladora Comunicacion, A.C.", owner_group: "La Voladora Radio", "founder.name": "Angelica Carrasco and program collective (to verify)", "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "community radio program / digital / social media" },
    assessment: "Program carried by community station La Voladora Radio in Amecameca, focused on women, history and community discussion and presented by Angelica Carrasco and collaborators.",
    ideology: "Its feminist and community-rights focus supports a broad left label. No reliable evidence establishes a consistent 4T relationship.",
    uncertainty: "This row is a program, not a standalone outlet. Its start date, program ownership, complete founding team and current schedule need verification.",
    sources: ["https://lavoladora.org/shows/iztaccihuatl-en-el-sendero-de-la-luna/", "https://www.te.gob.mx/media/SentenciasN/pdf/especializada/SRE-PSC-0062-2022.pdf"]
  },
  {
    row: 239, slug: "alianza_de_medios_periodistas_de_a_pie", title: "Alianza de Medios de Periodistas de a Pie",
    updates: { state: "Nacional", municipality: null, CVE_ENT: null, "coverage.scope": "national network / multistate", "city.headq": null, legal_name: "Red de Periodistas de a Pie, A.C.", owner_group: "Alianza de Medios / Red de Periodistas de a Pie", "founder.name": "Collective of local independent media", year_founded: 2018, "ideology.leftright": "left", "ideology.4t": "unclear", "ideology.confidence": "medium", "type.media": "media alliance / network / digital" },
    assessment: "Alliance launched publicly in October 2018 under Red de Periodistas de a Pie, initially grouping 12 local outlets and later described as 15 independent media across multiple states.",
    ideology: "Its human-rights, feminist, social and community journalism commitments support a broad left label. Member outlets retain editorial autonomy, so no alliance-wide 4T position is assigned.",
    uncertainty: "This is an alliance rather than a single outlet. The archive label's reference to Altavoz could not be reconciled with the official member lists, which have also changed over time.",
    sources: ["https://periodistasdeapie.org.mx/quienes-somos/", "https://periodistasdeapie.org.mx/category/areas-de-trabajo/alianza-de-medios/historia-de-la-alianza/", "https://periodistasdeapie.org.mx/wp-content/uploads/2024/12/Guia-Editorial-AMI.pdf", "https://biblioteca-repositorio.clacso.edu.ar/bitstream/CLACSO/253024/1/2023_978-607-571-912-2.pdf"]
  },
  {
    row: 240, slug: "despierta_quintana_roo", title: "Despierta Quintana Roo",
    updates: { state: "Quintana Roo", municipality: "Cancun", CVE_ENT: 23, "coverage.scope": "state / regional", address: "Av. Las Torres, Mz. 41, Lt. 1, Cancun, Quintana Roo (directory listing; verify)", "city.headq": 23, "owner.person": "Gonzalo Francisco Hermosillo Martinez (2018 contracting identity); Alfredo Alejandro Athie Perez (2021 representative)", owner_group: "Grupo Despierta Quintana Roo / Despierta TV", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "digital / television / video / social media" },
    assessment: "Quintana Roo multimedia outlet covering Cancun and the state. Public contracting and institutional records connect the commercial name to Gonzalo Francisco Hermosillo Martinez and later identify Alfredo Alejandro Athie Perez as a representative.",
    ideology: "Current content is largely local breaking news and government information. The available evidence does not support a durable partisan or 4T classification.",
    uncertainty: "High priority: reconcile the two public representatives, current ownership, legal entity, relationship to Despierta TV, launch date and address. The address comes from a map listing rather than an official legal notice.",
    sources: ["https://despiertaquintanaroo.mx/", "https://despierta.tv/", "https://documentos.transparencia.congresoqroo.gob.mx/91/XXIII/OM/2018/xv-legislatura-tercer-trimestre-2018/art91-F-XXIII-OM-xv-legislatura-tercer-trimestre-2018-2018-A91_FXXIIIB_CCS_GastosContratacionDeServicios_3erTrim2018.pdf", "https://www.itcancun.edu.mx/wp-content/uploads/2021/07/DIRECTORIO-CONVENIOS-DE-RESID.PROFESIONAL.pdf", "https://www.waze.com/es/live-map/directions/mx/q.r./cancun/despierta-quintana-roo-multimedios?to=place.ChIJr2iVY3srTI8RuQ_SlebcrMQ"]
  },
  {
    row: 241, slug: "debate_sinaloa", title: "Debate Sinaloa",
    updates: { state: "Sinaloa", municipality: "Culiacan", CVE_ENT: 25, "coverage.scope": "state / national digital", "city.headq": 25, legal_name: "Empresas El Debate, S.A. de C.V.", "owner.person": "Ildefonso Salido Ibarra; Luis Javier Salido Artola", "owner.family": "Familia Salido", owner_group: "Grupo El Debate", conglomerate: "Grupo El Debate", "founder.name": "Manuel Moreno Rivas", year_founded: "1941 Los Mochis; 1972 Culiacan edition", "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "medium", "type.media": "periodico / digital / video / social media" },
    assessment: "Sinaloa newspaper founded in Los Mochis in 1941 by Manuel Moreno Rivas, with a Culiacan edition since 1972. It was later acquired and directed by the Salido family.",
    ideology: "The outlet declares pluralism, but its recurring opinion content strongly attacks AMLO, Morena and the 4T and often amplifies opposition framing. Right/opp is therefore proposed with medium confidence rather than treating every news article as ideological.",
    uncertainty: "The current equity split within the Salido family, edition-specific address and distinction between Empresas El Debate and related corporate names require verification.",
    sources: ["https://www.debate.com.mx/site/nuestros-principios.html", "https://www.debate.com.mx/losmochis/EL-DEBATE-cumple-75-anos-de-contar-historias-20160310-0078.html", "https://www.debate.com.mx/sinaloa/losmochis/festejan-los-90-anos-de-don-ildefonso-salido-20260808-0020.html", "https://www.jornada.com.mx/2017/08/09/estados/030n2est", "https://www.debate.com.mx/opinion/Engano-mentira-y-farsa-en-el-debate-20240408-0228.html"]
  },
  {
    row: 242, slug: "elias_medina_en_las_redes", title: "Elias Medina en las Redes",
    updates: { state: "Baja California Sur", municipality: "La Paz", CVE_ENT: 3, "coverage.scope": "state / regional", "city.headq": 3, "owner.person": "Elias Medina P. (journalist/public representative)", owner_group: "Elias Medina en las Redes", "founder.name": "Elias Medina P. (to verify)", "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "personal digital / social media" },
    assessment: "Personal social-news operation of Baja California Sur journalist Elias Medina P., whose reporting is frequently credited by regional outlets and appears in official state media registries.",
    ideology: "Available material verifies reporting activity but does not establish a durable ideological or 4T position. Center/unclear is used with low confidence.",
    uncertainty: "High priority: no official website, legal entity, address, launch date or ownership record was found, and the exact social account should be matched to the archive record.",
    sources: ["https://ieebcs.org.mx/documentos/acuerdos/INFORME_ANUAL_ACTIVIDADES_JCS_2024.pdf?nocache=1744502400044", "https://www.bcsnoticias.mx/lopez-obrador-vuelve-a-baja-california-sur-este-viernes-visitara-a-la-paz-anuncia/", "https://oem.com.mx/elsudcaliforniano/local/analizaran-pescadores-ley-de-extincion-de-dominio-19738440"]
  },
  {
    row: 243, slug: "impacto_diario", title: "Impacto Diario",
    updates: { state: "Nacional", municipality: "Azcapotzalco", CVE_ENT: null, "coverage.scope": "national", address: "Av. Ceylan 517, Col. Industrial Vallejo, C.P. 02300, Azcapotzalco, Ciudad de Mexico", "city.headq": 9, legal_name: "Potros Editores, S.A. de C.V. (daily, historical); Publicaciones Llergo, S.A. de C.V. (current magazine notice)", "owner.person": "Juan Ramon Bustillos Toral (current director general); Juan Bustillos Orozco (historical owner)", "owner.family": "Familia Bustillos", owner_group: "Impacto", "founder.name": "Juan Bustillos; Miguel Angel Couchonnal", year_founded: 2005, "ideology.leftright": "right", "ideology.4t": "opp", "ideology.confidence": "high", "type.media": "print magazine / former daily newspaper / digital / social media" },
    assessment: "Impacto El Diario began circulation on 10 January 2005 under Juan Bustillos and Miguel Angel Couchonnal. Current Impacto publications retain the Ceylan address, but the operation now appears centered on a magazine and website.",
    ideology: "Current editorials and covers regularly describe the 4T in authoritarian, corrupt or propagandistic terms. Together with its historically establishment-oriented line, this supports right/opp with high confidence.",
    uncertainty: "High priority: determine whether the daily newspaper still circulates separately, reconcile Potros Editores with the current Publicaciones Llergo notice and verify present shareholders.",
    sources: ["https://sic.gob.mx/ficha.php?table=impresos&table_id=122", "https://impacto.mx/", "https://impacto.mx/wp-content/uploads/2026/06/IMPACTO-EDICION-3963.pdf", "https://expansion.mx/expansion/2011/09/14/extra-se-buscan-politicos", "https://www.imss.gob.mx/sites/all/statics/pdf/transparencia/focalizada/campa/2014-spots.pdf"]
  },
  {
    row: 244, slug: "ahora_tabasco", title: "Ahora Tabasco",
    updates: { state: "Tabasco", municipality: "Centro / Villahermosa", CVE_ENT: 27, "coverage.scope": "state / regional", address: "Av. Prof. Ramon Mendoza Herrera 236, Col. Jose Maria Pino Suarez, C.P. 86029, Villahermosa, Tabasco", "city.headq": 27, legal_name: "A Diario Tabasco, S. de R.L. de C.V.", "owner.person": "Alejandro Tovar Dominguez (director general in 2020)", owner_group: "Ahora Tabasco", year_founded: 2011, "ideology.leftright": "center", "ideology.4t": "unclear", "ideology.confidence": "low", "type.media": "periodico impreso / radio / digital / electronic screens / social media" },
    assessment: "Villahermosa multimedia outlet operating in print, digital platforms, electronic screens and radio. Its official page supplies the address, and state records identify A Diario Tabasco as the legal name.",
    ideology: "The outlet describes itself as plural and independent, and the available current content does not establish a stable left-right or 4T line.",
    uncertainty: "The current owner, shareholders, founder and exact start date require confirmation. The 2011 date is supported by its public account and directory history; the named director is from a 2020 issue.",
    sources: ["https://ahoratabasco.com/quienes-somos/", "https://ahoratabasco.com/", "https://publicacionperiodico.tabasco.gob.mx/documento/2065/firmado_qr.pdf", "https://www.calameo.com/books/006025572ed3d4c17f785", "https://x.com/AhoraTabasco/with_replies"]
  },
  {
    row: 245, slug: "radio_sonora", title: "Radio Sonora",
    updates: { state: "Sonora", municipality: "Hermosillo", CVE_ENT: 26, "coverage.scope": "state network", address: "Calle Gral. Alvaro Obregon 46, Col. Centro, C.P. 83000, Hermosillo, Sonora", "city.headq": 26, legal_name: "Radio Sonora, organismo publico descentralizado", owner_group: "Government of Sonora / Radio Sonora", conglomerate: "Sistema Estatal de Comunicacion Social del Estado de Sonora", "founder.name": "Government of Sonora; Abelardo Rodriguez; Monica Luna; Ricardo Ribeiro", year_founded: 1982, "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "public radio network / digital / social media" },
    assessment: "Public radio network of the Sonora state government. XHHB-FM began operations on 8 October 1982 and now feeds a statewide repeater network.",
    ideology: "Center avoids assigning a permanent partisan ideology to a public broadcaster. Aligned records its current institutional control by the Sonora government and public communication system under a Morena administration, not a claim about every program.",
    uncertainty: "The 4T label is structural and can change with state administrations. Current management, the distinction between the 1982 launch and 1985 OPD decree, and the legal status of each repeater should be checked.",
    sources: ["https://www.radiosonora.com.mx/historia-de-la-fundacion-de-radio-sonora/", "https://radio.sonora.gob.mx/acerca-de", "https://buengobierno.sonora.gob.mx/servicios-e-informacion/informacion-de-interes/compendio-legislativo-basico-estatal/reglamentos/671-reglamento-interior-de-radio-sonora/file.html", "https://www.sonora.gob.mx/gobierno/estructura-organizacional/item/sistema-estatal-de-comunicacion-social"]
  },
  {
    row: 246, slug: "telemax", title: "Telemax",
    updates: { state: "Sonora", municipality: "Hermosillo", CVE_ENT: 26, "coverage.scope": "state / regional", address: "Blvd. Luis Encinas y Dr. Domingo Olivares s/n, Col. Villa Satelite, Hermosillo, Sonora", "city.headq": 26, legal_name: "Televisora de Hermosillo, S.A. de C.V.", owner_group: "Government of Sonora / Telemax", conglomerate: "Sistema Estatal de Comunicacion Social del Estado de Sonora", year_founded: 1959, "ideology.leftright": "center", "ideology.4t": "aligned", "ideology.confidence": "medium", "type.media": "state television / digital / video / social media" },
    assessment: "Sonora state television company that began transmissions on 30 May 1959. Official transparency pages identify Televisora de Hermosillo, S.A. de C.V., its current director and Hermosillo address.",
    ideology: "Center avoids treating a state broadcaster as permanently left or right. Aligned reflects current ownership and coordination by the Sonora government under a Morena administration, not uniform support in every program.",
    uncertainty: "The alignment label is institutional and administration-dependent. The original founders, detailed state shareholding and exact division between commercial and public concessions require confirmation.",
    sources: ["https://telemax.com.mx/quienes-somos/", "https://telemax.com.mx/transparencia-sonora/", "https://telemax.com.mx/wp-content/uploads/2022/12/PROGRAMA-INSTITUCIONAL-TELEMAX.pdf", "https://telemax.com.mx/blog/2025/05/30/hoy-telemax-celebra-66-anos/", "https://www.sonora.gob.mx/gobierno/estructura-organizacional/item/sistema-estatal-de-comunicacion-social"]
  }
];

if (outlets.length !== 31) throw new Error(`Expected 31 outlets, got ${outlets.length}`);

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
  const sourceLines = outlet.sources.map((url, index) => `${index + 1}. ${url}`).join("\n");
  const md = `# ${outlet.title}\n\nResearch date: ${researchDate}\n\n## Proposed metadata\n\n| Field | Proposed value |\n|---|---|\n${mdRows}\n\n## Evidence summary\n\n${outlet.assessment}\n\n## Ideology rationale\n\n${outlet.ideology}\n\n## Verification note\n\n${outlet.uncertainty}\n\n## Sources\n\n${sourceLines}\n`;
  await fs.writeFile(path.join(notesDir, `${outlet.slug}.md`), md, "utf8");
}

sheet.getRange("AC1:AD246").format.wrapText = true;
sheet.getRange("AC1:AC246").format.columnWidth = 18;
sheet.getRange("AD1:AD246").format.columnWidth = 62;

const check = await workbook.inspect({ kind: "table", range: "Hoja1!A216:AD246", include: "values,formulas", tableMaxRows: 32, tableMaxCols: 30, tableMaxCellChars: 110 });
console.log(check.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 300 }, summary: "formula error scan after rows 216-246 update" });
console.log(errors.ndjson);

const after = await workbook.render({ sheetName: "Hoja1", range: "A216:AD246", scale: 1, format: "png" });
await fs.writeFile(`${outputDir}/rows_216_246_after.png`, new Uint8Array(await after.arrayBuffer()));
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const flagged = outlets.filter((outlet) => (outlet.verify ?? "yes") === "yes").length;
console.log(JSON.stringify({ outputPath, notes: outlets.length, flagged, notFlagged: outlets.length - flagged }, null, 2));
