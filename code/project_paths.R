load_project_env <- function() {
  roots <- unique(c(normalizePath(getwd(), winslash = "/", mustWork = FALSE), dirname(normalizePath(getwd(), winslash = "/", mustWork = FALSE))))

  script_args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", script_args, value = TRUE)
  if (length(file_arg) > 0) {
    script_dir <- dirname(normalizePath(sub("^--file=", "", file_arg[[1]]), winslash = "/", mustWork = FALSE))
    roots <- unique(c(script_dir, dirname(script_dir), dirname(dirname(script_dir)), dirname(dirname(dirname(script_dir))), roots))
  }

  for (root in roots) {
    env_file <- file.path(root, ".env")
    if (!file.exists(env_file)) {
      next
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
    return(invisible(env_file))
  }

  invisible(NULL)
}

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
