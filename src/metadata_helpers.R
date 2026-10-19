normalize_outlet_name <- function(x) {
  key <- x |>
    stringr::str_to_lower() |>
    stringi::stri_trans_general("Latin-ASCII") |>
    stringr::str_squish()

  dplyr::recode(
    key,
    "sintesis pueba" = "sintesis puebla",
    "latitudes press" = "latitude press",
    "diario de yucatan" = "el diario de yucatan"
  )
}

merge_newspaper_metadata <- function(meta, news) {
  add_keys <- function(df) {
    df |>
      dplyr::mutate(.name_key = normalize_outlet_name(.data$name.page)) |>
      dplyr::group_by(.data$.name_key) |>
      dplyr::mutate(.name_instance = dplyr::row_number()) |>
      dplyr::ungroup()
  }

  meta_keyed <- add_keys(meta)
  news_keyed <- add_keys(news)
  repeated <- intersect(names(meta), names(news))

  news_only <- news_keyed |>
    dplyr::select(-dplyr::any_of(repeated)) |>
    dplyr::select(-dplyr::matches("^\\.\\.\\.[0-9]+$"))

  meta_keyed |>
    dplyr::left_join(
      news_only,
      by = c(".name_key", ".name_instance"),
      relationship = "one-to-one"
    ) |>
    dplyr::select(-".name_key", -".name_instance") |>
    dplyr::mutate(metadata_id = dplyr::row_number(), .before = 1)
}

# Reviewed source-ID corrections. Keep workbook data untouched; apply these
# after merging so regenerated panels use the same IDs as the source cleaners.
apply_reviewed_conference_keys <- function(metadata) {
  name <- normalize_outlet_name(metadata$name.page)
  reporteros <- name %in% c("los reporteros mx", "el quintana roo mx")
  metadata$names.conference[reporteros] <- "reporteros mx"
  metadata$names.transcripts[reporteros] <- "losreporterosmx"
  grupo_sol <- name %in% "grupo sol campeche"
  metadata$names.conference[grupo_sol] <- "grupo sol"
  metadata$names.transcripts[grupo_sol] <- "grupo sol"
  metadata
}

add_metadata_dummies <- function(metadata) {
  clean_text <- function(x) {
    x |>
      tidyr::replace_na("") |>
      stringr::str_to_lower() |>
      stringi::stri_trans_general("Latin-ASCII")
  }
  dummy <- function(x, pattern) {
    as.integer(stringr::str_detect(clean_text(x), pattern))
  }
  category_dummy <- function(x, category, missing = "unclear") {
    value <- clean_text(x)
    value[value == ""] <- missing
    as.integer(value == category)
  }

  metadata |>
    dplyr::mutate(
      # Coverage can contain several labels, so these indicators may overlap.
      coverage_national = dummy(.data$coverage.scope, "national"),
      coverage_state = dummy(.data$coverage.scope, "state"),
      coverage_regional = dummy(.data$coverage.scope, "regional"),
      coverage_international = dummy(.data$coverage.scope, "international"),
      coverage_multistate = dummy(.data$coverage.scope, "multistate"),
      coverage_metropolitan = dummy(.data$coverage.scope, "metropolitan"),
      coverage_municipal = dummy(.data$coverage.scope, "municipal"),
      coverage_local = dummy(.data$coverage.scope, "local"),
      coverage_community = dummy(.data$coverage.scope, "community"),
      coverage_city = dummy(.data$coverage.scope, "(^|[/, ]+)city($|[/, ]+)"),
      coverage_unclear = as.integer(is.na(.data$coverage.scope)),

      # Missing owner ideology is explicitly coded as unclear.
      owner_ideology_left = category_dummy(.data$owner.ideology, "left"),
      owner_ideology_right = category_dummy(.data$owner.ideology, "right"),
      owner_ideology_unclear = category_dummy(.data$owner.ideology, "unclear"),

      ideology_left = category_dummy(.data$ideology.leftright, "left"),
      ideology_center = category_dummy(.data$ideology.leftright, "center"),
      ideology_center_right = category_dummy(
        .data$ideology.leftright,
        "center-right"
      ),
      ideology_right = category_dummy(.data$ideology.leftright, "right"),
      ideology_unclear = category_dummy(.data$ideology.leftright, "unclear"),

      ideology_4t_aligned = category_dummy(.data$ideology.4t, "aligned"),
      ideology_4t_opposition = category_dummy(.data$ideology.4t, "opp"),
      ideology_4t_unclear = category_dummy(.data$ideology.4t, "unclear"),

      # Media formats are also multi-label and may overlap.
      media_periodico = dummy(.data$type.media, "periodico|newspaper"),
      media_social_media = dummy(.data$type.media, "social media|facebook"),
      media_digital = dummy(.data$type.media, "digital"),
      media_print = dummy(.data$type.media, "periodico|newspaper|print|semanario"),
      media_radio = dummy(.data$type.media, "radio"),
      media_television = dummy(.data$type.media, "television"),
      media_video = dummy(.data$type.media, "video|audio-video"),
      media_magazine = dummy(.data$type.media, "revista|magazine"),
      media_news_agency = dummy(.data$type.media, "news agency"),
      media_podcast = dummy(.data$type.media, "podcast"),
      media_network = dummy(.data$type.media, "network"),
      media_personal = dummy(.data$type.media, "personal|individual"),
      media_unverified = as.integer(
        dummy(.data$type.media, "unverified") == 1L | is.na(.data$type.media)
      )
    )
}

