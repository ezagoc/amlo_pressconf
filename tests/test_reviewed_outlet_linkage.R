suppressPackageStartupMessages(library(dplyr))
source("src/reviewed_outlet_linkage.R")
a <- read_outlet_aliases("info_newspapers_gpt/attendance_aliases_20261016.tsv")
input <- data.frame(medios=c("ENFOQUE OPORTUNO", "Enfoque Noticias", "INTERMEDIA CANAL 44",
  "CANAL 44 DE LA UDG", "CANAL 44", "ABC AUSTRALIA", "ABC RADIO", "PUENTE LIBRE MX",
  "MAXIMA FM/CUARTO PODER", "CÓDICE 21", "CODIGO ROJO QUINTANA ROO", NA),
  outlet_final=c("enfoque noticias", "enfoque noticias", "canal 44", "canal 44", "canal 44",
    "abc", "abc", "movimiento consciencia", "cuarto poder", "codice 21", "codigo rojo", NA),
  stringsAsFactors=FALSE)
x <- apply_reviewed_attendance_linkage(input,a)
stopifnot(nrow(x)==nrow(input),identical(x$medios,input$medios),
  identical(x$outlet_final,c("enfoque oportuno","enfoque noticias","grupo intermedia",
    "universidad de guadalajara",NA,"abc australia","audiorama","tiempo la noticia digital",NA,"codice 21","codigo rojo",NA)),
  identical(apply_reviewed_attendance_linkage(x,a),x),
  nrow(apply_reviewed_attendance_linkage(input[FALSE,],a))==0L)
bad <- rbind(a,a[1,]);tmp <- tempfile(fileext=".tsv")
write.table(bad,tmp,sep="\t",row.names=FALSE,quote=FALSE,na="")
stopifnot(inherits(try(read_outlet_aliases(tmp),silent=TRUE),"try-error"));unlink(tmp)
q <- read_outlet_aliases("info_newspapers_gpt/question_aliases_20261016.tsv")
stopifnot(identical(apply_reviewed_question_linkage(
  c("codigo rojo", "codigo libre", "enfoque oportuno", "canal 44", "once noticias", NA),
  c("codigo libre", "codigo libre", "enfoque noticias", "canal 44", "canal 11", NA), q),
  c("codigo rojo","codigo libre","enfoque oportuno","canal 44","canal 11",NA)))
followup <- data.frame(medios=c("DIARIO RED", "POSTDATA.NEWS", "MÁXIMA 969",
  "MÁXIMA 979 Y MÁXIMA 969", "MÁXIMA TLAXIACO", "DIARIO.RED, PIEDEPAGINA.MX",
  "ENLACE MEXAAMERICA", "TRIBU POLÍTICA", "POLITICO.MX"),
  outlet_final=rep("legacy",9), stringsAsFactors=FALSE)
stopifnot(identical(apply_reviewed_attendance_linkage(followup,a)$outlet_final,
  c("diario red latinoamerica", "agua quemada", "maxima fm", "maxima fm",
    NA,NA,NA,NA,"legacy")))
stopifnot(identical(apply_reviewed_question_linkage(
  c("The Humane", "The Humanoid", "Red de Periodistas de Puerto Vallarta",
    "Postdata.news", "Revista El Político", "Sin Línea"),rep("legacy",6),q),
  c("the human hoy", "the human hoy", "universidad de guadalajara",
    "agua quemada", "sin linea", "sin linea")))
new_labels <- c("Ahora Noticias", "Ahora Tabasco Noticias", "Es Ahora AM",
  "ACIDEHIDALGO", "ACI México", "ACI NOTICIAS", "ACIR",
  "ACI Hidalgo, ACI México y Pulso Sur")
new_attendance <- data.frame(medios=new_labels, outlet_final=rep("legacy",8))
stopifnot(identical(apply_reviewed_attendance_linkage(new_attendance,a)$outlet_final,
  c("ahora tabasco","ahora tabasco","jaime farias informa","aci de hidalgo",
    "aci de hidalgo",NA,"legacy","legacy")))
stopifnot(identical(apply_reviewed_question_linkage(
  c("Ahora Noticias","Es Ahora AM","ACI de Hidalgo y ACI México",
    "ACI Noticias","ACI de Hidalgo y ACI México y Pulso Sur"),
  c("es ahora am","es ahora am","legacy","legacy","legacy"),q),
  c("ahora tabasco","jaime farias informa","aci de hidalgo","legacy","legacy")))
cat("Reviewed outlet linkage tests passed.\n")

# The approved Olvera grouping must not swallow the unrelated Mexico News brands.
olvera_labels <- c("Hidalgo News", "México News World", "Marco Olvera Oficial",
                   "Mexico Network", "The Mexico News", "Mexico News Daily",
                   "Hidalgo Noticias", "Bajo Palabra", "Énfasis")
legacy <- c(rep("legacy", 4), "mexico news", "mexico news daily",
            "hidalgo noticias", "bajo palabra", "enfasis")
