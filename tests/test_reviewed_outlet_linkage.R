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
    "canal 44 udg",NA,"abc australia","abc","puente libre",NA,"codice 21","codigo rojo",NA)),
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
  c("diario red latinoamerica", "revista posdata", "maxima fm", "maxima fm",
    NA,NA,NA,NA,"legacy")))
stopifnot(identical(apply_reviewed_question_linkage(
  c("The Humane", "The Humanoid", "Red de Periodistas de Puerto Vallarta",
    "Postdata.news", "Revista El Político", "Sin Línea"),rep("legacy",6),q),
  c("the human hoy", "the human hoy", "red periodistica de puerto vallarta",
    "revista posdata", "el politico en las redes", "legacy")))
cat("Reviewed outlet linkage tests passed.\n")
