# Compare questioned outlet identities with the full roster on each source date.
# This is an evidence audit, not an automatic alias or attendance-row expansion.
suppressPackageStartupMessages({library(arrow);library(readxl);library(dplyr);library(jsonlite)})
source('project_paths.R')
source('src/reviewed_outlet_linkage.R')
source('src/attendance_roles.R')
out <- 'info_newspapers_gpt/outlet_review_20261016/sheinbaum_date_matches'
dir.create(out,recursive=TRUE,showWarnings=FALSE)
a <- read_excel(media_path('data','02-conferences','raw','attendance','merged','attendance_merged_dedup.xlsx'))
a$attendance_row <- seq_len(nrow(a)) + 1L
a$event_date <- as.character(as.Date(a$fecha,tz='UTC'))
a$eligible_role <- keep_attendance_role(a$cargo)
a$attendance_key <- normalize_reviewed_label(a$medios)
q <- read_parquet(media_path('data','02-conferences-sheinbaum','api_extraction','official-full','auxiliar','journalist_media_evidence.parquet'))
t <- read_parquet(media_path('data','02-conferences-sheinbaum','official_source','through-2026-10-15','auxiliar','transcript_rows.parquet'))
source_date <- function(path) {
 d <- substr(basename(path),1,10)
 stopifnot(all(grepl('^\\d{4}-\\d{2}-\\d{2}$',d)),!anyNA(as.Date(d)))
 d
}
q$event_date <- source_date(q$source_path)
t$event_date <- source_date(t$source_path)
base <- read_parquet(media_path('data','02-conferences-sheinbaum','official_source','full','auxiliar','transcript_rows.parquet'))
base$event_date <- source_date(base$source_path)
t <- bind_rows(base,t[!t$event_date %in% base$event_date,])
# Parquet timestamps represent UTC midnight but display the preceding local day.
stopifnot(all(q$event_date==as.character(as.Date(q$date,tz='UTC'))),
          all(t$event_date==as.character(as.Date(t$date,tz='UTC'))))
transcript_max_available <- max(t$event_date)
# Later transcripts cannot be compared to attendance that stops in September 2025.
t <- t[t$event_date<=max(a$event_date),]
# Respect the existing user-maintained Sheinbaum rules, but label rule-derived
# identities separately from literal outlet self-identifications.
manual <- new.env(parent=globalenv())
invisible(capture.output(sys.source('code/03-cleaning_conf/question_class/sheinbaum/05_deduplicate_outlets_periodistas.R',envir=manual)))
stopifnot(identical(manual$WRITE_OUTPUT,FALSE))
key <- function(date,row,outlet,reporter)paste(date,row,coalesce(outlet,''),coalesce(reporter,''),sep='|')
mapped <- manual$df
mk <- key(as.character(mapped$date),mapped$source_row,mapped$outlet_aux_before,mapped$reporter_aux_before)
qk <- key(q$event_date,q$source_row,q$outlet_aux,q$reporter_aux)
q$harmonized_label <- mapped$outlet_aux[match(qk,mk)]
patterns <- c(
 'diario red latinoamerica'='diario[ .]+red',
 'la pancarta de quintana roo'='la pancarta',
 'el politico en las redes'='el politico en las redes|revista el politico',
 'ecosfera'='ecosfera|ecoosfera',
 'maxima fm'='maxima fm|^maxima[ .]|^maxima$',
 'animales con derechos'='animales con derechos',
 'the human hoy'='the ?human|human hoy',
 'tiempo y espacio'='tiempo y espacio|espacio y tiempo',
 'asi lo dice la mont'='asi lo dice la mont',
 'enlace mesoamerica'='enlace mesoamerica|enlace mexamerica|enlace mexaamerica',
 'grupo tribu'='grupo (la )?tribu|tribu politica',
 'revista posdata'='postdata|posdata',
 'empuje migrante'='empuje migrante',
 'rotativo de queretaro'='rotativo de queretaro|diario rotativo',
 'red periodistica de puerto vallarta'='red periodistica|red de periodistas de puerto vallarta')
candidate_patterns <- c(
 'diario red latinoamerica'='diario red|pie ?de ?pagina|luces del siglo',
 'la pancarta de quintana roo'='pancarta|saber',
 'el politico en las redes'='sin ?linea|politico',
 'ecosfera'='ecos|ecoo|cultura colectiva', 'maxima fm'='maxima|cuarto poder',
 'animales con derechos'='movimiento|conciencia|consciencia|sendero|iztaccihuatl',
 'the human hoy'='human|centinela', 'tiempo y espacio'='tiempo|espacio|canal 10',
 'asi lo dice la mont'='mont|sol de mexico|organizacion editorial|abc radio|audiorama',
 'enlace mesoamerica'='enlace|plaza juarez', 'grupo tribu'='tribu|cultura colectiva',
 'revista posdata'='posdata|postdata|agua|tubo|noreste',
 'empuje migrante'='migrante|oro solido',
 'rotativo de queretaro'='rotativo|meganoticias',
 'red periodistica de puerto vallarta'='vallarta|universidad|canal 44')
