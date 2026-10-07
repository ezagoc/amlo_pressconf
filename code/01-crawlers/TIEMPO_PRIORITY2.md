# Tiempo quality rules after Eduardo's feedback

Author: Kevin. Prepared October 6–7, 2026.

This is a technical follow-up to the frozen 2,670-request interim delivery. It
is not final article acceptance, full newspaper coverage, a new collection
campaign, or permission to overwrite historical reviews. The stopped runtime
checkout and original halt remain preserved. Repairs live on the isolated
`kevin/tiempo-quality-rules-20261006` branch, based on Kevin's pilot branch with
current main integrated. Do not deploy this branch into an old frozen campaign.

## Missing titles

Inspect the current article's visible heading and scoped title metadata before
calling an empty title an extraction defect. If the source heading is empty,
keep `title` null; never use a URL slug or directory title to manufacture it.
Store directory candidates separately with their exact source references.
A systematic absence merits a code/source audit; a high percentage alone does
not establish a code bug. In the frozen 592 missing-title responses, the
independent channel scan found no informative current-page title to recover.
This finding is bounded to the saved responses, not every current/historical
version of the website. Metadata-only titles on a future layout remain an
explicit discrepancy for investigation, not an automatic replacement heading.

Keep usable body text available even when the title is absent. Missing title
alone is not a reason to discard a genuine article or require individual human
approval of every unread record. Preserve original technical error and review
states; they describe different things from availability for body-text work.

## Discovery, deduplication and article units

Discover candidate article URLs first; normalize and deduplicate requested URLs,
validate expected hosts/routes and separate unsupported/query routes before
fetching. Exact request-URL deduplication already precedes extraction. Do not
strip meaningful query strings or guess that two different slugs are equivalent.
Standalone X/Twitter URLs are outside Tiempo article scope and excluded before
extraction. Preserve the discovery provenance and rejected/conflict queue.

After extraction, retain canonical aliases and identical-body relations with
member identities. The existing successful-article convenience export merges
only identical-field members of a canonical group and retains alias IDs/review
warnings. All request rows now also have a separate unmerged retained-results
export. Cross-URL equal text does not automatically establish a unique article.
The historical 19 relation pairs involve 24 records; subtracting 19 from 2,670
is invalid. Publication/version and broader article-unit decisions remain
`NEEDS_JOAQUIN_REVIEW`; preserve every original record meanwhile.

## Publication dates

Use explicit article publication evidence (visible byline, scoped JSON-LD
`datePublished`, publication-specific metadata). Preserve original evidence and
precision. Compare timestamps at shared precision and timezone where supplied;
do not invent seconds or timezone. Keep `dateModified`, directory timestamps,
archive capture and scrape timestamps separate. None replaces publication time.
Compatible evidence at different precision is not a conflict; genuine
publication conflicts remain null/flagged until resolved. Directory disagreement
is source evidence, not a reason to replace the article's publication date.

## Short articles and video

Retain genuine short news without a minimum-character exclusion. Preserve video
pages, their source URLs and any actual prose. Never invent transcripts.
`article_kind` is a derived technical label: `article`, `article_with_video`, or
`video_only`. Here `article` means no video recognized by these narrow rules,
not proof that a page has no video (other embeds remain preserved). HTTP
`content_type` keeps its MIME meaning. Video classification
requires a native video element or a recognized video embed, not an arbitrary
iframe or an ordinary tweet link. `media_evidence` records the selector/raw URL
and normalized video URL; `classification_rule_version` identifies the rule.

Zero-prose video records remain stored and visible in `retained_results`, with
`main_text` null and the truthful existing `missing_body` error. They are not
silently promoted to core-complete text articles. Independently verified
zero-prose video source pages carry a source-content warning rather than an
unexplained missing-body alarm; unrelated empty/error/advertisement pages and
omitted real prose must still fail. A video-only record has no
body text for text analysis. Classification itself is automated, not review.

## Social quotations and source warnings

Collect newspaper articles, not standalone tweets. Preserve newspaper prose,
embedded quotations and original source languages in raw/faithful fields. A
separate analysis view excluding embedded quotations is `NEEDS_JOAQUIN_REVIEW`;
never delete the whole article or silently rewrite its original text.

A nested article wrapper entirely inside one recognized body is structurally
different from multiple competing article/lead/body containers. The former is
retained with source-markup evidence and research warnings; the latter still
fails. Conversation-style attributes already present in downloaded HTML are
source observations, not proof about authorship or our pipeline's authorship.
Source amount/headline conflicts remain `NEEDS_JOAQUIN_REVIEW`.

Only an isolated, terminal related-article recommendation may be excluded under
the established body contract, with exact text/link in removal evidence. Mixed
news paragraphs, mid-body recommendations and news links remain content.
Source checking implements the contract independently of the extraction parser;
prose loss, media loss, real date conflicts and unexpected layouts must still
raise technical flags. Warnings and old halt records are never erased to pass.

## Reproducible offline validation and exports

`audit_tiempo_missing_titles.py --package <frozen-package> --output <new-dir>`
reproduces the independent 592-record title-channel scan without importing the
production parser. It does not claim a full reading or create review approvals.

`review_tiempo_frozen_package.py --package <frozen-package> --output <new-dir>`
checks bound source snapshots, reparses them without network, compares core
fields and creates a sidecar. It refuses an existing output directory or a
location inside the frozen package. The sidecar is a new audit, not a replacement
corpus or a human approval sheet. Original review fields remain unchanged.

Pilot exports include `articles` (legacy core-complete canonical view),
`attempts` (attempt ledger), and `retained_results` (all committed request rows,
including errors, source-empty titles and video-only pages). CSV and Parquet
forms have matching record identities; Parquet preserves typed nulls. Exports
carry field evidence and review state. Existing seven-field review digests
continue to bind source text/date/identity/media; new derived classification is
not retrospectively human-reviewed. Changing media links invalidates an old
core-field digest automatically.

The next collection stage must first freeze a versioned successor runtime,
verify reuse of saved rows and raw snapshots, bind the remaining queue, and pass
recovery checks. This priority does not migrate the 44,146-row halted campaign,
clear its safety halt, restart collection, or analyze its later corpus.
