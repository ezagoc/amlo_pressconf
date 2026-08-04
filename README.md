# AMLO Press Conference Media Code

This repository is for code, notes, and reproducible workflows. The media data itself stays in Dropbox at:

```text
C:\Users\Dell\Dropbox\Media
```

The working rule is: code lives in this Git repository, while inputs and outputs continue to use the same folder structure under `MEDIA_ROOT`.

## Local Environment

This repo uses a local `.env` file:

```text
MEDIA_ROOT=C:\Users\Dell\Dropbox\Media
YOUTUBE_API_KEYS=
OPENAI_API_KEY=
```

`.env` is ignored by Git so the machine-specific path does not get committed. A template is kept in `.env.example`.

Install Python dependencies with:

```powershell
pip install -r requirements.txt
```

## Path Convention

Use `project_paths.py` in scripts copied into this repo:

```python
from project_paths import media_path, media_input_path, media_output_path

source = media_input_path("some", "existing", "folder", "file.csv")
target = media_output_path("some", "existing", "folder", "cleaned_file.csv")
```

Both helpers resolve paths under `MEDIA_ROOT`, so the same relative folder structure is preserved in Dropbox. `media_output_path(...)` also creates the parent folder automatically.

For one-off paths, use:

```python
from project_paths import media_path

folder = media_path("subfolder", "nested-folder")
```

R scripts use the same convention via `project_paths.R`:

```r
source("../../project_paths.R")

input_file <- media_path("data", "folder", "input.csv")
output_file <- media_output_path("data", "folder", "output.csv")
```

## Suggested Workflow

1. Copy code files from `C:\Users\Dell\Dropbox\Media` into this repository.
2. Replace hard-coded Dropbox paths with `media_path(...)`, `media_input_path(...)`, or `media_output_path(...)`.
3. Keep generated data, large raw files, and exports in Dropbox under `MEDIA_ROOT`.
4. Commit only code, documentation, and lightweight project metadata here.

## Presentations

The existing `presentations/` folder contains project PDFs that are small enough to keep with the repo unless you decide to move them into Dropbox later.