events <- list()
question_label_key <- normalize_reviewed_label(q$outlet_aux)
transcript_text_key <- normalize_reviewed_label(t$text)
for (id in names(patterns)) {
 literal <- grepl(patterns[[id]],question_label_key)
 selected <- literal | q$harmonized_label %in% id
 qi <- q[selected,]
 qi$selection_basis <- ifelse(literal[selected],'literal_outlet_label','existing_harmonization_rule')
 ti <- t[t$is_question_speaker %in% TRUE & grepl(patterns[[id]],transcript_text_key),]
 for(i in seq_len(nrow(ti))) {
  x <- ti[i,]
  # API evidence may quote several source rows. Do not create a second event
  # for a literal line already covered by that same introduction.
  covered <- qi$event_date==x$event_date & vapply(qi$source_rows,function(s) x$source_row %in% as.integer(strsplit(gsub('[^0-9]+',' ',coalesce(s,'')),' +')[[1]]),logical(1))
  if(any(covered) || any(qi$event_date==x$event_date & qi$evidence_text==x$text))next
  qi <- bind_rows(qi,tibble(event_date=x$event_date,source_path=x$source_path,
      source_row=x$source_row,reporter_aux=NA_character_,outlet_aux=id,
      evidence_text=x$text,source_url=x$source_url,selection_basis='literal_question_speaker_text',extraction_method='literal_question_speaker_text'))
 }
 if(!nrow(qi))next
 qi <- qi |> distinct(event_date,source_path,source_row,evidence_text,.keep_all=TRUE)
 for(i in seq_len(nrow(qi))) {
  x<-qi[i,]
  same_intro<-q[q$event_date==x$event_date & q$evidence_text==x$evidence_text,]
  reporter<-unique(na.omit(same_intro$reporter_aux))
  # Context allows review of fragmentary introductions; no inferred reporter fill.
  context<-t[t$event_date==x$event_date & abs(t$source_row-x$source_row)<=4,]
  events[[length(events)+1L]]<-tibble(outlet_id=id,event_date=x$event_date,
    source_row=x$source_row,reporter=if(length(reporter))paste(reporter,collapse=' | ') else NA_character_,
    question_outlet_label=x$outlet_aux,
    other_stated_outlets=paste(setdiff(unique(same_intro$outlet_aux),x$outlet_aux),collapse=' | '),
    selection_basis=x$selection_basis,harmonized_label=x$harmonized_label,
    evidence_text=x$evidence_text,context=paste(context$text,collapse='\n'),source_path=x$source_path,source_url=x$source_url)
 }
}
e<-bind_rows(events) |> arrange(outlet_id,event_date,source_row)
e$event_id<-sprintf('shein-outlet-%03d',seq_len(nrow(e)))
rosters<-e |> select(event_id,outlet_id,event_date) |>
 left_join(a |> select(event_date,attendance_row,medios,cargo,eligible_role,sede,source_file,attendance_key),by='event_date',relationship='many-to-many')
rosters$candidate_name <- mapply(function(id,label) !is.na(label) && grepl(candidate_patterns[[id]],label),rosters$outlet_id,rosters$attendance_key)
e$attendance_rows_on_date<-vapply(e$event_date,function(d)sum(a$event_date==d),integer(1))
e$eligible_rows_on_date<-vapply(e$event_date,function(d)sum(a$event_date==d & a$eligible_role),integer(1))
e$roster_candidates<-vapply(e$event_id,function(id)paste(unique(rosters$medios[rosters$event_id==id & rosters$candidate_name]),collapse=' | '),character(1))
counts<-e |> group_by(outlet_id) |> summarise(question_dates=n_distinct(event_date),question_evidence_rows=n(),first_date=min(event_date),last_date=max(event_date),.groups='drop')
coverage<-tibble(outlet_id=names(patterns)) |> left_join(counts,by='outlet_id')
coverage$question_dates[is.na(coverage$question_dates)]<-0L
coverage$question_evidence_rows[is.na(coverage$question_evidence_rows)]<-0L
write.csv(e,file.path(out,'question_date_evidence.csv'),row.names=FALSE,na='')
write.csv(rosters,file.path(out,'full_same_day_attendance.csv'),row.names=FALSE,na='')
write.csv(filter(rosters,candidate_name),file.path(out,'candidate_attendance_rows.csv'),row.names=FALSE,na='')
write.csv(coverage,file.path(out,'coverage.csv'),row.names=FALSE,na='')
write_json(list(question_min=min(t$event_date),question_max=max(t$event_date),transcript_max_available=transcript_max_available,
 question_dates=length(unique(t$event_date)),question_evidence_rows=nrow(e),
 matched_question_dates=length(unique(e$event_date)),
 attendance_min=min(a$event_date),attendance_max=max(a$event_date),
 attendance_has_reporter_names=FALSE,date_join='source filename date, checked against UTC date',
 note='Candidate name patterns select review rows only. Same-day presence is not proof of alias identity.'),
 file.path(out,'audit_inputs.json'),auto_unbox=TRUE,pretty=TRUE)
for(i in seq_len(nrow(e)))cat(e$event_id[i],e$outlet_id[i],e$event_date[i],
 '| reporter:',ifelse(is.na(e$reporter[i]),'not stated',e$reporter[i]),
 '| roster:',e$roster_candidates[i],'\n')
print(coverage,n=15)
