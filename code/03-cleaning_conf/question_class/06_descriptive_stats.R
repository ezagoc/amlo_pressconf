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

pfo     <- paste0(media_path('data', '02-conferences', 'auxiliar'), '/')
res_dir <- paste0(dirname(media_output_path('results', 'descriptives', '.keep')), '/')
dir.create(res_dir, recursive = TRUE, showWarnings = FALSE)

LOTTERY_DATE <- as.Date('2022-04-14')
PRE_START    <- as.Date('2021-04-14')
POST_END     <- as.Date('2023-04-13')

# ── Build reporter-day dataset (preguntas only) ───────────────────────────────

join_keys <- c('date', 'reporter', 'outlet', 'turn_index', 'item_index', 'item_type', 'text')

dedup_labels <- read_parquet(paste0(pfo, 'questions_dataset_dedup.parquet')) |>
  mutate(date = as.Date(date)) |>
  select(all_of(join_keys),
         reporter_aux_dedup = reporter_aux,
         outlet_aux_dedup   = outlet_aux) |>
  distinct()

df_raw <- read_parquet(paste0(pfo, 'questions_with_alignment.parquet')) |>
  mutate(date = as.Date(date)) |>
  left_join(dedup_labels, by = join_keys) |>
  mutate(
    reporter_aux = coalesce(reporter_aux_dedup, reporter_aux),
    outlet_aux   = coalesce(outlet_aux_dedup, outlet_aux),
    reporter_aux = str_squish(reporter_aux),
    outlet_aux   = str_squish(outlet_aux)
  ) |>
  select(-reporter_aux_dedup, -outlet_aux_dedup) |>
  filter(item_type %in% c('pregunta', 'question'),
         date >= PRE_START, date <= POST_END,
         !is.na(reporter_aux), reporter_aux != '',
         !is.na(outlet_aux), outlet_aux != '') |>
  mutate(period = factor(if_else(date < LOTTERY_DATE,
                                 'Pre-lottery', 'Post-lottery'),
                         levels = c('Pre-lottery', 'Post-lottery')))

# Collapse to reporter-day: opp_day = 1 if any pregunta was oppositional
df <- df_raw |>
  group_by(reporter_aux, outlet_aux, date, period) |>
  summarise(opp_day     = as.integer(any(alignment == 'oppositional')),
            n_preguntas = n(),
            .groups = 'drop')

cat('\n=== Reporter-day dataset ===\n')
cat('Preguntas in window :', nrow(df_raw), '\n')
cat('Reporter-days       :', nrow(df), '\n')
cat('Unique reporters    :', n_distinct(df$reporter_aux), '\n')
cat('Unique outlets      :', n_distinct(df$outlet_aux), '\n')
cat('Pre-lottery rows    :', sum(df$period == 'Pre-lottery'), '\n')
cat('Post-lottery rows   :', sum(df$period == 'Post-lottery'), '\n')

# ── Shared helpers ────────────────────────────────────────────────────────────

base_theme <- theme_bw() +
  theme(axis.text.x      = element_text(size = 10, colour = 'black', angle = 45, hjust = 1),
        axis.title.x     = element_text(size = 12),
        axis.text.y      = element_text(size = 10, colour = 'black'),
        axis.title.y     = element_text(size = 12),
        legend.position  = 'bottom',
        legend.title     = element_blank(),
        strip.background = element_blank(),
        strip.text       = element_text(size = 11))

period_labels <- c('Pre-lottery'  = 'Pre-lottery (Apr 2021\u2013Apr 2022)',
                   'Post-lottery' = 'Post-lottery (Apr 2022\u2013Apr 2023)')

write_tex <- function(df_tab, file, caption, label, digits = NULL) {
  xt <- xtable(df_tab, caption = caption, label = label, digits = digits)
  print(xt, file = paste0(res_dir, file), include.rownames = FALSE,
        booktabs = TRUE, caption.placement = 'top', comment = FALSE)
  cat('Saved \u2192', file, '\n')
}

# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Overall distribution (console)
# ══════════════════════════════════════════════════════════════════════════════

cat('\n=== Share of oppositional reporter-days ===\n')
print(round(prop.table(table(df$period, df$opp_day), margin = 1) * 100, 1))

ct   <- table(df$period, df$opp_day)
chi2 <- chisq.test(ct)
cat('\nchi2 =', round(chi2$statistic, 2),
    '| p =', format.pval(chi2$p.value, digits = 3), '\n')

# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Weekly trend + before/after bar
# ══════════════════════════════════════════════════════════════════════════════

