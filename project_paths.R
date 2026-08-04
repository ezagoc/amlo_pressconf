load_project_env <- function() {
  env_file <- file.path(dirname(normalizePath(sys.frame(1)$ofile %||% getwd(), winslash = "/", mustWork = FALSE)), ".env")
  if (!file.exists(env_file)) {
    env_file <- file.path(getwd(), ".env")
  }
  if (!file.exists(env_file)) {
    return(invisible(NULL))
  }

  lines <- readLines(env_file, warn = FALSE)
  for (line in trimws(lines)) {
    if (!nzchar(line) || startsWith(line, "#") || !grepl("=", line, fixed = TRUE)) {
      next
    }
    key <- trimws(sub("=.*$", "", line))
    value <- trimws(sub("^[^=]*=", "", line))
    value <- gsub("^[\"']|[\"']$", "", value)
    if (!nzchar(Sys.getenv(key))) {
      do.call(Sys.setenv, as.list(stats::setNames(value, key)))
    }
  }

  invisible(env_file)
}

`%||%` <- function(x, y) if (is.null(x)) y else x

load_project_env()

media_root <- function() {
  root <- Sys.getenv("MEDIA_ROOT", unset = "C:/Users/Dell/Dropbox/Media")
  normalizePath(root, winslash = "/", mustWork = FALSE)
}

media_path <- function(...) {
  parts <- c(...)
  if (any(grepl("^([A-Za-z]:|/|\\\\)", parts))) {
    stop("Media paths must be relative to MEDIA_ROOT.", call. = FALSE)
  }
  file.path(media_root(), ...)
}

media_output_path <- function(...) {
  path <- media_path(...)
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  path
}
