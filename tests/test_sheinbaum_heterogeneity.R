suppressPackageStartupMessages({library(arrow);library(dplyr);library(fixest)})
source('project_paths.R')
parent<-media_path('results/sheinbaum/main_results/lottery-through-2025-06-15')
out<-file.path(parent,'pooled_interactions_combined')
x<-readRDS(file.path(out,'analysis_panel.rds'));d<-x$data
fits<-readRDS(file.path(out,'fits.rds'));r<-read.csv(file.path(out,'results.csv'))
manifest<-read.csv(file.path(out,'input_manifest.csv'));cuts<-read.csv(file.path(parent,'winsorization_cutoffs.csv'))
stopifnot(identical(unname(tools::md5sum(manifest$path)),manifest$md5),length(fits)==12,nrow(r)==36)
original<-readRDS(file.path(parent,'analysis_panel.rds'))$data
links<-read.csv('output/balance/sheinbaum_12m/metadata_links.csv')
meta<-read_parquet(media_path('data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet'))
classes<-links |> left_join(select(meta,metadata_id,ideology.4t),by='metadata_id',relationship='many-to-one') |>
  group_by(unit_id) |> summarise(code=paste(sort(unique(na.omit(ideology.4t))),collapse=' | '),.groups='drop')
expected<-original |> inner_join(filter(classes,code %in% c('opp','unclear','aligned')),by='unit_id') |>
  group_by(date) |> filter(any(ask==1),any(ask==0)) |> ungroup() |> arrange(unit_id,date)
repeat {
  n<-nrow(expected)
  expected<-expected |> group_by(unit_id) |> filter(n()>1) |> ungroup() |> group_by(date) |> filter(n()>1) |> ungroup()
  if(nrow(expected)==n)break
}
expected<-expected |> arrange(unit_id,date)
stopifnot(identical(as.character(expected$unit_id),d$unit_id),identical(expected$date,d$date),
  all(d$ask==expected$ask),all(d$ask_aligned==d$ask*(expected$code=='aligned')),
  identical(x$controls,readRDS(file.path(parent,'analysis_panel.rds'))$controls),
  sum(d$videos==0)==1230,all(d$records>0))
for(o in c('videos','interactions','mean_interactions','likes','comments','views')) stopifnot(all(d[[o]]==expected[[o]]))
for(key in names(fits)) {
  f<-fits[[key]];parts<-strsplit(key,':',fixed=TRUE)[[1]];o<-parts[1];model<-parts[2]
  Y<-log1p(pmin(d[[o]],cuts$upper[cuts$outcome==o]))
  vars<-c('ask','ask_aligned',if(model=='History adjusted')x$controls)
  within<-demean(cbind(Y,as.matrix(d[vars])),f=list(d$unit_id,d$date),tol=1e-10)
  beta<-qr.solve(within[,-1,drop=FALSE],within[,1])
  stopifnot(nobs(f)==nrow(d),max(abs(beta-coef(f)))<1e-7,is.null(f$collin.var))
  rr<-filter(r,outcome==o,.data$model==.env$model)
  for(i in seq_len(nrow(rr))) {
    row<-rr[i,];w<-switch(row$label,'Opp. + Independent'=c(1,0),'Aligned'=c(1,1),'Aligned - (Opp. + Independent)'=c(0,1))
    b<-coef(f)[c('ask','ask_aligned')];V<-vcov(f)[c('ask','ask_aligned'),c('ask','ask_aligned')]
    est<-sum(w*b);s<-sqrt(drop(w%*%V%*%w));df<-degrees_freedom(f,'t')
    stopifnot(abs(row$estimate-est)<1e-8,abs(row$se-s)<1e-8,
      abs(row$p_value-2*pt(-abs(est/s),df))<1e-10,
      abs(row$ci_low-(est-qt(.975,df)*s))<1e-8,abs(row$ci_high-(est+qt(.975,df)*s))<1e-8)
    h<-switch(row$label,'Opp. + Independent'='combined','Aligned'='aligned','Aligned - (Opp. + Independent)'='difference')
    tag<-paste(o,if(model=='History adjusted')'adjusted' else 'baseline',h,sep='_')
    bt<-readRDS(file.path(out,paste0('wild_',tag,'.rds')))$test
    stopifnot(length(bt$t_boot)==9999,all(is.finite(bt$t_boot)),isTRUE(bt$impose_null),bt$r==0,
      bt$N==nrow(d),unname(bt$N_G)==n_distinct(d$unit_id),abs(bt$point_estimate-row$estimate)<1e-8,
      abs(mean(abs(bt$t_boot)>=abs(bt$t_stat))-row$wild_p)<1e-10)
  }
}
cat('PASS: classifications, identical zero-inclusive sample, 12 independent within-FE fits, 36 contrasts/CIs and 359,964 bootstrap draws.\n')
