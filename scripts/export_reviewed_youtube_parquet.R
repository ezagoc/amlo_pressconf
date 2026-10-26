suppressPackageStartupMessages({library(arrow);library(readr)})
# Run from the repository root after either reviewed YouTube extractor.
source('project_paths.R')
args <- commandArgs(trailingOnly=TRUE)
p <- if(length(args)) args[[1]] else media_path('data','06-outcomes','youtube','reviewed_outlets')
channels <- read_csv(file.path(p,'youtube_channels.csv'),col_types=cols(.default=col_character(), yt_subscriberCount=col_double(),yt_videoCount=col_double(),yt_viewCount=col_double(),yt_hiddenSubs=col_logical(),uploads_complete=col_logical(),pages_fetched=col_double(),saved_video_count=col_double(),reported_minus_saved=col_double()),progress=FALSE)
videos <- read_csv(file.path(p,'youtube_videos.csv'),col_types=cols(.default=col_character(),publishedAt_dt=col_datetime(),viewCount=col_double(),likeCount=col_double(),commentCount=col_double()),progress=FALSE)
stopifnot(nrow(problems(channels))==0L,nrow(problems(videos))==0L,!anyDuplicated(channels$outlet_id),!anyDuplicated(videos$videoId),all(videos$channel_id %in% channels$channelId))
for (name in c('channels','videos')) {
 obj <- get(name);target <- file.path(p,paste0('youtube_',name,'.parquet'));temp <- paste0(target,'.tmp')
 write_parquet(obj,temp);check <- read_parquet(temp)
 stopifnot(nrow(check)==nrow(obj),identical(names(check),names(obj)))
 stopifnot(file.rename(temp,target))
 cat(name,':',nrow(obj),'rows, Parquet verified\n')
}
