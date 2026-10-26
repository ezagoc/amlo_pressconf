# AMLO and Sheinbaum Press Conference Media Code

## Project status and workflow map

Latest: [panel rebuild and initial Sheinbaum analysis](docs/PANEL_REBUILD_2026-10-26.md).
The finalized mappings have now been propagated through the panels. The new
[participation workflow](code/08-results/03-sheinbaum-participation/README.md)
adds outlet/date summaries using explicit transcript identities and attendance.

The [October 26, 2026 project recap](docs/PROJECT_STATUS_2026-10-26.md)
records completed extraction and outlet reconciliation, dataset definitions,
validation, and pending work. The current Sheinbaum archive contains 503
conferences through October 15, 2026; later dates have not been collected.

- [Sheinbaum preprocessing](code/03-cleaning_conf/question_class/sheinbaum/README.md): official transcripts, journalist/outlet extraction, and manual harmonization.
- [Speaker and question–answer pilot](code/03-cleaning_conf/question_class/sheinbaum/transcript_pilot/README.md): text units, linking, and alignment review.
- [AMLO official archive](code/03-cleaning_conf/official_amlo/README.md): scraping, source comparison, and remaining date gaps.
- [Outlet migration scripts](scripts/README.md): dated reconciliation tools and local input requirements.
- `code/07-final_panel/`: panel assembly, descriptive statistics, and earlier estimation workflows.
- [Effect-of-asking handoff](code/08-results/01-effect-of-asking/HANDOFF.md): current YouTube specifications and run status.
- [Balance specifications](code/08-results/balance/BALANCE_TESTING_SPEC_DRAFT.md) and [variable dictionary](code/08-results/balance/VARIABLE_DICTIONARY.md).

Code, reviewed alias/evidence tables, and selected publication figures/tables
are versioned here. Raw transcripts, model checkpoints, bulk datasets, and
local recovery backups are not. Panels reflect the latest outlet changes;
historical model estimates have not been re-estimated.

This repository is for code, notes, and reproducible workflows. The media data
stays in Dropbox. Configure the path for the current machine, for example:

```text
C:\Users\Dell\Dropbox\Media
/Users/ezagoc/Dropbox/Media
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

## AMLO Tracking Poll approval series

The approval data workflow is documented in
[`code/06-outcomes/approval_tracking/README.md`](code/06-outcomes/approval_tracking/README.md).
Its code is tracked here; frozen inputs, evidence images, and generated output
are in `MEDIA_ROOT/data/06-outcomes/approval_tracking/`.
