# Sheinbaum counterpart to AMLO 01-build-and-estimate.R / 16-daily-six-outcomes-winsor99.R.
# Daily recorded attendees; identified speaking proxy; all recovered-video outcomes.
suppressPackageStartupMessages({library(arrow);library(dplyr);library(fixest)})
source('project_paths.R')
.libPaths(c('tmp/Rlibs/wildclusterboot',.libPaths()))
suppressPackageStartupMessages(library(fwildclusterboot))
setFixest_nthreads(1)
out<-media_path('results/sheinbaum/main_results/lottery-through-2025-06-15')
dir.create(out,recursive=TRUE,showWarnings=FALSE)
base_dir<-'output/balance/sheinbaum_12m'
paths<-file.path(base_dir,c('youtube_overlap_sample.parquet','youtube_outlet_daily.parquet','build_audit.json'))
manifest<-data.frame(path=normalizePath(paths),md5=unname(tools::md5sum(paths)))
save_csv<-function(x,name) write.csv(x,file.path(out,name),row.names=FALSE)
OUTCOMES<-c('videos','interactions','mean_interactions','likes','comments','views')
B<-9999L; SEED<-20261012L # Same weights / settings as the AMLO tables.
b<-read_parquet(paths[1]) |> mutate(date=as.Date(date)) |>
  transmute(unit_id,date,ask=as.integer(speaking_identified),records=recorded_attendance_n,
            prior_ratio=question_attendance_ratio)
y<-read_parquet(paths[2]) |> mutate(date=as.Date(date)) |>
  select(unit_id,date,videos,views,likes,comments,interactions,mean_interactions=interactions_per_video)
d0<-inner_join(b,y,by=c('unit_id','date'),relationship='one-to-one') |> arrange(unit_id,date)
stopifnot(nrow(d0)==nrow(b),!anyDuplicated(d0[c('unit_id','date')]),
  all(d0$date>=as.Date('2024-10-01') & d0$date<=as.Date('2025-06-15')),
  all(d0$records>0), all(d0$ask %in% 0:1),all(is.finite(as.matrix(d0[OUTCOMES]))),
  all(as.matrix(d0[OUTCOMES])>=0),all(d0$interactions==d0$likes+d0$comments))
# Exact fixest singleton pruning once, reused across outcomes/specifications.
probe<-feols(log1p(videos)~ask|unit_id+date,d0,cluster=~unit_id,notes=FALSE)
keep<-obs(probe);d<-as.data.frame(d0[keep,])
save_csv(d0[setdiff(seq_len(nrow(d0)),keep),], 'singleton_rows_removed.csv')
d$quarter<-paste0(format(d$date,'%Y'),'Q',(as.integer(format(d$date,'%m'))-1L)%/%3L+1L)
d$missing_ratio<-as.integer(!is.finite(d$prior_ratio))
d$ratio_filled<-ifelse(d$missing_ratio==1,0,d$prior_ratio)
quarters<-sort(unique(d$quarter));controls<-character()
for(q in quarters[-1]) {
  v<-paste0('history_',q);m<-paste0('missing_',q)
  d[[v]]<-d$ratio_filled*as.integer(d$quarter==q)
  d[[m]]<-d$missing_ratio*as.integer(d$quarter==q)
  controls<-c(controls,v,m)
}
# Shared pooled-sample upper-p99 caps, R type 7, before log1p; no lower cap.
cuts<-bind_rows(lapply(OUTCOMES,function(o) data.frame(outcome=o,upper=unname(quantile(d[[o]],.99,type=7)),
  capped_rows=sum(d[[o]]>quantile(d[[o]],.99,type=7)),n=nrow(d))))
