# Inspect stages 1–2 of the Sheinbaum transcript pilot; writes no files.
suppressPackageStartupMessages({library(arrow); library(dplyr); library(readr)})
starts <- getwd()
script_arg <- commandArgs(FALSE)[startsWith(commandArgs(FALSE), '--file=')]
if (length(script_arg)) starts <- c(starts, dirname(sub('^--file=', '', script_arg[1])))
if (requireNamespace('rstudioapi', quietly = TRUE) && rstudioapi::isAvailable()) {
  starts <- c(starts, dirname(rstudioapi::getActiveDocumentContext()$path))
}
project_root <- NULL
for (start in starts) {
  p <- normalizePath(start, mustWork = FALSE)
  repeat {
    if (file.exists(file.path(p, 'project_paths.R'))) {project_root <- p; break}
    if (identical(p, dirname(p))) break
    p <- dirname(p)
  }
  if (!is.null(project_root)) break
}
if (is.null(project_root)) stop('Run inside amlo_pressconf or open this script in RStudio.')
source(file.path(project_root, 'project_paths.R'), chdir = TRUE)
SOURCE_VERSION <- 'official' # Use 'github' to inspect the preserved earlier pilot.
stopifnot(SOURCE_VERSION %in% c('official', 'github'))
pilot_root <- media_path('data', '02-conferences-sheinbaum', 'transcript_analysis',
                         if (SOURCE_VERSION == 'official') 'official-pilot-10' else 'pilot-10')
read_pilot <- function(name) read_parquet(file.path(pilot_root, 'auxiliar', paste0(name, '.parquet')))
conference_measures <- read_pilot('conference_measures')
speakers <- read_pilot('speaker_registry')
turns <- read_pilot('speaking_turns')
questions <- read_pilot('questions')
responses <- read_pilot('responses')
links <- read_pilot('question_response_links')
adjacent_responses <- read_pilot('adjacent_response_turns')
affiliations <- read_pilot('journalist_affiliations')
review_flags <- read_pilot('review_flags')
coverage <- read_pilot('question_turn_coverage')

# Several questions can share one answer; this expanded table is for inspection.
# Never sum its words to estimate total speech. Use conference_measures instead.
question_answers <- questions |>
  left_join(links, by = c('date', 'question_id'), suffix = c('', '_link')) |>
  left_join(responses, by = c('date', 'response_id'), suffix = c('_question', '_response'))
inspect_question <- function(id) {
  list(question = filter(questions, question_id == id),
       linked_responses = filter(question_answers, question_id == id),
       immediately_following_turn = filter(adjacent_responses, question_id == id))
}
# View(conference_measures)
# View(filter(speakers, live_words > 0))
# View(review_flags)
# inspect_question('2024-10-02:q007') # Thematic non-response vs immediate reply.
# browseURL(file.path(pilot_root, 'review', 'index.html'))
print(conference_measures |> select(date, president_words,
  n_other_speaking_officials_provisional, n_questions_and_requests,
  n_questions_linked_to_president))
message('Review only: no files written. Counts and model annotations remain provisional.')