make_nominatim_query <- function(address) {
  purrr::map_chr(address, function(x) {
    if (is.na(x) || !nzchar(stringr::str_squish(x))) return(NA_character_)
    parts <- stringr::str_split(x, ",")[[1]] |>
      stringr::str_squish()
    parts <- parts[nzchar(parts)]
    paste(unique(c(parts[[1]], utils::tail(parts, 2), "Mexico")), collapse = ", ")
  })
}

geocode_nominatim <- function(
    queries,
    cache_file,
    user_agent = Sys.getenv(
      "NOMINATIM_USER_AGENT",
      unset = "amlo_pressconf-research/1.0 (https://github.com/ezagoc/amlo_pressconf)"
    ),
    delay = 1.1) {
  queries <- unique(stats::na.omit(queries))
  schema <- readr::cols(
    geocode_query = readr::col_character(),
    office_latitude = readr::col_double(),
    office_longitude = readr::col_double(),
    geocode_display_name = readr::col_character(),
    geocode_status = readr::col_character()
  )
  cache <- if (file.exists(cache_file)) {
    readr::read_csv(cache_file, col_types = schema) |>
      dplyr::filter(.data$geocode_query %in% queries)
  } else {
    tibble::tibble(
      geocode_query = character(),
      office_latitude = double(),
      office_longitude = double(),
      geocode_display_name = character(),
      geocode_status = character()
    )
  }

  missing <- setdiff(queries, cache$geocode_query)
  for (i in seq_along(missing)) {
    if (i > 1L) Sys.sleep(delay)
    query <- missing[[i]]
    response <- tryCatch(
      httr::GET(
        "https://nominatim.openstreetmap.org/search",
        query = list(
          q = query,
          format = "jsonv2",
          limit = 1,
          addressdetails = 1,
          countrycodes = "mx"
        ),
        httr::user_agent(user_agent),
        httr::timeout(30)
      ),
      error = identity
    )

    result <- if (inherits(response, "error") || httr::http_error(response)) {
      tibble::tibble(
        geocode_query = query,
        office_latitude = NA_real_,
        office_longitude = NA_real_,
        geocode_display_name = NA_character_,
        geocode_status = if (inherits(response, "error")) {
          conditionMessage(response)
        } else {
          paste("HTTP", httr::status_code(response))
        }
      )
    } else {
      place <- httr::content(response, as = "parsed", type = "application/json")
      if (length(place) == 0L) {
        tibble::tibble(
          geocode_query = query,
          office_latitude = NA_real_,
          office_longitude = NA_real_,
          geocode_display_name = NA_character_,
          geocode_status = "no_match"
        )
      } else {
        tibble::tibble(
          geocode_query = query,
          office_latitude = as.numeric(place[[1]]$lat),
          office_longitude = as.numeric(place[[1]]$lon),
          geocode_display_name = place[[1]]$display_name,
          geocode_status = "matched"
        )
      }
    }

    cache <- dplyr::bind_rows(cache, result) |>
      dplyr::distinct(.data$geocode_query, .keep_all = TRUE)
    readr::write_csv(cache, cache_file, na = "")
  }

  cache
}

haversine_km <- function(lat1, lon1, lat2, lon2) {
  radians <- pi / 180
  lat1 <- lat1 * radians
  lon1 <- lon1 * radians
  lat2 <- lat2 * radians
  lon2 <- lon2 * radians
  a <- sin((lat2 - lat1) / 2)^2 +
    cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2)^2
  2 * 6371.0088 * asin(pmin(1, sqrt(a)))
}

add_office_geocodes <- function(
    metadata,
    cache_file,
    destination_latitude = 19.432937370008197,
    destination_longitude = -99.13134237514555) {
  metadata <- metadata |>
    dplyr::mutate(geocode_query = make_nominatim_query(.data$address))
  geocodes <- geocode_nominatim(metadata$geocode_query, cache_file)

  metadata |>
    dplyr::left_join(geocodes, by = "geocode_query", relationship = "many-to-one") |>
    dplyr::mutate(
      distance_palacio_nacional_km = haversine_km(
        .data$office_latitude,
        .data$office_longitude,
        destination_latitude,
        destination_longitude
      ),
      geocode_attribution = dplyr::if_else(
        !is.na(.data$office_latitude),
        "OpenStreetMap contributors, ODbL; geocoded with Nominatim",
        NA_character_
      )
    )
}
