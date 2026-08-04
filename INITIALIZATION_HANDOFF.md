# Initialization Handoff

This repo contains code only. Data, generated outputs, checkpoints, figures, and large artifacts should stay under the Dropbox Media tree configured by `MEDIA_ROOT`.

## Local Setup

1. Copy `.env.example` to `.env`.
2. Set `MEDIA_ROOT` to the local Dropbox Media folder for this machine.

Examples:

```text
MEDIA_ROOT=C:\Users\Dell\Dropbox\Media
MEDIA_ROOT=D:\Dropbox\Media
MEDIA_ROOT=/Users/name/Dropbox/Media
```

3. Add API secrets only in `.env` or the shell environment:

```text
OPENAI_API_KEY=
YOUTUBE_API_KEYS=
```

`YOUTUBE_API_KEYS` can contain one key or multiple keys separated by commas.

## Path Convention

Python scripts should use:

```python
from project_paths import media_path, media_input_path, media_output_path
```

R scripts should use the correct relative source path to the repo helper, for example:

```r
source("../../project_paths.R")
```

Then build paths with:

```r
media_path("data", "folder", "input.csv")
media_output_path("data", "folder", "output.csv")
```

Do not hardcode `C:\Users\Dell\Dropbox\Media` inside scripts.

## Current State

- Root `.env.example`, `.gitignore`, `README.md`, `requirements.txt`, `project_paths.py`, and `project_paths.R` are in place.
- Python/R/Rmd source files have been migrated away from hardcoded Dropbox paths where found.
- Notebooks may still contain old paths in saved cells and outputs; treat them as exploratory unless separately cleaned.
- Python files passed syntax compilation with the bundled Python runtime.
- R was not parse-tested here because `Rscript` was not available on PATH.
