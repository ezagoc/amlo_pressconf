# Explicit-date FE counterfactual imputation; joint outlet bootstraps across outcomes/groups.
source('project_paths.R')
suppressPackageStartupMessages({library(arrow);library(fixest);library(jsonlite)})
setFixest_nthreads(1)
args<-commandArgs(TRUE)
option<-function(key,default){v<-grep(paste0('^--',key,'='),args,value=TRUE);if(length(v))sub(paste0('^--',key,'='),'',v[1]) else default}
mode<-option('mode','diagnostics');B<-as.integer(option('nboots','1000'));stopifnot(mode%in%c('diagnostics','heterogeneity'),B>=5)
parent<-media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question')
out<-file.path(parent,'diagnostics_heterogeneity');path<-file.path(out,'analysis_panel.parquet');hash<-unname(tools::md5sum(path))
d<-as.data.frame(read_parquet(path));d$date<-as.Date(d$date)
OUTCOMES<-c('videos','interactions','mean_interactions','likes','comments','views')
controls<-c('attendance_dummy','history_2025Q1','missing_2025Q1','history_2025Q2','missing_2025Q2')
YCOLS<-paste0('Y_',OUTCOMES)
# The fixed-effects imputation is mathematically the FEct method='fe' point estimator.
# Multivariate feols reuses the common design; sampling weights exactly represent
# replicated outlet clusters without duplicating identical fixed effects.
impute<-function(z,train,w,adjusted=TRUE){
  use<-train&w>0;target<-which(w>0);z$boot_w<-w
  fml<-as.formula(paste('c(',paste(YCOLS,collapse=','),') ~',paste(if(adjusted)controls else controls[1],collapse='+'),'| unit_id + sample_day'))
  fit<-feols(fml,z[use,],weights=~boot_w,notes=FALSE,warn=FALSE,fixef.rm='none')
  residual<-matrix(NA_real_,nrow(z),length(YCOLS),dimnames=list(NULL,OUTCOMES))
  for(j in seq_along(YCOLS)){
    f<-fit[[j]];stopifnot(nobs(f)==sum(use))
    pred<-predict(f,newdata=z[target,]);stopifnot(all(is.finite(pred)))
    # A dropped covariate must be redundant on target cells too, not unsupported.
    if(!is.null(f$collin.var))stop('Rank deficient covariate design: ',paste(f$collin.var,collapse=','))
    residual[target,j]<-z[[YCOLS[j]]][target]-pred
  }
  residual
}
aggregate_cells<-function(r,mask,w){ii<-which(mask&w>0);stopifnot(length(ii)>0);colSums(r[ii,,drop=FALSE]*w[ii])/sum(w[ii])}
# Before custom diagnostic fits, match all six saved package FEct point estimates.
check_original<-function(){
  r<-impute(d,d$D==0,rep(1,nrow(d)))
  for(j in seq_along(OUTCOMES)){
    old<-readRDS(file.path(parent,'fect_1000',paste0(OUTCOMES[j],'_adjusted.rds')))
    stopifnot(abs(mean(r[d$D==1,j])-old$fit$att.avg)<1e-4)
  }
}
check_original()
if(mode=='diagnostics'){
  z<-d[d$clean_eligible,];strata<-rep('Pooled',nrow(z))
  stat<-function(w){
    clean<-impute(z,z$clean_train,w);base<-impute(z,z$D==0,w)
    masks<-c(setNames(lapply(-5:-1,function(k)z$pre_day==k&!z$overlap),paste0('pre_',-5:-1)),
      setNames(lapply(1:5,function(k)z$post_day==k&!z$overlap),paste0('post_',1:5)),
      list(pre_average=z$pre_day!=0&!z$overlap,post_average=z$post_day!=0&!z$overlap,
        att_clean=z$D==1))
    a<-do.call(rbind,lapply(masks,function(m)aggregate_cells(clean,m,w)))
    a<-rbind(a,att_original_matched=aggregate_cells(base,z$D==1,w))
    rbind(a,att_clean_minus_original=a['att_clean',]-a['att_original_matched',])
  }
}else{
  z<-d[!is.na(d$group),];strata<-z$group
  stat<-function(w){
    stats<-list()
    for(adjusted in c(FALSE,TRUE)){
      model<-if(adjusted)'adjusted' else 'baseline'
      for(design in c('original','clean')){
        keep<-if(design=='clean')z$clean_eligible else rep(TRUE,nrow(z));v<-z[keep,];vw<-w[keep]
        r<-impute(v,if(design=='clean')v$clean_train else v$D==0,vw,adjusted)
        al<-aggregate_cells(r,v$D==1&v$group=='Aligned',vw)
        op<-aggregate_cells(r,v$D==1&v$group=='Opp. + Independent',vw)
        for(g in c('aligned','comparison','difference'))stats[[paste(model,design,g,sep=':')]]<-switch(g,aligned=al,comparison=op,difference=al-op)
      }
    }
    do.call(rbind,stats)
  }
}
units<-unique(z$unit_id);unit_strata<-strata[match(units,z$unit_id)];idx<-match(z$unit_id,units)
input<-list(mode=mode,B=B,seed=20261027L,panel_md5=hash,units=units,method='FEct-equivalent fixed-effects imputation; joint heldouts; ordinary pairs bootstrap',fixest=as.character(packageVersion('fixest')))
checkpoint<-file.path(out,paste0(mode,'_',B,'.rds'))
saved<-if('--resume'%in%args&&file.exists(checkpoint))readRDS(checkpoint) else NULL
if(!is.null(saved)&&identical(input,saved$input)){
  point<-saved$point;boots<-saved$boots;message('Reusing exact checkpoint: ',mode)
}else{
  point<-stat(rep(1,nrow(z)));stopifnot(all(is.finite(point)))
  boots<-array(NA_real_,c(B,nrow(point),ncol(point)),dimnames=list(NULL,rownames(point),colnames(point)))
  set.seed(input$seed)
  for(b in seq_len(B)){
    count<-integer(length(units))
    for(g in unique(unit_strata)){u<-which(unit_strata==g);draw<-sample(u,length(u),replace=TRUE);count<-count+tabulate(draw,nbins=length(units))}
    boots[b,,]<-stat(count[idx]);stopifnot(all(is.finite(boots[b,,])))
    if(b%%50==0)message(mode,': ',b,'/',B,' complete')
  }
  saveRDS(list(input=input,point=point,boots=boots),checkpoint)
}
rows<-list()
for(i in seq_len(nrow(point)))for(j in seq_len(ncol(point))){
  se<-sd(boots[,i,j]);e<-point[i,j]
  rows[[length(rows)+1]]<-data.frame(statistic=rownames(point)[i],outcome=colnames(point)[j],estimate=e,se,
    ci_low=e-qnorm(.975)*se,ci_high=e+qnorm(.975)*se,p_value=2*pnorm(-abs(e/se)),B,valid_draws=sum(is.finite(boots[,i,j])))
}
results<-do.call(rbind,rows);write.csv(results,file.path(out,paste0(mode,'_results_',B,'.csv')),row.names=FALSE)
if(mode=='diagnostics'){
  tests<-list();bands<-list()
  for(test in c('pre','post'))for(j in seq_along(OUTCOMES)){
    ii<-grep(paste0('^',test,'_-?[0-9]+$'),rownames(point));q<-boots[,ii,j];s<-apply(q,2,sd)
    centered<-sweep(sweep(q,2,point[ii,j]),2,s,'/');maxboot<-apply(abs(centered),1,max)
    observed<-max(abs(point[ii,j]/s));critical<-unname(quantile(maxboot,.95))
    tests[[length(tests)+1]]<-data.frame(test,outcome=OUTCOMES[j],max_t=observed,joint_p=(1+sum(maxboot>=observed))/(B+1),simultaneous_critical=critical,B)
    bands[[length(bands)+1]]<-data.frame(test,outcome=OUTCOMES[j],day=as.integer(sub(paste0(test,'_'),'',rownames(point)[ii])),estimate=point[ii,j],se=s,
      simultaneous_low=point[ii,j]-critical*s,simultaneous_high=point[ii,j]+critical*s)
  }
  write.csv(do.call(rbind,tests),file.path(out,paste0('diagnostics_joint_tests_',B,'.csv')),row.names=FALSE)
  write.csv(do.call(rbind,bands),file.path(out,paste0('diagnostics_bands_',B,'.csv')),row.names=FALSE)
}
stopifnot(hash==unname(tools::md5sum(path)))
writeLines(capture.output(sessionInfo()),file.path(out,paste0(mode,'_session_info.txt')))
print(results[grepl('average|adjusted:original|att_',results$statistic),],row.names=FALSE)
message('PASS ',mode,': all ',B,' paired outlet draws finite; original FEct points matched.')
