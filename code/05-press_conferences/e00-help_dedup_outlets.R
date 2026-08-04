library(tidyverse)
library(arrow)
library(stringi)
library(stringr)
library(stringdist)
library(readxl)
library(writexl)

rm(list = ls())
rstudioapi::getActiveDocumentContext
setwd(dirname(rstudioapi::getActiveDocumentContext()$path))
source("../../project_paths.R")

# ── 0. Load data (same as preprocessing script) ────────────────────────────────

outlets <- read_excel(media_path('data', '02-conferences', 'raw', 'attendance', 'merged', 'bridge_outlets.xlsx'))


# ── 1. Unique outlet names (weighted by frequency) ─────────────────────────────

unique_names <- outlets$outlet_final
n <- length(unique_names)

cat("Total unique outlet_clean values:", n, "\n")

# ── 2. Pairwise similarity matrix (Jaro-Winkler) ───────────────────────────────
# Jaro-Winkler is well-suited for proper-noun name matching.
# stringdist returns a *distance* (0 = identical, 1 = totally different).
# We convert to similarity: sim = 1 - dist.

cat("Computing pairwise distances (this may take a moment for large n)...\n")
dist_matrix <- stringdistmatrix(unique_names, unique_names, method = "jw", p = 0.1)
sim_matrix  <- 1 - dist_matrix

# ── 3. Extract pairs ────────────────────────────────────────────────────────────

# Keep only upper triangle (avoid self-pairs and duplicates)
pairs <- which(upper.tri(sim_matrix), arr.ind = TRUE) %>%
  as.data.frame() %>%
  rename(i = row, j = col) %>%
  mutate(
    name_a   = unique_names[i],
    name_b   = unique_names[j],
    freq_a   = outlets$n[i],
    freq_b   = outlets$n[j],
    sim      = sim_matrix[cbind(i, j)]
  ) %>%
  select(name_a, name_b, freq_a, freq_b, sim) %>%
  arrange(desc(sim))

# ── 4. Split by threshold ───────────────────────────────────────────────────────

HIGH_THRESHOLD  <- 0.99   # auto-accept
LOW_THRESHOLD   <- 0.60   # lower bound for manual review

auto_pairs   <- pairs %>% filter(sim >= HIGH_THRESHOLD)
review_pairs <- pairs %>% filter(sim >= LOW_THRESHOLD & sim < HIGH_THRESHOLD)

cat("Pairs auto-merged  (sim >= 90%):", nrow(auto_pairs), "\n")
cat("Pairs for review (60–90%)      :", nrow(review_pairs), "\n")

# ── 5. Build canonical name mapping (auto pairs) ───────────────────────────────
# Strategy: within each cluster of highly-similar names, pick the one with the
# highest frequency as the canonical form.

# Union-Find helper to cluster names
find_clusters <- function(pairs_df, all_names) {
  parent <- setNames(seq_along(all_names), all_names)

  find <- function(x) {
    while (parent[x] != x) {
      parent[x] <<- parent[parent[x]]
      x <- parent[x]
    }
    x
  }

  union <- function(a, b) {
    ra <- find(a); rb <- find(b)
    if (ra != rb) parent[ra] <<- rb
  }

  for (k in seq_len(nrow(pairs_df))) {
    union(pairs_df$name_a[k], pairs_df$name_b[k])
  }

  # Assign cluster id = root name
  tibble(outlet_final = all_names) %>%
    mutate(cluster = map_chr(outlet_final, find))
}

clusters <- find_clusters(auto_pairs, unique_names)

# Join frequency info and pick the highest-frequency name per cluster
freq_lookup <- setNames(outlets$n, outlets$outlet_final)

canonical_map <- clusters %>%
  mutate(freq = freq_lookup[outlet_final]) %>%
  group_by(cluster) %>%
  mutate(canonical = outlet_final[which.max(freq)]) %>%
  ungroup() %>%
  select(outlet_final, canonical)

# ── 6. Apply mapping to df ──────────────────────────────────────────────────────

outlets <- outlets %>%
  left_join(canonical_map, by = "outlet_final") %>%
  mutate(outlet_dedup = coalesce(canonical, outlet_final)) %>%
  select(-canonical)

cat("\nSample of changes made (auto-dedup):\n")
outlets %>%
  filter(outlet_final != outlet_dedup) %>%
  distinct(outlet_final, outlet_dedup) %>%
  arrange(outlet_dedup) %>%
  print(n = 30)

# ── 7. Export review sheet ──────────────────────────────────────────────────────
# Add a blank column so the reviewer can type the chosen canonical name.

review_sheet <- review_pairs %>%
  mutate(
    sim_pct        = scales::percent(sim, accuracy = 0.1),
    chosen_canonical = ""   # reviewer fills this in
  ) %>% 
  arrange(desc(sim))

review_sheet <- review_sheet |> group_by(name_a) |> slice_max(sim_pct, n=1, 
                                                                    with_ties = T) |>
  arrange(desc(sim)) |>
  ungroup()

write_xlsx(
  list(
    auto_merged  = auto_pairs  %>% mutate(sim_pct = scales::percent(sim, accuracy = 0.1)),
    manual_review = review_sheet
  ),
  path = media_output_path('data', '02-conferences', 'raw', 'attendance', 'merged', 'outlet_dedup_review.xlsx')
)

cat("\nReview file written to: outlet_dedup_review.xlsx\n")

# ── 8. (Optional) Apply manual corrections after review ────────────────────────
# After you fill in `chosen_canonical` in the Excel sheet, re-run from here:

apply_manual_corrections <- function(df_in, review_file = "outlet_dedup_review.xlsx") {
  manual <- read_excel(review_file, sheet = "manual_review") %>%
    filter(!is.na(chosen_canonical) & chosen_canonical != "") %>%
    select(name_a, name_b, chosen_canonical)

  # Build a name -> canonical lookup from manual decisions
  manual_map <- bind_rows(
    manual %>% select(outlet_clean = name_a, canonical = chosen_canonical),
    manual %>% select(outlet_clean = name_b, canonical = chosen_canonical)
  ) %>%
    distinct(outlet_clean, .keep_all = TRUE)

  df_in %>%
    left_join(manual_map, by = c("outlet_dedup" = "outlet_clean")) %>%
    mutate(outlet_dedup = coalesce(canonical, outlet_dedup)) %>%
    select(-canonical)
}

# Uncomment after filling the review sheet:
# df <- apply_manual_corrections(df)

# ── 9. Final counts ─────────────────────────────────────────────────────────────

cat("\nOriginal unique outlets:", n_distinct(df$outlet_clean), "\n")
cat("After auto-dedup        :", n_distinct(df$outlet_dedup),  "\n")

# Save deduplicated data
# write_parquet(df, media_output_path('data', '02-conferences', 'processed', 'attendance_dedup.parquet'))
# write_xlsx(df, media_output_path('data', '02-conferences', 'processed', 'attendance_dedup.xlsx'))
