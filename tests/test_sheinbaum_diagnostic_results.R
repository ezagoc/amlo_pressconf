source('project_paths.R')
suppressPackageStartupMessages({library(arrow);library(fixest)})
setFixest_nthreads(1)
out<-media_path('results/sheinbaum/intermittent_did/five_weekdays_including_question/diagnostics_heterogeneity')
d<-as.data.frame(read_parquet(file.path(out,'analysis_panel.parquet')))
hash<-unname(tools::md5sum(file.path(out,'analysis_panel.parquet')))
a<-readRDS(file.path(out,'diagnostics_1000.rds'));h<-readRDS(file.path(out,'heterogeneity_1000.rds'))
for(x in list(a,h))stopifnot(x$input$B==1000,identical(x$input$panel_md5,hash),all(is.finite(x$boots)),dim(x$boots)[1]==1000)
for(model in c('adjusted','baseline'))for(design in c('original','clean')){
 al<-paste(model,design,'aligned',sep=':');op<-paste(model,design,'comparison',sep=':');gap<-paste(model,design,'difference',sep=':')
 stopifnot(max(abs(h$point[gap,]-(h$point[al,]-h$point[op,])))<1e-10,
   max(abs(h$boots[,gap,]-(h$boots[,al,]-h$boots[,op,])))<1e-10)
}
# Independently reproduce held-out and heterogeneous point estimates using single-outcome fits.
controls<-c('attendance_dummy','history_2025Q1','missing_2025Q1','history_2025Q2','missing_2025Q2')
residual<-function(z,clean=TRUE,weights=NULL){
 z$w<-if(is.null(weights))1 else weights
 use<-if(clean)z$clean_train else z$D==0
 f<-feols(as.formula(paste('Y_views~',paste(controls,collapse='+'),'|unit_id+sample_day')),z[use&z$w>0,],weights=~w,notes=FALSE)
 list(fit=f,r=z$Y_views-predict(f,newdata=z))
}
z<-d[d$clean_eligible,];r<-residual(z)$r
stopifnot(abs(mean(r[z$pre_day!=0&!z$overlap])-a$point['pre_average','views'])<1e-8,
 abs(mean(r[z$post_day!=0&!z$overlap])-a$point['post_average','views'])<1e-8)
z<-d[!is.na(d$group),];r<-residual(z,FALSE)$r
for(g in c('Aligned','Opp. + Independent')){
 key<-if(g=='Aligned')'adjusted:original:aligned' else 'adjusted:original:comparison'
 stopifnot(abs(mean(r[z$D==1&z$group==g])-h$point[key,'views'])<1e-8)
}
# Frequency weights equal literal resampling of whole outlet clusters.
set.seed(1201);u<-unique(z$unit_id);draw<-sample(u,length(u),replace=TRUE)
w<-tabulate(match(draw,u),nbins=length(u))[match(z$unit_id,u)]
weighted<-residual(z,FALSE,w)$r
expanded<-do.call(rbind,lapply(seq_along(draw),function(i){v<-z[z$unit_id==draw[i],];v$unit_id<-paste0('copy_',i);v}))
r2<-residual(expanded,FALSE)$r
for(g in c('Aligned','Opp. + Independent')){
 ii<-which(z$D==1&z$group==g&w>0)
 stopifnot(abs(weighted.mean(weighted[ii],w[ii])-mean(r2[expanded$D==1&expanded$group==g]))<1e-7)
}
# Independently check reported SEs, joint tests and simultaneous critical values.
for(mode in c('diagnostics','heterogeneity')){
 x<-if(mode=='diagnostics')a else h
 rows<-read.csv(file.path(out,paste0(mode,'_results_1000.csv')))
 for(i in seq_len(nrow(rows))){r<-rows[i,];stopifnot(abs(r$se-sd(x$boots[,r$statistic,r$outcome]))<1e-10)}
}
joint<-read.csv(file.path(out,'diagnostics_joint_tests_1000.csv'))
for(i in seq_len(nrow(joint))){
 r<-joint[i,];ii<-grep(paste0('^',r$test,'_-?[0-9]+$'),rownames(a$point));b<-a$boots[,ii,r$outcome];s<-apply(b,2,sd)
 t<-apply(abs(sweep(sweep(b,2,a$point[ii,r$outcome]),2,s,'/')),1,max)
 obs<-max(abs(a$point[ii,r$outcome]/s))
 stopifnot(abs((1+sum(t>=obs))/1001-r$joint_p)<1e-10)
}
cat('PASS: exact inputs; paired group differences on every draw; explicit versus weighted cluster resampling; independent points, SEs and joint tests.\n')