weekly <- df |>
  mutate(week = floor_date(date, 'week', week_start = 1)) |>
  group_by(week) |>
  summarise(opp_share      = mean(opp_day),
            n_reporter_days = n(),
            .groups = 'drop') |>
  arrange(week) |>
  mutate(opp_share_roll = rollmean(opp_share, k = 4, fill = NA, align = 'center'))

p_weekly <- ggplot(weekly, aes(x = week)) +
  geom_line(aes(y = opp_share), colour = 'grey60', linewidth = .5, alpha = .5) +
  geom_line(aes(y = opp_share_roll), colour = 'black', linewidth = 1) +
  geom_vline(xintercept = as.numeric(LOTTERY_DATE),
             linetype = 'dashed', colour = 'red', linewidth = .7) +
  annotate('text', x = LOTTERY_DATE + 7, y = .97,
           label = 'Lottery', hjust = 0, size = 3.2, colour = 'red') +
  scale_x_date(breaks = seq(PRE_START, POST_END, by = '2 months'),
               date_labels = '%b %Y', limits = c(PRE_START, POST_END)) +
  scale_y_continuous(labels = percent_format(accuracy = 1), limits = c(0, 1)) +
  ylab('Share of reporter-days with \u22651 oppositional pregunta') +
  xlab('Date') + base_theme

# Before/after bar
p_bar <- df |>
  group_by(period) |>
  summarise(opp_share = mean(opp_day), .groups = 'drop') |>
  ggplot(aes(x = period, y = opp_share,
             fill = period)) +
  geom_col(width = .5) +
  geom_text(aes(label = percent(opp_share, accuracy = .1)),
            vjust = -.4, size = 3.5) +
  scale_x_discrete(labels = c('Pre-lottery' = 'Pre', 'Post-lottery' = 'Post')) +
  scale_y_continuous(labels = percent_format(accuracy = 1),
                     expand = expansion(mult = c(0, .12)), limits = c(0, 1)) +
  scale_fill_manual(values = c('Pre-lottery' = '#4e79a7', 'Post-lottery' = '#f28e2b'),
                    guide = 'none') +
  ylab('Share oppositional reporter-days') + xlab(NULL) +
  base_theme + theme(axis.text.x = element_text(angle = 0, hjust = .5))

ggsave(p_weekly + p_bar + plot_annotation(tag_levels = 'A'),
       filename = paste0(res_dir, 'alignment_trend_weekly.pdf'),
       device = cairo_pdf, width = 14, height = 6, units = 'in')
cat('\nSaved \u2192 alignment_trend_weekly.pdf\n')

# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Histogram: distribution of reporter-days per outlet
# ══════════════════════════════════════════════════════════════════════════════

reporter_counts <- df |> count(reporter_aux, period) |> filter(n>5)

p_dist <- ggplot(reporter_counts, aes(x = n, fill = period, colour = period)) +
  geom_density(alpha = .35, linewidth = .8) +
  scale_fill_manual(values   = c('Pre-lottery' = '#4e79a7', 'Post-lottery' = '#f28e2b'),
                    labels = period_labels) +
  scale_colour_manual(values = c('Pre-lottery' = '#4e79a7', 'Post-lottery' = '#f28e2b'),
                      labels = period_labels) +
  scale_y_continuous(expand = expansion(mult = c(0, .05))) +
  labs(x = 'Days with mic access per reporter', y = 'Density') +
  base_theme +
  theme(axis.text.x = element_text(angle = 0, hjust = .5))

ggsave(p_dist,
       filename = paste0(res_dir, 'reporter_distribution.pdf'),
       device = cairo_pdf, width = 9, height = 5, units = 'in')
cat('Saved \u2192 reporter_distribution.pdf\n')

# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — Top 20 reporters by days with mic access
# ══════════════════════════════════════════════════════════════════════════════

rep_stats <- df |>
  group_by(reporter_aux, period) |>
  summarise(days      = n(),
            opp_share = mean(opp_day),
            .groups = 'drop')

make_access_plot <- function(df_top, id_col, y_lab, title) {
  ggplot(df_top,
         aes(x = reorder(.data[[id_col]], days), y = days, fill = opp_share)) +
    geom_col(width = .7) +
    geom_text(aes(label = days), hjust = -.2, size = 3) +
    coord_flip() +
    scale_fill_gradient(low = 'steelblue', high = 'firebrick',
                        name = '% days oppositional',
                        labels = percent_format(accuracy = 1), limits = c(0, 1)) +
    scale_y_continuous(expand = expansion(mult = c(0, .15))) +
    labs(title = title, x = NULL, y = y_lab) +
    theme_bw() +
    theme(axis.text.y     = element_text(size = 9, colour = 'black'),
          axis.text.x     = element_text(size = 9, colour = 'black'),
          axis.title.x    = element_text(size = 10),
          legend.position = 'bottom',
          plot.title      = element_text(size = 11, face = 'bold'))
}

