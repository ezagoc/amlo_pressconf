###################################################
## Descriptive statistics: journalist alignment at mañaneras
## Author: Eduardo Zago-Cuevas (all errors are my own)
## Run after: 05_classify_alignment.py
## Unit of analysis: reporter-day (preguntas only)
##   opp_day = 1 if reporter asked >= 1 oppositional pregunta that day
## Window: ±1 year around the April 14 2022 lottery
##   Pre-lottery : 2021-04-14 – 2022-04-13
##   Post-lottery: 2022-04-14 – 2023-04-13
###################################################

# install.packages('pacman')

pacman::p_load(tidyverse, arrow, patchwork, zoo, scales, xtable)

rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../../project_paths.R")

LOTTERY_DATE <- as.Date('2022-04-14')

pfo     <- paste0(media_path('data', '02-conferences', 'auxiliar'), '/')
res_dir <- paste0(dirname(media_output_path('results', 'descriptives', '.keep')), '/')
dir.create(res_dir, recursive = TRUE, showWarnings = FALSE)

df <- read_parquet(paste0(pfo, 'questions_dataset_dedup.parquet')) |>
  mutate(date = as.Date(date)) |> select(-period)

att <- read_parquet(media_path('data', '02-conferences', 'raw', 'attendance', 'panel_attendance.parquet.gzip')) |>
  mutate(date = as.Date(fecha)) |>
  mutate(period = factor(if_else(date < LOTTERY_DATE,
                                 'Pre-lottery', 'Post-lottery'),
                         levels = c('Pre-lottery', 'Post-lottery'))) 

bridge <- readxl::read_excel(media_path('data', '00-newspaper_data', 'mexican_newspapers.xlsx'))
bridge <- bridge |> select(names.transcripts, names.conference) |> 
  distinct(names.transcripts, names.conference) |> 
  mutate(
    outlet_final = names.conference |>
      str_to_lower() |>
      stri_trans_general("Latin-ASCII"), 
    outlet_aux = names.transcripts |>
      str_to_lower() |>
      stri_trans_general("Latin-ASCII")
  ) |>
  select(outlet_final, outlet_aux)

att <- att |> 
  filter(date > '2021-05-01') |> filter(date < '2023-02-24')

att <- att |> left_join(bridge) |> filter(is.na(outlet_aux) == F)

totalman <- att |> distinct(date, .keep_all = T) |>
  group_by(period) |> summarise(total = n()) |>
  ungroup()

att <- att |> filter(attended == 1)


#### 

out_dedup <- df |> distinct(date, outlet_aux, .keep_all = T)

att <- att |> left_join(out_dedup, by = c('date', 'outlet_aux'))

att <- att |> mutate(asked = ifelse(is.na(text) == F, 1, 0))

out_dedup_final <- att |>
  group_by(outlet_aux, period) |>
  summarise(n_att = sum(attended),
            n_que = sum(asked)) |>
  ungroup() |>
  mutate(ratio = n_que / n_att) |> filter(ratio>0) |> filter(ratio<1)

# Compute means per group
means <- aggregate(ratio ~ period, data = out_dedup_final, FUN = mean)

ggplot(out_dedup_final, 
       aes(x = ratio, fill = period, color = period)) +
  geom_density(alpha = 0.25, linewidth = 0.8) +
  scale_fill_manual(values = c("Pre-lottery" = "#3266ad", "Post-lottery" = "#c04f2e")) +
  scale_color_manual(values = c("Pre-lottery" = "#3266ad", "Post-lottery" = "#c04f2e")) +
  labs(
    x = "Ratio (questions / attendees)",
    y = "Density",
    fill = NULL,
    color = NULL
  ) +
  theme_minimal(base_size = 13) +
  theme(
    legend.position = "top",
    panel.grid.minor = element_blank()
  )


############### Dedup:


