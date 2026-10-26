suppressPackageStartupMessages({library(arrow);library(dplyr);library(fixest)})
source('project_paths.R')
out<-media_path('results/sheinbaum/main_results/lottery-through-2025-06-15')
x<-readRDS(file.path(out,'analysis_panel.rds'));d<-x$data
fits<-readRDS(file.path(out,'fits.rds'));r<-read.csv(file.path(out,'regression_results.csv'))
cuts<-read.csv(file.path(out,'winsorization_cutoffs.csv'))
manifest<-read.csv(file.path(out,'input_manifest.csv'))
stopifnot(identical(unname(tools::md5sum(manifest$path)),manifest$md5),length(fits)==24,nrow(r)==24)
b<-read_parquet('output/balance/sheinbaum_12m/youtube_overlap_sample.parquet') |> mutate(date=as.Date(date))
# Independent iterative singleton removal; no filter on outcome/publication.
repeat {
  old_n<-nrow(b)
  b<-b |> group_by(unit_id) |> filter(n()>1) |> ungroup() |> group_by(date) |> filter(n()>1) |> ungroup()
  if(nrow(b)==old_n) break
}
b<-b |> arrange(unit_id,date)
stopifnot(identical(as.character(b$unit_id),d$unit_id),identical(b$date,d$date),
  all(d$ask==b$speaking_identified),all(d$records>0),
  all(d$date>=as.Date('2024-10-01') & d$date<=as.Date('2025-06-15')),
  all(d$interactions==d$likes+d$comments),sum(d$videos==0)==1387)
y<-read_parquet('output/balance/sheinbaum_12m/youtube_outlet_daily.parquet') |> mutate(date=as.Date(date))
fresh<-d |> select(unit_id,date) |> left_join(y,by=c('unit_id','date'),relationship='one-to-one')
for(o in c('videos','views','likes','comments','interactions')) stopifnot(all(d[[o]]==fresh[[o]]))
stopifnot(all(d$mean_interactions==ifelse(d$videos>0,d$interactions/pmax(d$videos,1),0)))
for(i in seq_len(nrow(r))) {
  row<-r[i,];f<-fits[[paste(row$variant,row$outcome,row$model,sep=':')]]
  raw<-d[[row$outcome]];cap<-cuts$upper[cuts$outcome==row$outcome]
  stopifnot(abs(cap-unname(quantile(raw,.99,type=7)))<1e-8)
  Y<-log1p(if(row$variant=='winsor99_log1p')pmin(raw,cap) else raw)
  vars<-c('ask',if(row$model=='History adjusted')x$controls)
  within<-demean(cbind(Y,as.matrix(d[vars])),f=list(d$unit_id,d$date),tol=1e-10)
  beta<-qr.solve(within[,-1,drop=FALSE],within[,1])
  stopifnot(max(abs(beta-coef(f)))<1e-7,abs(beta[['ask']]-row$estimate)<1e-7,
    nobs(f)==nrow(d),is.null(f$collin.var),abs(se(f)[['ask']]-row$se)<1e-10)
  ci<-confint(f,'ask')
  stopifnot(abs(ci[1,1]-row$ci_low)<1e-10,abs(ci[1,2]-row$ci_high)<1e-10)
  if(row$variant=='winsor99_log1p') {
    tag<-if(row$model=='History adjusted')'adjusted' else 'baseline'
    bt<-readRDS(file.path(out,paste0('wild_',row$outcome,'_',tag,'.rds')))$test
    stopifnot(length(bt$t_boot)==9999,all(is.finite(bt$t_boot)),isTRUE(bt$impose_null),bt$r==0,
      bt$N==nrow(d),unname(bt$N_G)==n_distinct(d$unit_id),
      abs(bt$point_estimate-row$estimate)<1e-8,
      abs(mean(abs(bt$t_boot)>=abs(bt$t_stat))-row$wild_p)<1e-10)
  }
}
cat('PASS: 24 independent within-FE coefficients, source totals, original zero-fill/cap rules, shared sample and 12 validated 9,999-draw wild tests.\n')