expected <- c(rep("mexico news world", 4), legacy[5:9])
stopifnot(identical(apply_reviewed_question_linkage(olvera_labels, legacy, q), expected))
attendance <- data.frame(medios=olvera_labels, outlet_final=legacy)
mapped <- apply_reviewed_attendance_linkage(attendance, a)
stopifnot(identical(mapped$outlet_final, expected), identical(mapped$medios, olvera_labels))

# Alias rows must disappear as analysis units without renumbering later outlets.
source("src/metadata_helpers.R")
meta <- tibble(name.page=c("Mexico News World", "Hidalgo News", "Other"),
               analysis_merged_into=c(NA, "mexico news world", NA))
news <- tibble(name.page=meta$name.page, names.conference=c("mexico news world", NA, "other"),
               names.transcripts=c("mexico news world", NA, "other"))
merged <- apply_reviewed_conference_keys(merge_newspaper_metadata(meta, news))
stopifnot(identical(merged$metadata_id, c(1L, 3L)), nrow(merged)==2L)
cat("Olvera alias, exclusion and stable metadata-ID checks passed.\n")

# User-approved Sin Linea / El Politico grouping, without broad politico matches.
labels <- c("SIN LÍNEA.MX", "SIN LINEA MX", "El Político en las Redes",
            "Revista El Político", "revistaelpolitico.com", "POLITICO.MX",
            "Animal Político", "El Charro Político", "Galeazzi News")
expected <- c(rep("sin linea",5),rep("legacy",2),"nopal times","legacy")
stopifnot(identical(apply_reviewed_question_linkage(labels,rep("legacy",9),q),expected))
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=rep("legacy",9)),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels))
meta <- tibble(name.page=c("Sin Linea MX","El Politico en las Redes","Other"),
               analysis_merged_into=c(NA,"sin linea",NA))
news <- tibble(name.page=meta$name.page,names.conference=c("SIN LINEA MX",NA,"other"),
               names.transcripts=c("sin linea",NA,"other"))
merged <- apply_reviewed_conference_keys(merge_newspaper_metadata(meta,news))
stopifnot(identical(merged$metadata_id,c(1L,3L)),
          identical(merged$names.conference,c("sin linea","other")))
cat("Sin Linea alias, exclusion and stable metadata-ID checks passed.\n")

# Tiempo / Puente Libre retain brand metadata and share only conference IDs.
labels <- c("Puente Libre MX","PuenteLibre.mx","TIEMPO.COM.MX Y PUENTELIBRE.M",
            "Tiempo La Noticia Digital","A TIEMPO.TV","Proyecto Puente","Movimiento Consciencia")
expected <- c(rep("tiempo la noticia digital",4),rep("legacy",2),"movimiento conciencia")
stopifnot(identical(apply_reviewed_question_linkage(labels,rep("legacy",7),q),expected))
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=rep("legacy",7)),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels),nrow(x)==7L)
meta <- tibble(name.page=c("Tiempo La Noticia Digital","PuenteLibreMX","Other"),
               analysis_merged_into=NA_character_,youtube.channel=c("tiempotv","puentelibre-channel","other"))
news <- tibble(name.page=meta$name.page,names.conference=c("TIEMPO LA NOTICIA DIGITAL","puente libre","other"),
               names.transcripts=c("tiempo la noticia digital","puente libre mx","other"))
merged <- apply_reviewed_conference_keys(merge_newspaper_metadata(meta,news))
stopifnot(identical(merged$metadata_id,1:3),identical(merged$name.page,meta$name.page),
          identical(merged$youtube.channel,meta$youtube.channel),
          identical(merged$names.conference,c(rep("tiempo la noticia digital",2),"other")),
          identical(merged$names.transcripts,c(rep("tiempo la noticia digital",2),"other")))
cat("Tiempo/Puente Libre shared conference IDs and separate brands verified.\n")

labels <- c("Teleurban","Tele Urban","Grupo TeleUrban","RADIOPOLIS","W Radio",
            "Los 40","W Deportes","Reportero Urbano","Radio Educacion")
expected <- c(rep("w radio",5),rep("legacy",4))
stopifnot(identical(apply_reviewed_question_linkage(labels,rep("legacy",9),q),expected))
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=rep("legacy",9)),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels),nrow(x)==9L)
cat("Teleurban/W Radio exact conference grouping and exclusions verified.\n")

# Keep the three brand metadata rows while joining their conference records.
labels <- c("FrecuenciaCAD.com","Es Ahora AM","JF INFORMA",
            "JF INFORMA DESDE CANCÚN Y ESAHORAAM DE QUERÉTARO", "ES AHORA AM NOTICIAS",
            "10 AM MX","Frecuencia 420","Frecuencia F Noticias","Ahora Noticias")
expected <- c(rep("jaime farias informa",5),rep("legacy",3),"ahora tabasco")
stopifnot(identical(apply_reviewed_question_linkage(labels,rep("legacy",9),q),expected))
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=rep("legacy",9)),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels),nrow(x)==9L)
meta <- tibble(name.page=c("Jaime Farias Informa","Es Ahora AM","Frecuencia CAD","Other"),
               analysis_merged_into=NA_character_,youtube.channel=c("jf","ahora","cad","other"))
