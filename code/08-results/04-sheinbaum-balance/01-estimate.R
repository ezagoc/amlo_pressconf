# Same nine metadata / twelve history blocks as the latest AMLO balance.
# Sheinbaum exposure is explicit speaking identification, not exhaustive questions.
suppressPackageStartupMessages({library(arrow);library(dplyr);library(fixest);library(jsonlite)})
setFixest_nthreads(1)
out <- 'output/balance/sheinbaum_12m'
spec <- read.csv(file.path(out,'spec.csv'))
informative <- function(d) d |> group_by(date) |> filter(any(speaking_identified == 1),any(speaking_identified == 0)) |> ungroup()
models <- list(); individual <- list(); joints <- list(); maps <- list(); missing_balance <- list()
for (sample_name in c('full','youtube_overlap')) {
  raw <- read_parquet(file.path(out,paste0(sample_name,'_sample.parquet'))) |> mutate(date=as.Date(date))
  stopifnot(!anyDuplicated(raw[c('unit_id','date')]),all(raw$recorded_attendance_n>0),
            all(raw$common_coverage),all(raw$speaking_identified %in% 0:1))
  fits <- samples <- list()
  for (v in spec$metric) {
    d <- raw |> mutate(x=.data[[v]]) |> filter(is.finite(x)) |> informative()
    if (n_distinct(d$x)<2 || n_distinct(d$unit_id)<2) {
      individual[[length(individual)+1]] <- tibble(sample=sample_name,metric=v,status='No usable variation',n=nrow(d),units=n_distinct(d$unit_id),dates=n_distinct(d$date))
      next
    }
    fit <- feols(x ~ speaking_identified | date,d,cluster=~unit_id,notes=FALSE)
    stopifnot('speaking_identified' %in% names(coef(fit)),nobs(fit)==nrow(d))
    ct <- coeftable(fit)['speaking_identified',];ci<-confint(fit,'speaking_identified')
    individual[[length(individual)+1]] <- tibble(sample=sample_name,metric=v,status='Estimated',
      estimate=ct[[1]],se=ct[[2]],ci_low=ci[[1]],ci_high=ci[[2]],p_value=ct[[4]],
      identified_mean=mean(d$x[d$speaking_identified==1]),other_mean=mean(d$x[d$speaking_identified==0]),
      standardized_difference=ct[[1]]/sd(d$x),n=nobs(fit),units=n_distinct(d$unit_id),dates=n_distinct(d$date),
      missing_share=mean(!is.finite(raw[[v]])))
    fits[[v]]<-fit;samples[[v]]<-d
    # Missingness is an observable feature; do not hide selection into history samples.
    md<-raw |> mutate(missing_value=as.numeric(!is.finite(.data[[v]])))
    if (n_distinct(md$missing_value)>1) {
      mf<-feols(missing_value~speaking_identified|date,md,cluster=~unit_id,notes=FALSE)
      mc<-coeftable(mf)['speaking_identified',]
      missing_balance[[length(missing_balance)+1]]<-tibble(sample=sample_name,metric=v,difference=mc[[1]],p_value=mc[[4]],missing_share=mean(md$missing_value))
    }
  }
  joint_fits<-joint_samples<-list()
  for (block in c('metadata','histories')) {
    vars<-spec$metric[(spec$family=='Metadata')==(block=='metadata')]
    d<-raw; patterns<-list(); mapping<-list()
    for (v in vars) {
      miss<-!is.finite(d[[v]]);scale<-if(block=='metadata') 1 else sd(d[[v]][!miss])
      stopifnot(is.finite(scale),scale>0)
      indicator<-NA_character_
      if(any(miss)) {
        same<-names(patterns)[vapply(patterns,identical,logical(1),miss)]
        indicator<-if(length(same)) same[[1]] else paste0('missing_',v)
        if(!length(same)) { patterns[[indicator]]<-miss;d[[indicator]]<-as.integer(miss) }
      }
      d[[v]]<-ifelse(miss,0,d[[v]]/scale)
      mapping[[v]]<-tibble(sample=sample_name,block=block,metric=v,indicator=indicator,scale=scale,missing_rows=sum(miss))
    }
    terms<-c(vars,names(patterns))
    fml<-as.formula(paste('speaking_identified ~',paste(terms,collapse=' + '),'| date'))
    fit<-feols(fml,d,cluster=~unit_id,notes=FALSE)
    stopifnot(is.null(fit$collin.var),setequal(names(coef(fit)),terms),nobs(fit)==nrow(d))
    V<-vcov(fit)[vars,vars,drop=FALSE];b<-coef(fit)[vars];C<-cov2cor(V)
    ev<-eigen(C,symmetric=TRUE,only.values=TRUE)$values
    stopifnot(min(ev)>0)
    wt<-wald(fit,keep=paste0('^(',paste(vars,collapse='|'),')$'),print=FALSE)
    z<-b/sqrt(diag(V));check<-drop(crossprod(z,solve(C,z)))/length(vars)
    stopifnot(isTRUE(all.equal(wt$stat,check,tolerance=1e-6)),wt$df1==length(vars),wt$df2==n_distinct(d$unit_id)-1)
    centered<-d
    for(v in vars) { ok<-is.finite(raw[[v]]);centered[[v]][ok]<-d[[v]][ok]-mean(d[[v]][ok]) }
    cf<-feols(fml,centered,cluster=~unit_id,notes=FALSE)
    check_center<-wald(cf,keep=paste0('^(',paste(vars,collapse='|'),')$'),print=FALSE)
    stopifnot(abs(check_center$stat-wt$stat)/max(1,abs(wt$stat))<1e-5)
    joints[[length(joints)+1]]<-tibble(sample=sample_name,block=block,F=wt$stat,df1=wt$df1,df2=wt$df2,p_value=wt$p,
      n=nobs(fit),units=n_distinct(d$unit_id),dates=n_distinct(d$date),missingness_controls=length(patterns),
      covariance_condition=max(ev)/min(ev))
    maps[[length(maps)+1]]<-bind_rows(mapping)
    joint_fits[[block]]<-fit;joint_samples[[block]]<-d
  }
  models[[sample_name]]<-list(raw=raw,individual_fits=fits,individual_samples=samples,joint_fits=joint_fits,joint_samples=joint_samples)
}
individual<-bind_rows(individual) |> left_join(spec,by='metric')
joints<-bind_rows(joints)
write.csv(individual,file.path(out,'individual.csv'),row.names=FALSE)
write.csv(joints,file.path(out,'joint.csv'),row.names=FALSE)
write.csv(bind_rows(maps),file.path(out,'missingness_mapping.csv'),row.names=FALSE)
write.csv(bind_rows(missing_balance),file.path(out,'missingness_balance.csv'),row.names=FALSE)
saveRDS(list(models=models,individual=individual,joint=joints,spec=spec),file.path(out,'models.rds'))
writeLines(capture.output(sessionInfo()),file.path(out,'session_info.txt'))
print(joints,width=160)
print(individual |> select(sample,label,estimate,p_value,n,units),n=50,width=160)