top20_rep_pre  <- rep_stats |> filter(period == 'Pre-lottery')  |>
  arrange(desc(days)) |> slice_head(n = 20)
top20_rep_post <- rep_stats |> filter(period == 'Post-lottery') |>
  arrange(desc(days)) |> slice_head(n = 20)

ggsave(
  make_access_plot(top20_rep_pre,  'reporter_aux', 'Days with mic access',
                   period_labels['Pre-lottery']) +
  make_access_plot(top20_rep_post, 'reporter_aux', 'Days with mic access',
                   period_labels['Post-lottery']),
  filename = paste0(res_dir, 'reporters_before_after.pdf'),
  device = cairo_pdf, width = 14, height = 9, units = 'in')
cat('Saved \u2192 reporters_before_after.pdf\n')

# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — Top 20 outlets by reporter-days with mic access
# ══════════════════════════════════════════════════════════════════════════════

out_stats <- df |>
  group_by(outlet_aux, period) |>
  summarise(days      = n(),
            opp_share = mean(opp_day),
            .groups = 'drop')

top20_out_pre  <- out_stats |> filter(period == 'Pre-lottery')  |>
  arrange(desc(days)) |> slice_head(n = 20)
top20_out_post <- out_stats |> filter(period == 'Post-lottery') |>
  arrange(desc(days)) |> slice_head(n = 20)

ggsave(
  make_access_plot(top20_out_pre,  'outlet_aux', 'Reporter-days with mic access',
                   period_labels['Pre-lottery']) +
  make_access_plot(top20_out_post, 'outlet_aux', 'Reporter-days with mic access',
                   period_labels['Post-lottery']),
  filename = paste0(res_dir, 'outlets_before_after.pdf'),
  device = cairo_pdf, width = 14, height = 9, units = 'in')
cat('Saved \u2192 outlets_before_after.pdf\n')

# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — Top 20 outlets: oppositional vs aligned days (pre & post)
# ══════════════════════════════════════════════════════════════════════════════

make_count_plot <- function(df_top, fill_colour, title, xlab) {
  ggplot(df_top, aes(x = reorder(outlet_aux, days), y = days)) +
    geom_col(fill = fill_colour, width = .7) +
    geom_text(aes(label = days), hjust = -.2, size = 2.8) +
    coord_flip() +
    scale_y_continuous(expand = expansion(mult = c(0, .15))) +
    labs(title = title, x = NULL, y = xlab) +
    theme_bw() +
    theme(axis.text.y  = element_text(size = 8.5, colour = 'black'),
          axis.text.x  = element_text(size = 8.5, colour = 'black'),
          axis.title.x = element_text(size = 10),
          plot.title   = element_text(size = 10, face = 'bold'))
}

for (per in c('Pre-lottery', 'Post-lottery')) {
  slug      <- if_else(per == 'Pre-lottery', 'pre', 'post')
  per_label <- if_else(per == 'Pre-lottery',
                       'Apr 2021\u2013Apr 2022', 'Apr 2022\u2013Apr 2023')

  opp_aln <- df |>
    filter(period == per) |>
    group_by(outlet_aux) |>
    summarise(opp_days = sum(opp_day),
              aln_days = sum(opp_day == 0),
              .groups = 'drop')

  p_opp <- make_count_plot(
    opp_aln |> arrange(desc(opp_days)) |> slice_head(n = 20) |>
      rename(days = opp_days),
    'firebrick', 'Top 20 — oppositional days', 'Days with \u22651 opp. pregunta')

  p_aln <- make_count_plot(
    opp_aln |> arrange(desc(aln_days)) |> slice_head(n = 20) |>
      rename(days = aln_days),
    'steelblue', 'Top 20 — aligned days', 'Days with 0 opp. preguntas')

  ggsave(
    p_opp + p_aln +
      plot_annotation(
        title      = paste0(per, ' (', per_label, ')'),
        tag_levels = 'A'),
    filename = paste0(res_dir, 'outlets_opp_vs_aligned_', slug, '.pdf'),
    device = cairo_pdf, width = 14, height = 9, units = 'in')
  cat('Saved \u2192 outlets_opp_vs_aligned_', slug, '.pdf\n', sep = '')
}