news <- tibble(name.page=meta$name.page,names.conference=meta$name.page,names.transcripts=meta$name.page)
merged <- apply_reviewed_conference_keys(merge_newspaper_metadata(meta,news))
stopifnot(identical(merged$metadata_id,1:4),identical(merged$name.page,meta$name.page),
          identical(merged$youtube.channel,meta$youtube.channel),
          identical(merged$names.conference,c(rep("jaime farias informa",3),"Other")),
          identical(merged$names.transcripts,c(rep("jaime farias informa",3),"Other")))
cat("JF/Frecuencia/Es Ahora shared conference IDs, separate brands and exclusions verified.\n")
stopifnot(all(apply_reviewed_question_linkage(
  c("frecuenciacadcom","frecuencia cadcom","esahoraamcom","es ahora amcom"),rep("legacy",4),q)=="jaime farias informa"))

# Empuje Migrante / Oro Solido: shared reporter representation, distinct brands.
labels <- c("Empuje Migrante","ORO SÓLIDO","ORO SOLIDO",
            "Amigo Migrante","Mitote Migrante","Conexion Migrante","TV Migrante")
expected <- c(rep("oro solido",3),rep("legacy",4))
stopifnot(identical(apply_reviewed_question_linkage(labels,rep("legacy",7),q),expected))
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=rep("legacy",7)),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels),nrow(x)==7L)
meta <- tibble(name.page=c("Oro Solido","Empuje Migrante","Other"),
               analysis_merged_into=NA_character_,youtube.channel=c("oro",NA,"other"))
news <- tibble(name.page=meta$name.page,names.conference=c("ORO SOLIDO",NA,"other"),
               names.transcripts=c("oro solido","empuje migrante","other"))
merged <- apply_reviewed_conference_keys(merge_newspaper_metadata(meta,news))
stopifnot(identical(merged$metadata_id,1:3),identical(merged$name.page,meta$name.page),
          identical(merged$youtube.channel,meta$youtube.channel),
          identical(merged$names.conference,c("oro solido","oro solido","other")),
          identical(merged$names.transcripts,c("oro solido","oro solido","other")))
cat("Oro Solido/Empuje Migrante shared conference keys and separate brands verified.\n")

# New groups are exact identities, not generic words or similar outlet names.
labels <- c("Bloomberg News","Bloomberg Linea","Bloomberg","El Financiero Bloomberg Television",
            "El Charro Politico","Politico.mx","CANAL 44","CANAL 44 DE LA UDG",
            "El Regreso de Donald Trump","TV Migrante","SandraAguilera.com")
expected <- c("el financiero","el financiero","bloomberg","el financiero",
              "nopal times","legacy",NA,"universidad de guadalajara",
              "alcanzando el conocimiento","legacy","legacy")
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final="legacy"),a)
stopifnot(identical(x$outlet_final,expected),identical(x$medios,labels))
meta <- tibble(name.page=c("AMARC (Red de radios comunitarias de México)",
  "Politica y Rock and Roll Radio ","El Financiero","Bloomberg News","Bloomberg Línea"),
  names.conference="original",names.transcripts="original",youtube.channel=letters[1:5])
merged <- apply_reviewed_conference_keys(meta)
stopifnot(identical(merged$name.page,meta$name.page),identical(merged$youtube.channel,meta$youtube.channel),
 identical(merged$names.conference,c("amarc","amarc","el financiero","el financiero","el financiero")))
cat("Flagged review exact groups, exclusions and preserved brand metadata verified.\n")

# ABC Radio is included by explicit user decision; unrelated ABC outlets are not.
labels <- c("Así lo dice La Mont","ABC RADIO 760 AM","ABC RADIO XEABC-AM 760 KHZ",
 "GRUPO AUDIORAMA COMUNICACIONES","ABC DE MONTERREY","ABC AUSTRALIA","ABC NEWS",
 "PORTAL DIARIO ABC PUEBLA","ABC RADIO SLP")
legacy <- c(rep("legacy",4),"abc","abc australia","unknown","abc","abc")
x <- apply_reviewed_attendance_linkage(data.frame(medios=labels,outlet_final=legacy),a)
stopifnot(identical(x$outlet_final,c(rep("audiorama",4),"abc","abc australia",NA,"abc","abc")),
 identical(x$medios,labels),nrow(x)==length(labels))
meta <- tibble(name.page=c("Asi lo dice La Mont","ABC Radio","Grupo Audiorama","ABC","ABC Australia"),
 names.conference=c("lamont","abc radio","audiorama","abc","abc australia"),
 names.transcripts=c("lamont","abc radio","audiorama","abc","abc australia"),
 youtube.channel=letters[1:5])
mapped <- apply_reviewed_conference_keys(meta)
stopifnot(identical(mapped$names.conference,c(rep("audiorama",3),"abc","abc australia")),
 identical(mapped$name.page,meta$name.page),identical(mapped$youtube.channel,meta$youtube.channel))
cat("La Mont/ABC Radio/Audiorama grouping and unrelated ABC exclusions verified.\n")
