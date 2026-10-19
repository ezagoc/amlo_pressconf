# Audit already collected YouTube files; never alter production inputs.
suppressPackageStartupMessages({library(dplyr);library(readxl);library(arrow);library(jsonlite)})
source("project_paths.R")
report_dir <- "info_newspapers_gpt/outlet_review_20261016"
review <- read.csv(file.path(report_dir,"youtube_review.csv"),check.names=FALSE,na.strings="")
root <- media_path("data","06-outcomes","youtube")
mapping <- read_excel(file.path(root,"mexican_newspapers_youtube.xlsx"))
files <- list.files(root,pattern="\\.parquet$",recursive=TRUE,full.names=TRUE)
files <- files[grepl("/(videos|big_channels)/",files) & !grepl("/playlists/",files)]
inventory <- list()
for (file in files) {
  tab <- open_dataset(file)
  if (!"videoId" %in% names(tab)) next
  fields <- intersect(names(tab),c("videoId","channel_id","channelId","publishedAt_dt","publishedAt","collectedAt"))
  d <- select(tab,all_of(fields)) |> collect()
  cid <- if("channel_id" %in% names(d)) d$channel_id else if("channelId" %in% names(d)) d$channelId else rep(NA_character_,nrow(d))
  day <- if("publishedAt_dt" %in% names(d)) as.character(d$publishedAt_dt) else if("publishedAt" %in% names(d)) d$publishedAt else rep(NA_character_,nrow(d))
  collected <- if("collectedAt" %in% names(d)) as.character(d$collectedAt) else rep(NA_character_,nrow(d))
  inventory[[length(inventory)+1L]] <- data.frame(video_id=d$videoId,channel_id=cid,published=day,collected=collected,source_file=file)
}
all <- bind_rows(inventory)
extreme <- function(x,fun) if(all(is.na(x))) NA_character_ else fun(x,na.rm=TRUE)
stats <- all |> filter(!is.na(channel_id)) |> group_by(channel_id) |>
 summarise(saved_video_rows=n(),saved_distinct_videos=n_distinct(video_id),
           earliest_saved_publication=extreme(published,min),latest_saved_publication=extreme(published,max),
           latest_saved_collection=extreme(collected,max),source_files=paste(sort(unique(source_file)),collapse=" | "),.groups="drop")
channel_stats <- mapping |> select(channelId,yt_createdAt,yt_subscriberCount,yt_videoCount,yt_viewCount) |> distinct(channelId,.keep_all=TRUE)
result <- review |> left_join(channel_stats,by=c("channel_id"="channelId"),na_matches="never") |>
 left_join(stats,by="channel_id",na_matches="never") |>
 mutate(saved_data_status=case_when(is.na(channel_id)~"channel_unresolved",is.na(saved_video_rows)~"no_matching_saved_video_file",TRUE~"saved_video_data_found"))
write.csv(result,file.path(report_dir,"youtube_data_audit.csv"),row.names=FALSE,na="")
write_json(list(note="Saved channel counts are historical snapshots of unknown collection date; public-page counts in visible_* are rounded display text. Channel creation is not outlet founding. Saved files are deduplicated by videoId for counts; coverage is observed, not guaranteed complete. Candidate channels retain their identity-review status.",
 examined_files=length(files),matched_outlet_rows=sum(result$saved_data_status=="saved_video_data_found"),checked_outlets=nrow(result)),file.path(report_dir,"youtube_audit_inputs.json"),pretty=TRUE,auto_unbox=TRUE)
print(count(result,saved_data_status))