# ══════════════════════════════════════════════════════════════════════════════
# Section 7 — LaTeX tables
# ══════════════════════════════════════════════════════════════════════════════

# Table 1: overall share of oppositional reporter-days
df |>
  group_by(period) |>
  summarise(`Reporter-days` = n(),
            `Opp. days`     = sum(opp_day),
            `\\% opp.`      = round(mean(opp_day) * 100, 1),
            .groups = 'drop') |>
  rename(Period = period) |>
  write_tex('tab_overall.tex',
            'Share of oppositional reporter-days by period (\\textpm{}1 year window)',
            'tab:overall')

# Table 2: before/after chi-square
tab_ba <- as.data.frame(ct) |>
  rename(Period = Var1, `Opp. day` = Var2, N = Freq) |>
  group_by(Period) |>
  mutate(`\\% share` = round(N / sum(N) * 100, 1)) |>
  ungroup()

chi2_note <- list(
  pos     = list(nrow(tab_ba)),
  command = paste0('\\midrule\n\\multicolumn{4}{l}{\\footnotesize $\\chi^2$ = ',
                   round(chi2$statistic, 2), ', $p$ ',
                   ifelse(chi2$p.value < .001, '< 0.001',
                          paste0('= ', round(chi2$p.value, 3))),
                   '} \\\\\n'))

xt_ba <- xtable(tab_ba,
                caption = 'Reporter-days by opp.\\ day status and period',
                label   = 'tab:before_after')
print(xt_ba, file = paste0(res_dir, 'tab_before_after.tex'),
      include.rownames = FALSE, booktabs = TRUE,
      caption.placement = 'top', comment = FALSE, add.to.row = chi2_note)
cat('Saved \u2192 tab_before_after.tex\n')

# Tables 3–4: top 20 reporters (pre / post)
for (per in c('Pre-lottery', 'Post-lottery')) {
  slug <- if_else(per == 'Pre-lottery', 'pre', 'post')
  rep_stats |>
    filter(period == per) |>
    arrange(desc(days)) |>
    slice_head(n = 20) |>
    mutate(opp_share = round(opp_share * 100, 1)) |>
    select(Reporter = reporter_aux, Days = days,
           `\\% days opp.` = opp_share) |>
    write_tex(paste0('tab_reporters_', slug, '.tex'),
              paste0('Top 20 reporters by mic access (', tolower(per), ')'),
              paste0('tab:reporters_', slug))
}

# Tables 5–6: top 20 outlets by reporter-days (pre / post)
for (per in c('Pre-lottery', 'Post-lottery')) {
  slug <- if_else(per == 'Pre-lottery', 'pre', 'post')
  out_stats |>
    filter(period == per) |>
    arrange(desc(days)) |>
    slice_head(n = 20) |>
    mutate(opp_share = round(opp_share * 100, 1)) |>
    select(Outlet = outlet_aux, `Reporter-days` = days,
           `\\% days opp.` = opp_share) |>
    write_tex(paste0('tab_outlets_', slug, '.tex'),
              paste0('Top 20 outlets by reporter-days (', tolower(per), ')'),
              paste0('tab:outlets_', slug))
}

# Tables 7–10: outlets by opp/aln days (pre & post)
for (per in c('Pre-lottery', 'Post-lottery')) {
  slug <- if_else(per == 'Pre-lottery', 'pre', 'post')
  opp_aln <- df |>
    filter(period == per) |>
    group_by(outlet_aux) |>
    summarise(opp_days = sum(opp_day),
              aln_days = sum(opp_day == 0), .groups = 'drop')

  opp_aln |> arrange(desc(opp_days)) |> slice_head(n = 20) |>
    select(Outlet = outlet_aux, `Opp. days` = opp_days) |>
    write_tex(paste0('tab_outlet_opp_', slug, '.tex'),
              paste0('Top 20 outlets by oppositional days (', tolower(per), ')'),
              paste0('tab:outlet_opp_', slug))

  opp_aln |> arrange(desc(aln_days)) |> slice_head(n = 20) |>
    select(Outlet = outlet_aux, `Aln. days` = aln_days) |>
    write_tex(paste0('tab_outlet_aln_', slug, '.tex'),
              paste0('Top 20 outlets by aligned days (', tolower(per), ')'),
              paste0('tab:outlet_aln_', slug))
}

cat('\nAll outputs saved to:', res_dir, '\n')
