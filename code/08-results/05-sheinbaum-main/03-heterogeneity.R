# AMLO pooled asking-by-alignment specification, applied to Sheinbaum speaking proxy.
suppressPackageStartupMessages({library(arrow);library(dplyr);library(fixest)})
source('project_paths.R');.libPaths(c('tmp/Rlibs/wildclusterboot',.libPaths()))
suppressPackageStartupMessages(library(fwildclusterboot));setFixest_nthreads(1)
parent<-media_path('results/sheinbaum/main_results/lottery-through-2025-06-15')
out<-file.path(parent,'pooled_interactions_combined');dir.create(out,recursive=TRUE,showWarnings=FALSE)
save_csv<-function(x,name)write.csv(x,file.path(out,name),row.names=FALSE)
oldmanifest<-read.csv(file.path(parent,'input_manifest.csv'))
stopifnot(identical(unname(tools::md5sum(oldmanifest$path)),oldmanifest$md5))
paths<-c(file.path(parent,c('analysis_panel.rds','winsorization_cutoffs.csv')),
  'output/balance/sheinbaum_12m/metadata_links.csv',
  media_path('data/00-newspaper_data/processed/newspaper_metadata_geocoded.parquet'))
manifest<-data.frame(path=normalizePath(paths),md5=unname(tools::md5sum(paths)))
x<-readRDS(paths[1]);cuts<-read.csv(paths[2]);links<-read.csv(paths[3])
meta<-read_parquet(paths[4]) |> transmute(metadata_id,ideology_4t=ideology.4t)
members<-links |> left_join(meta,by='metadata_id',relationship='many-to-one')
classes<-members |> group_by(unit_id) |>
  summarise(codes=paste(sort(unique(na.omit(ideology_4t))),collapse=' | '),.groups='drop') |>
  mutate(group_original=case_when(codes=='aligned'~'Aligned',codes=='opp'~'Opposition',
    codes=='unclear'~'Independent',TRUE~NA_character_),
    group=ifelse(group_original %in% c('Opposition','Independent'),'Opp. + Independent',group_original),
    exclusion_reason=case_when(codes==''~'Missing classification',is.na(group)~'Conflicting linked-brand classifications',TRUE~NA_character_))
all<-x$data |> left_join(classes,by='unit_id',relationship='many-to-one')
save_csv(members |> filter(unit_id %in% all$unit_id),'metadata_members.csv')
save_csv(all |> distinct(unit_id,codes,group_original,group,exclusion_reason),'classification_audit.csv')
d0<-all |> filter(!is.na(group)) |> group_by(date) |> filter(any(ask==1),any(ask==0)) |> ungroup() |>
  mutate(ask_aligned=ask*as.integer(group=='Aligned')) |> arrange(unit_id,date)
probe<-feols(log1p(videos)~ask+ask_aligned|unit_id+date,d0,cluster=~unit_id,notes=FALSE)
d<-as.data.frame(d0[obs(probe),])
save_csv(anti_join(all,d,by=c('unit_id','date')) |> select(unit_id,date,ask,codes,group,exclusion_reason),'sample_exclusions.csv')
save_csv(d |> group_by(group) |> summarise(n=n(),units=n_distinct(unit_id),dates=n_distinct(date),
  speaking_days=sum(ask),speaking_outlets=n_distinct(unit_id[ask==1]),zero_video_days=sum(videos==0),.groups='drop'),'group_sample_sizes.csv')
flow<-function(z,stage)data.frame(stage,n=nrow(z),units=n_distinct(z$unit_id),dates=n_distinct(z$date),speaking_days=sum(z$ask),zero_video_days=sum(z$videos==0))
save_csv(bind_rows(flow(all,'Main regression input'),flow(filter(all,!is.na(group)),'Unambiguous classification'),
  flow(d0,'Within-date speaking variation'),flow(d,'After FE singleton removal')),'sample_flow.csv')
write_parquet(d,file.path(out,'analysis_panel.parquet'))
saveRDS(list(data=d,controls=x$controls,quarters=x$quarters),file.path(out,'analysis_panel.rds'))
d$unit_id<-factor(d$unit_id);d$date<-factor(d$date)
OUTCOMES<-c('videos','interactions','mean_interactions','likes','comments','views')
B<-9999L;SEED<-20261012L;terms<-c('ask','ask_aligned')
hypotheses<-list(combined=list(label='Opp. + Independent',w=c(1,0),param='ask',R=1),
  aligned=list(label='Aligned',w=c(1,1),param=terms,R=c(1,1)),
  difference=list(label='Aligned - (Opp. + Independent)',w=c(0,1),param='ask_aligned',R=1))
