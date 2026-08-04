# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(arrow)
library(kableExtra)

path_co <- paste0(media_path('data', '01-social_communication'), '/')

df <- read_parquet(paste0(path_co, 
                          '01-intermediate/beneficiarios_panel_2016_2021.parquet'))


df <- df |> filter(between(year.contrato, 2017, 2020)) |> 
  mutate(before_amlo = ifelse(year.contrato < 2019, 1, 0))


df_bef <- df |> filter(before_amlo == 1) |> group_by(beneficiario) |> 
  summarise(importe = sum(importe))

df_aft <- df |> filter(before_amlo == 0) |> group_by(beneficiario) |> 
  summarise(importe_aft = sum(importe))

df_final <- df_bef |> left_join(df_aft) 

df_final <- df_final |> mutate(change = importe_aft - importe)

df_final$percent_change <- ((df_final$importe_aft - df_final$importe) / df_final$importe)*100

df_p <- df_final |> filter(change > 0) |> arrange(desc(change)) |> head(10) |>
  select(beneficiario, change, percent_change)

df_n <- df_final |> filter(change < 0) |> arrange(change) |> head(10) |> 
  select(beneficiario, change, percent_change)

df_latex2 <- cbind(df_p, df_n)

df_aft_lat <- df_aft |> arrange(desc(importe_aft)) |> head(10)

df_bef_lat <- df_bef |> arrange(desc(importe)) |> head(10)

df_latex <- cbind(df_bef_lat, df_aft_lat)

kable(df_latex, format = "latex", booktabs = TRUE, caption = "Summary Statistics of Spending")

kable(df_latex2, format = "latex", booktabs = TRUE, caption = "Summary Statistics of Spending")

df_final <- df_final |> mutate(change = ifelse(percent_change<0, 
                                               -log(importe - importe_aft), 
                                               log(importe_aft - importe)))

data_long <- df_final %>% 
  pivot_longer(cols = c(importe, importe_aft), 
               names_to = "category", 
               values_to = "spending")

data_long <- data_long |> filter(spending>0)

# Plot the densities
ggplot(data_long, aes(x = spending, fill = category, color = category)) +
  geom_histogram(alpha = 0.5) +  # Density plot with transparency
  labs(
    title = "Density Plot of Spending Before and After",
    x = "Spending",
    y = "Density",
    fill = "Category",
    color = "Category"
  ) +
  theme_minimal(base_size = 14) +  # Clean minimal theme
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold"),  # Center title
    legend.position = "top"
  )

ggplot(df_final, aes(x = change)) +
  geom_histogram(fill = "darkred", alpha = 0.7) +  # Smooth density plot with color
  labs(
    title = "Density Plot of Spending",
    x = "Spending",
    y = "Density"
  ) +
  theme_minimal() +  # Clean theme with readable text
  theme(
    plot.title = element_text(hjust = 0.5, face = "bold")  # Center and bold title
  )
