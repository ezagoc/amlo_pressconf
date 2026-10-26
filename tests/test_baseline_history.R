# Synthetic checks: no source writes, no regression estimation.
suppressPackageStartupMessages({library(dplyr); library(tidyr)})
source("src/baseline_history.R")
cutoff <- as.Date("2022-04-18")
w <- baseline_windows(cutoff)
stopifnot(w$from[w$window=="year1"]==as.Date("2018-12-01"),
          w$to[w$window=="year1"]==as.Date("2019-11-30"),
          w$from[w$window=="last_year"]==as.Date("2021-04-18"),
          w$from[w$window=="last_2years"]==as.Date("2020-04-18"), all(w$to < cutoff))
days <- crossing(metadata_id=1:3, date=as.Date(c("2021-11-01","2022-04-15","2022-04-16","2022-04-17"))) |>
  mutate(attendance_matched=metadata_id!=2, questions_matched=metadata_id!=2,
    attendance_observed=TRUE, questions_observed=date!=as.Date("2022-04-17"),
    attendance_recorded=if_else(date==as.Date("2022-04-15"),2,0),
    attendance_assumed=0,
    questions=if_else(metadata_id==1,3,0))
prepared <- prepare_baseline_days(days)
stopifnot(all(!prepared$attendance_observed[format(prepared$date,"%Y-%m")=="2021-11"]),
          all(is.na(prepared$attendance_recorded[prepared$metadata_id==2])),
          prepared$attendance_corrected[prepared$metadata_id==1 & prepared$date==as.Date("2022-04-16")]==1)
out <- summarise_baseline_history(prepared,w,cutoff) |> filter(window=="total")
# Outlet 1: three questions per observed day, not binary question-day counts.
stopifnot(out$questions[out$metadata_id==1]==9,
          out$attendance[out$metadata_id==1]==2,
          out$questions_per_attendance[out$metadata_id==1]==6/3,
          out$question_day_share[out$metadata_id==1]==1,
          is.na(out$questions[out$metadata_id==2]),
          out$attendance_observed_days[out$metadata_id==2]==0,
          out$questions[out$metadata_id==3]==0)
stopifnot(is.na(history_ratio(0,0)), is.na(history_sum(numeric())))
future <- bind_rows(prepared,mutate(prepared[1,],date=cutoff))
stopifnot(inherits(try(summarise_baseline_history(future,w,cutoff),silent=TRUE),'try-error'))
cat("Baseline history tests passed.\n")

# Contracts: observed zeros, absent coverage, November inclusion and shared IDs.
contracts <- crossing(contracts_entity_id=c("company_a","company_b","unmatched"),
                      date=as.Date(c("2021-11-01","2022-04-17"))) |>
  mutate(source_entity_matched=contracts_entity_id!="unmatched", source_date_observed=TRUE,
    contracts_costo=if_else(contracts_entity_id=="company_a",100,0),
    contracts_importe=if_else(contracts_entity_id=="company_a",80,0),
    contracts_received_n=if_else(contracts_entity_id=="company_a",1,0),
    contracts_n=if_else(contracts_entity_id=="company_a",3,0))
ct <- summarise_contract_history(contracts,w,cutoff) |> filter(window=="total")
stopifnot(ct$contracts_costo[ct$contracts_entity_id=="company_a"]==200,
          ct$contracts_importe[ct$contracts_entity_id=="company_a"]==160,
          ct$contracts_received_n[ct$contracts_entity_id=="company_a"]==2,
          ct$contracts_n[ct$contracts_entity_id=="company_a"]==6,
          ct$contracts_award_days[ct$contracts_entity_id=="company_a"]==2,
          ct$contracts_costo[ct$contracts_entity_id=="company_b"]==0,
          is.na(ct$contracts_costo[ct$contracts_entity_id=="unmatched"]),
          ct$contracts_observed_days[ct$contracts_entity_id=="unmatched"]==0)
shared <- tibble(metadata_id=1:2,contracts_entity_id="company_a") |>
  left_join(ct,by="contracts_entity_id",relationship="many-to-one")
stopifnot(nrow(shared)==2, all(shared$contracts_costo==200))
future_contracts <- bind_rows(contracts,mutate(contracts[1,],date=cutoff))
stopifnot(inherits(try(summarise_contract_history(future_contracts,w,cutoff),silent=TRUE),'try-error'),
          inherits(try(summarise_contract_history(bind_rows(contracts,contracts[1,]),w,cutoff),silent=TRUE),'try-error'))
cat("Contract history tests passed.\n")
