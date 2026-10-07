"""Inspect public archive pagination before continuing historical discovery."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import urllib.parse
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402

import build_approval_series as b


def probe(item):
    label, url = item
    try:
        raw = b.http_get(url, timeout=45, retries=0)
        path = WORK_ROOT / "discovery_probes" / f"{label}.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        document = raw.decode("utf-8", errors="replace")
        if label.startswith("cdx"):
            payload = json.loads(document)
            return {"label": label, "rows": len(payload) - 1, "sample": payload[:3]}
        records = b.parse_listing_records(document, "probe")
        if label.startswith("archived_listing"):
            links = re.findall(r'href=["\x27]([^"\x27]+)', document, flags=re.I)
            records = b.merge_source_records([*records, *[
                b.SourceRecord(article_url=clean,
                               publication_date=b.publication_date_from_url(clean),
                               discovery_sources={"internet_archive_tag"})
                for link in links if (clean := b.clean_article_url(link))
            ]])
            b.write_jsonl(path.with_suffix(".jsonl"), (r.to_dict() for r in records))
        return {"label": label, "url": url, "bytes": len(raw),
                "records": len(records), "dates": [r.publication_date for r in records],
                "next": b.parse_next_url(document)}
    except Exception as error:
        return {"label": label, "url": url, "error": str(error)}


if __name__ == "__main__":
    urls = []
    for name in ("cdx_old_tag_captures", "cdx_current_tag_captures"):
        captures = json.loads((WORK_ROOT / "discovery_probes" / (name + ".html")).read_text())
        for timestamp, original in captures[1:]:
            urls.append((f"archived_listing_{timestamp}", f"https://web.archive.org/web/{timestamp}id_/{original}"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(probe, urls):
            print(json.dumps(result), flush=True)
