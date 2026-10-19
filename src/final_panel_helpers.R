normalize_panel_key <- function(x) {
  key <- x |>
    stringr::str_to_lower() |>
    stringi::stri_trans_general("Latin-ASCII") |>
    stringr::str_replace_all("[^a-z0-9]+", " ") |>
    stringr::str_squish() |>
    dplyr::na_if("")

  dplyr::recode(
    key,
    "sdpnoticias" = "sdp noticias",
    "unomasuno" = "uno mas uno",
    "tiempo la noticial digital" = "tiempo la noticia digital"
  )
}

# Source files retain raw affiliations for the transcript-to-clean-name bridge.
# After aliases collapse, count each canonical outlet/reporter/item only once.
deduplicate_canonical_question_items <- function(data, outlet_column) {
  key <- c(outlet_column, "date", "reporter_aux", "turn_index",
           "item_index", "item_type", "text")
  stopifnot(all(key %in% names(data)))
  data[!duplicated(data[key]), , drop = FALSE]
}

# Apply the COMSOC beneficiary cleaner to both contracts and the registry.
clean_contract_key <- function(x) {
  key <- x |>
    stringr::str_to_lower() |>
    stringi::stri_trans_general("Latin-ASCII") |>
    stringr::str_remove_all("[[:punct:]]") |>
    stringr::str_squish()

  key <- dplyr::case_when(
    stringr::str_detect(key, "grupo formula|radio formula|teleformula|informula") ~ "formula",
    stringr::str_detect(key, "grupo expansion|5m2|expansion sa") ~ "expansion",
    stringr::str_detect(key, "tv azteca|operadora mexicana") ~ "azteca",
    stringr::str_detect(key, "milenio diario|diario milenio|agencia digital|editorial milenio") ~ "milenio",
    stringr::str_detect(key, "medios del caribe") ~ "demos caribe",
    TRUE ~ key
  )

  key <- key |>
    stringr::str_remove_all(
      "\\b(s\\.?a\\.?\\s*de\\s*c\\.?v\\.?|s\\.?a\\.?|s\\.?\\s*de\\s*r\\.?l\\.?\\s*de\\s*c\\.?v\\.?|s\\.?\\s*de\\s*r\\.?l\\.?|s\\.?\\s*c\\.?|a\\.?c\\.?)\\b"
    ) |>
    stringr::str_remove_all(
      "\\b(periodicos?|diarios?|editorial|revistas?|grupo|medios?|comunicacion|noticias|informativo|informativa|online|television|tv|radio|canal)\\b"
    ) |>
    stringr::str_squish()

  key <- dplyr::case_when(
    stringr::str_detect(key, "proabri") ~ "quinto poder",
    stringr::str_detect(key, "debate") ~ "debate",
    stringr::str_detect(key, "sistema de tabasco") ~ "diario presente",
    stringr::str_detect(key, "ofem|estrictamente|difusion de info|libertad") ~ "eje central",
    stringr::str_detect(key, "hojas") ~ "el chapucero",
    stringr::str_detect(key, "financiero|lauman") ~ "el financiero",
    stringr::str_detect(key, "voz del istmo") ~ "voz del istmo",
    stringr::str_detect(key, "editora offset") ~ "noticias de queretaro",
    stringr::str_detect(key, "yucateca") ~ "diario de yucatan",
    stringr::str_detect(key, "sistema periodistico de sinaloa") ~ "noroeste",
    stringr::str_detect(key, "editora de la laguna") ~ "el siglo de torreon",
    stringr::str_detect(key, "excelsior|gim compania") ~ "excelsior",
    stringr::str_detect(key, "contrareplica") ~ "contrareplica",
    stringr::str_detect(key, "nrm") ~ "nrm comunicaciones",
    stringr::str_detect(key, "economista|especializado en economia") ~ "el economista",
    stringr::str_detect(key, "masivos mexicanos") ~ "medios masivos mexicanos",
    stringr::str_detect(key, "demos|al fin verde") ~ "la jornada demos",
    stringr::str_detect(key, "sendero") ~ "sdp noticias",
    stringr::str_detect(key, "angulo 7") ~ "angulo 7",
    stringr::str_detect(key, "imagen comercial|gim nacional") ~ "imagen",
    stringr::str_detect(key, "comunitarias de mexico|comunitarias demexico") ~ "amarc",
    stringr::str_detect(key, "televisa") ~ "televisa",
    stringr::str_detect(key, "el universal") ~ "el universal",
    stringr::str_detect(key, "lrhg") ~ "la razon mexico",
    stringr::str_detect(key, "canton|acuario|campeche hoy|prosperidad") ~ "grupo canton",
    stringr::str_detect(key, "informacion integral") ~ "diario 24 horas",
    stringr::str_detect(key, "imparcial") ~ "grupo healy",
    stringr::str_detect(key, "stereorey|mvs") ~ "mvs noticias",
    stringr::str_detect(key, "publimetro") ~ "publimetro",
    stringr::str_detect(key, "mayann") ~ "mayann",
    stringr::str_detect(key, "reforma|editora el sol") ~ "reforma",
    stringr::str_detect(key, "cifo multimedios") ~ "cifo",
    stringr::str_detect(key, "multimedios oro") ~ "grupo oro",
    stringr::str_detect(
      key,
      "sipse|novedades de quintana|novedades del sureste|novedades de campeche|novedades de merida"
    ) ~ "sipse",
    TRUE ~ key
  )

  normalize_panel_key(key)
}

youtube_url_token <- function(x) {
  purrr::map_chr(x, function(value) {
    if (is.na(value) || !nzchar(stringr::str_squish(value))) return(NA_character_)
    value <- utils::URLdecode(value) |>
      stringr::str_to_lower() |>
      stringi::stri_trans_general("Latin-ASCII") |>
      stringr::str_remove("[?#].*$") |>
      stringr::str_remove("/+$")
    token <- stringr::str_extract(value, "[^/]+$") |>
      stringr::str_remove("^@") |>
      stringr::str_replace_all("[^a-z0-9_-]+", "")
    dplyr::na_if(token, "")
  })
}

collapse_unique <- function(x) {
  values <- sort(unique(x[!is.na(x) & nzchar(x)]))
  if (length(values) == 0L) NA_character_ else paste(values, collapse = " | ")
}

make_match_report <- function(source, keys, registry_map) {
  tibble::tibble(source = source, source_key = keys) |>
    dplyr::filter(!is.na(.data$source_key)) |>
    dplyr::count(.data$source, .data$source_key, name = "source_rows") |>
    dplyr::left_join(
      registry_map |>
        dplyr::filter(!is.na(.data$source_key)) |>
        dplyr::count(.data$source_key, name = "matched_metadata_rows"),
      by = "source_key"
    ) |>
    dplyr::mutate(
      matched_metadata_rows = tidyr::replace_na(.data$matched_metadata_rows, 0L),
      matched = .data$matched_metadata_rows > 0L
    )
}

assert_unique_panel_key <- function(df, label) {
  if (anyDuplicated(df[c("metadata_id", "date")])) {
    stop(label, " has duplicated metadata_id-date rows.", call. = FALSE)
  }
  invisible(df)
}