save_csv(cuts,'winsorization_cutoffs.csv')
write_parquet(d,file.path(out,'analysis_panel.parquet'))
saveRDS(list(data=d,controls=controls,quarters=quarters,source_rows=keep),file.path(out,'analysis_panel.rds'))
summary<-data.frame(n=nrow(d),units=n_distinct(d$unit_id),dates=n_distinct(d$date),
  speaking_days=sum(d$ask),zero_video_days=sum(d$videos==0),
  zero_video_speaking_days=sum(d$videos==0 & d$ask==1),
  ever_speaking_outlets=n_distinct(d$unit_id[d$ask==1]),
  switching_outlets=sum(tapply(d$ask,d$unit_id,function(x)length(unique(x)))==2),
  missing_history_outlets=n_distinct(d$unit_id[d$missing_ratio==1]),
  date_from=as.character(min(d$date)),date_to=as.character(max(d$date)),
  singleton_rows_removed=nrow(d0)-nrow(d))
save_csv(summary,'sample_summary.csv')
# Factors also avoid fwildclusterboot's Date-class get_cluster incompatibility.
d$unit_id<-factor(d$unit_id);d$date<-factor(d$date)
fits<-results<-list();bootrows<-list()
for(variant in c('winsor99_log1p','raw_log1p')) for(o in OUTCOMES) for(adjusted in c(FALSE,TRUE)) {
  model<-if(adjusted)'History adjusted' else 'Baseline'
  d$Y<-log1p(if(variant=='winsor99_log1p')pmin(d[[o]],cuts$upper[cuts$outcome==o]) else d[[o]])
  fml<-as.formula(paste('Y ~',paste(c('ask',if(adjusted)controls),collapse=' + '),'| unit_id + date'))
  f<-feols(fml,data=d,cluster=~unit_id,notes=FALSE)
  stopifnot(nobs(f)==nrow(d),identical(obs(f),seq_len(nrow(d))),is.null(f$collin.var))
  key<-paste(variant,o,model,sep=':');fits[[key]]<-f
  ct<-coeftable(f)['ask',];ci<-confint(f,'ask')
  r<-data.frame(variant,outcome=o,model,estimate=unname(ct[1]),se=unname(ct[2]),ci_low=ci[1,1],ci_high=ci[1,2],p_value=unname(ct[4]),
    n=nobs(f),units=nlevels(d$unit_id),dates=nlevels(d$date),within_r2=unname(r2(f,'wr2')),wild_p=NA_real_)
  if(variant=='winsor99_log1p') {
    set.seed(SEED);dqrng::dqset.seed(SEED)
    message(o,' / ',model,': ',B,' outlet wild-bootstrap draws')
    bt<-boottest(f,param='ask',R=1,r=0,B=B,clustid='unit_id',bootcluster='unit_id',fe='unit_id',
      type='rademacher',impose_null=TRUE,bootstrap_type='fnw11',p_val_type='two-tailed',
      conf_int=FALSE,engine='R',nthreads=1,
      ssc=boot_ssc(adj=TRUE,cluster.adj=TRUE,fixef.K='none'))
    draws<-as.numeric(bt$t_boot)
    stopifnot(bt$N==nrow(d),unname(bt$N_G)==nlevels(d$unit_id),length(draws)==B,all(is.finite(draws)),
      abs(bt$point_estimate-r$estimate)<1e-8,
      abs(bt$p_val-mean(abs(draws)>=abs(as.numeric(bt$t_stat))))<1e-10)
    r$wild_p<-as.numeric(bt$p_val)
    saveRDS(list(test=bt,seed=SEED,B=B),file.path(out,paste0('wild_',o,'_',if(adjusted)'adjusted' else 'baseline','.rds')))
    bootrows[[key]]<-data.frame(outcome=o,model,wild_p=r$wild_p,B,seed=SEED,
      valid_draws=length(draws),mc_se=sqrt(r$wild_p*(1-r$wild_p)/B))
  }
  results[[key]]<-r
  save_csv(bind_rows(results),'regression_results.csv')
}
saveRDS(fits,file.path(out,'fits.rds'))
save_csv(bind_rows(bootrows),'wild_bootstrap_audit.csv')
stopifnot(identical(unname(tools::md5sum(paths)),manifest$md5))
save_csv(manifest,'input_manifest.csv')
writeLines(capture.output(sessionInfo()),file.path(out,'session_info.txt'))
print(summary,width=180)
print(as_tibble(bind_rows(results)) |> filter(variant=='winsor99_log1p') |> select(outcome,model,estimate,se,p_value,wild_p),n=24)
