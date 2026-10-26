suppressPackageStartupMessages({library(dplyr);library(fixest);library(arrow)})
out<-'output/balance/sheinbaum_12m'
x<-readRDS(file.path(out,'models.rds'))
stopifnot(nrow(x$individual)==42,nrow(x$joint)==4,!any(grepl('^age_',x$spec$metric)))
for (s in names(x$models)) {
  m<-x$models[[s]]
  d<-read_parquet(file.path(out,paste0(s,'_sample.parquet'))) |> mutate(date=as.Date(date))
  stopifnot(identical(m$raw,d),all(d$date>=as.Date('2024-10-01')),all(d$date<=as.Date('2025-06-15')),
    !anyDuplicated(d[c('unit_id','date')]),all(d$recorded_attendance_n>0),all(d$common_coverage))
  if(s=='youtube_overlap') stopifnot(all(d$yt_eligible))
  for(v in x$spec$metric) {
    ds<-m$individual_samples[[v]];f<-m$individual_fits[[v]]
    # Independent within-date OLS calculation checks the exposure and direction.
    yd<-ds$x-ave(ds$x,ds$date)
    xd<-ds$speaking_identified-ave(ds$speaking_identified,ds$date)
    beta<-sum(yd*xd)/sum(xd^2)
    stopifnot(abs(beta-coef(f)[['speaking_identified']])<1e-9,
              all(is.finite(ds$x)),nobs(f)==nrow(ds))
    row<-filter(x$individual,sample==s,metric==v)
    stopifnot(abs(row$estimate-beta)<1e-9, row$n==nrow(ds),row$units==n_distinct(ds$unit_id))
  }
  for(b in c('metadata','histories')) {
    row<-filter(x$joint,sample==s,block==b);f<-m$joint_fits[[b]]
    stopifnot(row$n==nrow(d),row$df2==n_distinct(d$unit_id)-1,
      abs(pf(row$F,row$df1,row$df2,lower.tail=FALSE)-row$p_value)<1e-10,
      is.null(f$collin.var))
    if(b=='metadata') stopifnot(length(coef(f))==9,!any(grepl('missing_',names(coef(f)))))
  }
}
cat('PASS: 42 independent date-demeaned coefficients; 4 joint p-values; strict roster, coverage, samples and model separation.\n')
