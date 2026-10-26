source('project_paths.R')
suppressPackageStartupMessages({library(arrow);library(jsonlite);library(fixest)})
setFixest_nthreads(1)
out <- media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question')
d <- as.data.frame(read_parquet(file.path(out,'analysis_panel.parquet')))
a <- fromJSON(file.path(out,'build_audit.json'))
files <- list.files(file.path(out,'fect_1000'),pattern='[.]rds$',full.names=TRUE)
stopifnot(length(files)==12L)
for(path in files){
 s <- readRDS(path);f <- s$fit;i <- s$input
 stopifnot(i$nboots==1000,identical(i$panel_md5,unname(tools::md5sum(file.path(out,'analysis_panel.parquet')))),
   f$N==125,f$T==179,sum(f$I.dat)==nrow(d),sum(f$D.dat[f$I.dat==1])==sum(d$D),
   length(f$att.avg.boot)==1000,all(is.finite(f$att.avg.boot)))
 z <- i$data; controls <- setdiff(names(z),c('unit_id','sample_day','Y','D'))
 fit <- feols(as.formula(paste('Y ~',paste(controls,collapse='+'),'| unit_id + sample_day')),z[z$D==0,],notes=FALSE)
 residual <- z$Y[z$D==1]-predict(fit,newdata=z[z$D==1,])
 stopifnot(all(is.finite(residual)),abs(mean(residual)-f$att.avg)<1e-4,
   abs(coef(fit)[['attendance_dummy']]-f$est.beta[1,1])<1e-4,
   abs(sd(as.numeric(f$att.avg.boot))-f$est.avg[1,2])<1e-8)
}
cat('PASS: 12 exact-input fits; 12,000 finite outlet-bootstrap draws; independent ATT and attendance checks.\n')