fits<-rows<-bootrows<-list()
for(o in OUTCOMES)for(adjusted in c(FALSE,TRUE)) {
  model<-if(adjusted)'History adjusted' else 'Baseline'
  d$Y<-log1p(pmin(d[[o]],cuts$upper[cuts$outcome==o]))
  rhs<-c(terms,if(adjusted)x$controls)
  fml<-as.formula(paste('Y ~',paste(rhs,collapse=' + '),'| unit_id + date'))
  f<-feols(fml,data=d,cluster=~unit_id,notes=FALSE)
  stopifnot(nobs(f)==nrow(d),identical(obs(f),seq_len(nrow(d))),is.null(f$collin.var))
  fits[[paste(o,model,sep=':')]]<-f
  b<-coef(f)[terms];V<-vcov(f)[terms,terms,drop=FALSE];df<-degrees_freedom(f,'t')
  # Equivalent direct group slopes, sharing the SAME date FE and histories.
  dd<-d;dd$ask_combined<-dd$ask-dd$ask_aligned
  alt<-feols(as.formula(paste('Y ~',paste(c('ask_combined','ask_aligned',if(adjusted)x$controls),collapse=' + '),'| unit_id + date')),
    data=dd,cluster=~unit_id,notes=FALSE)
  for(h in names(hypotheses)) {
    sp<-hypotheses[[h]];beta<-sum(sp$w*b);s<-sqrt(drop(sp$w%*%V%*%sp$w))
    if(h!='difference') {
      term<-if(h=='combined')'ask_combined' else 'ask_aligned'
      stopifnot(abs(beta-coef(alt)[[term]])<1e-8,abs(s-se(alt)[[term]])<1e-8)
    }
    set.seed(SEED);dqrng::dqset.seed(SEED)
    message(o,' / ',model,' / ',sp$label,': ',B,' draws')
    bt<-boottest(f,param=sp$param,R=sp$R,r=0,B=B,clustid='unit_id',bootcluster='unit_id',fe='unit_id',
      type='rademacher',impose_null=TRUE,bootstrap_type='fnw11',p_val_type='two-tailed',conf_int=FALSE,
      engine='R',nthreads=1,ssc=boot_ssc(adj=TRUE,cluster.adj=TRUE,fixef.K='none'))
    draws<-as.numeric(bt$t_boot)
    stopifnot(bt$N==nrow(d),unname(bt$N_G)==nlevels(d$unit_id),length(draws)==B,all(is.finite(draws)),
      isTRUE(bt$impose_null),bt$r==0,abs(bt$point_estimate-beta)<1e-8,
      abs(bt$p_val-mean(abs(draws)>=abs(as.numeric(bt$t_stat))))<1e-10)
    tag<-paste(o,if(adjusted)'adjusted' else 'baseline',h,sep='_')
    saveRDS(list(test=bt,spec=sp,B=B,seed=SEED),file.path(out,paste0('wild_',tag,'.rds')))
    rows[[tag]]<-data.frame(outcome=o,model,label=sp$label,estimate=beta,se=s,
      ci_low=beta-qt(.975,df)*s,ci_high=beta+qt(.975,df)*s,p_value=2*pt(-abs(beta/s),df),
      wild_p=as.numeric(bt$p_val),n=nrow(d),units=nlevels(d$unit_id),dates=nlevels(d$date))
    bootrows[[tag]]<-data.frame(outcome=o,model,label=sp$label,B,seed=SEED,valid_draws=length(draws),
      mc_se=sqrt(bt$p_val*(1-bt$p_val)/B))
    save_csv(bind_rows(rows),'results.csv')
  }
}
saveRDS(fits,file.path(out,'fits.rds'));save_csv(bind_rows(bootrows),'wild_bootstrap_audit.csv')
stopifnot(identical(unname(tools::md5sum(paths)),manifest$md5))
save_csv(manifest,'input_manifest.csv');writeLines(capture.output(sessionInfo()),file.path(out,'session_info.txt'))
print(as_tibble(bind_rows(rows)) |> filter(model=='History adjusted') |> select(outcome,label,estimate,p_value,wild_p),n=18)
