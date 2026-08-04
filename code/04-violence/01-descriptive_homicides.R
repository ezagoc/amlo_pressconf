# 0.0 Set up the environment, clean it and set working directory to the code path
rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

library(purrr)
library(tidyverse)
library(sf)

path_co <- paste0(media_path('data', '04-violence', '01-crime_violence', 'final'), '/')

df <- readxl::read_excel(paste0(path_co, 'panel_homicides_2015_2023.xlsx'))

df_agg <- df |> filter(between(year, 2015, 2022)) |> group_by(year, month) |>
  summarise(across(c(homicide, drugs), ~sum(.x))) |> ungroup() |>
  mutate(date = as.Date(paste0(year, '-', month, '-', 1)))

year_labels <- format(seq(as.Date("2015-01-01"), as.Date("2022-01-01"), 
                          by = "1 year"), "%Y")


p1 <- ggplot(df_agg, aes(date)) + 
  geom_line(aes(y = homicide), size = .6) +  # Line for Variable 1
  theme_classic() + 
  geom_vline(xintercept=as.Date('2019-01-01'), color="black", linetype="dotted") +
  geom_label(mapping = aes(x = as.Date('2019-01-01'), y = 4500, 
                           label = "Start AMLO's tenure"), colour='black') +
  scale_x_date(breaks = seq(as.Date("2015-01-01"), as.Date("2023-12-1"), by = "1 year"),
               labels = year_labels,
               date_labels = "%Y") +
  scale_y_continuous(breaks = seq(0, 4500, by = 100), limits = c(2000, 4500)) +
  labs(y= "Number of Homicides", x = "Month-Year")

p1

ggsave(p1, filename = media_output_path('results', 'descriptives', 'homicides.pdf'),
       device = cairo_pdf,
       dpi = 300, width = 8.45, height = 6.4, units = 'in')

#### Distribution

pop <- haven::read_dta(media_path('data', '05-others', 'Censo2020_MUNICIPAL.dta')) |>
  select(code_inegi, POBTOT)

df_bef <- df |> filter(between(year, 2017, 2018)) |> group_by(code_inegi) |> 
  summarise(homicide = sum(homicide)) |> ungroup() |> left_join(pop) |>
  mutate(hom_bef_100 = (homicide/POBTOT)*100000) |> select(code_inegi, hom_bef_100)

df_aft <- df |> filter(between(year, 2019, 2020)) |> group_by(code_inegi) |> 
  summarise(homicide = sum(homicide)) |> ungroup() |> left_join(pop) |>
  mutate(hom_aft_100 = (homicide/POBTOT)*100000) |> select(code_inegi, hom_aft_100)

muns_pol2 <- read_sf(media_path('data', '05-others', 'shapefile_media', 'mun.shp')) |>
  mutate(code_inegi = 1000*as.numeric(CVE_ENT) + as.numeric(CVE_MUN)) |>
  left_join(df_bef) |> left_join(df_aft)


library(classInt)

muns_pol2 <- muns_pol2 |> drop_na()
# get quantile breaks. Add .00001 offset to catch the lowest value
breaks_qt <- classIntervals(c(min(muns_pol2$hom_bef_100) - .0001,
                              muns_pol2$hom_bef_100), n = 7, style = "quantile")

max(muns_pol2$hom_bef_100)
str(breaks_qt)

d <- muns_pol2 %>% 
  mutate(arc_cat = cut(hom_bef_100, breaks_qt$brks)) %>% 
  ggplot() + 
  geom_sf(aes(fill=arc_cat), color = NA) +
  scale_fill_brewer(palette = "OrRd") +
  labs(fill = "Homicides per 100K") + 
  theme(legend.text = element_text(size = 8),
        legend.title = element_text(size = 8),
        panel.background = element_rect(fill = "white"))

ggsave(d, filename = media_output_path('results', 'descriptives', 'map_homicides_before.pdf'),
       device = cairo_pdf,
       dpi = 300, width = 8.45, height = 6.4, units = 'in')

#### 

breaks_qt <- classIntervals(c(min(muns_pol2$hom_aft_100) - .0001,
                              muns_pol2$hom_aft_100), n = 7, style = "quantile")

max(muns_pol2$hom_aft_100)
str(breaks_qt)

d <- muns_pol2 %>% 
  mutate(arc_cat = cut(hom_aft_100, breaks_qt$brks)) %>% 
  ggplot() + 
  geom_sf(aes(fill=arc_cat), color = NA) +
  scale_fill_brewer(palette = "OrRd") +
  labs(fill = "Homicides per 100K") + 
  theme(legend.text = element_text(size = 8),
        legend.title = element_text(size = 8),
        panel.background = element_rect(fill = "white"))

ggsave(d, filename = media_output_path('results', 'descriptives', 'map_homicides_after.pdf'),
       device = cairo_pdf,
       dpi = 300, width = 8.45, height = 6.4, units = 'in')

