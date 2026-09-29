#!/usr/bin/env python3
"""Reconstruct the daily AMLO approval series from El Economista graphics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402


BASE_URL = "https://www.eleconomista.com.mx"
TAG_URL = f"{BASE_URL}/tags/%2523amlotrackingpoll-12444"
AUTHOR_URL = f"{BASE_URL}/autor/consulta.mitofsky?facet=app&mode=light"
CDX_URL = "https://web.archive.org/cdx/search/cdx"
USER_AGENT = "amlo-tracking-poll-research/0.2 (+public archival research)"
ARTICLE_PATTERN = re.compile(
    r"https?://(?:www\.)?eleconomista\.com\.mx/+politica/"
    r"[^?#\"']*amlotrackingpoll[^?#\"']*\.html",
    re.IGNORECASE,
)
PUBLICATION_DATE_PATTERN = re.compile(r"-(20\d{2})(\d{2})(\d{2})-\d+\.html$")
SPANISH_MONTHS = {name: index for index, name in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
     "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}
DATE_PATTERN = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})(?!\d)")
VALUE_PATTERN = re.compile(r"(?<!\d)(\d{2})[.,](\d)(?!\d)")
COMPACT_VALUE_PATTERN = re.compile(r"(?<!\d)([2-7]\d{2})(?!\d)")
RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class SourceRecord:
    """Describe one candidate daily article and its provenance."""

    article_url: str
    publication_date: str = ""
    image_url: str = ""
    archive_url: str = ""
    discovery_sources: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON representation."""

        record = asdict(self)
        record["discovery_sources"] = sorted(self.discovery_sources)
        return record


@dataclass
class SeriesObservation:
    """Store one OCR result and all information needed to audit it."""

    measurement_date: str
    approval: float | None
    disapproval: float | None
    disapproval_complement: float | None
    disapproval_effective: float | None
    disapproval_source: str
    publication_date: str
    date_source: str
    article_url: str
    image_url: str
    archive_url: str
    image_path: str
    discovery_sources: str
    extraction_method: str
    ocr_text: str
    approval_confidence: float | None
    disapproval_confidence: float | None
    sum_percent: float | None
    review_status: str
    review_flags: str


def http_get(url: str, *, timeout: int = 45, retries: int = 4) -> bytes:
    """Download a public resource with bounded retries and a descriptive agent."""

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*,*/*",
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in RETRYABLE_HTTP_CODES or attempt == retries:
                raise
        except urllib.error.URLError:
            if attempt == retries:
                raise
        time.sleep(min(20.0, 2**attempt))
    raise AssertionError("The retry loop should return or raise")


def clean_article_url(url: str) -> str | None:
    """Normalize a matching El Economista article URL and discard decorations."""

    url = html.unescape(url).replace("\\/", "/")
    url = url.replace("/amp/politica/", "/politica/")
    if url.startswith("/"):
        url = urllib.parse.urljoin(BASE_URL, url)
    match = ARTICLE_PATTERN.search(url)
    if not match:
        return None
    clean = match.group(0).replace("http://", "https://", 1)
    clean = clean.replace("eleconomista.com.mx//", "eleconomista.com.mx/")
    clean = re.sub(r"^https://eleconomista\.com\.mx/", f"{BASE_URL}/", clean)
    return clean


def publication_date_from_url(url: str) -> str:
    """Extract the publication date embedded near the end of an article slug."""

    match = PUBLICATION_DATE_PATTERN.search(url)
    if not match:
        return ""
    try:
        return date(int(match[1]), int(match[2]), int(match[3])).isoformat()
    except ValueError:
        return ""


def measurement_date_from_slug(url: str) -> str:
    """Read the day named in a daily article title, including overnight posts."""

    match = re.search(r"-(\d{1,2})-de-(" + "|".join(SPANISH_MONTHS)
                      + r")(?:-de-(20\d{2}))?-", url, flags=re.I)
    published = publication_date_from_url(url)
    if not match or not published:
        return ""
    publication = date.fromisoformat(published)
    years = [int(match[3])] if match[3] else [publication.year - 1, publication.year, publication.year + 1]
    candidates = []
    for year in years:
        try:
            candidate = date(year, SPANISH_MONTHS[match[2].lower()], int(match[1]))
        except ValueError:
            continue
        if abs((candidate - publication).days) <= 3:
            candidates.append(candidate)
    return min(candidates, key=lambda day: abs((day - publication).days)).isoformat() if candidates else ""


def full_size_image_url(url: str) -> str:
    """Promote a listing thumbnail URL to the site's full-size image variant."""

    url = html.unescape(url).replace("\\/", "/")
    # The 1000x1000 transform preserves the original aspect ratio. The
    # 1200x600 transform crops tall 2020 infographics and loses the current day.
    url = re.sub(r"/files/(?:webp|image)_\d+_\d+/", "/files/image_1000_1000/", url)
    return url


def parse_listing_records(document: str, source: str) -> list[SourceRecord]:
    """Extract tracking-poll articles and thumbnails from a listing document."""

    records: list[SourceRecord] = []
    for block in re.findall(r"<article\b.*?</article>", document, flags=re.I | re.S):
        hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", block, flags=re.I)
        article_url = next((clean_article_url(value) for value in hrefs if clean_article_url(value)), None)
        if not article_url:
            continue
        image_match = re.search(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", block, flags=re.I)
        image_url = full_size_image_url(image_match[1]) if image_match else ""
        records.append(
            SourceRecord(
                article_url=article_url,
                publication_date=publication_date_from_url(article_url),
                image_url=image_url,
                discovery_sources={source},
            )
        )
    return records


def parse_next_url(document: str) -> str:
    """Extract the next-page link used by the site's listing widget."""

    matches = re.findall(
        r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*class=[\"'][^\"']*c-pagination__btn",
        document,
        flags=re.I,
    )
    if not matches:
        matches = re.findall(
            r"<a\b[^>]*class=[\"'][^\"']*c-pagination__btn[^\"']*[\"'][^>]*href=[\"']([^\"']+)",
            document,
            flags=re.I,
        )
    return urllib.parse.urljoin(BASE_URL, html.unescape(matches[-1])) if matches else ""


def discover_from_listing(
    start_url: str, source: str, max_pages: int, *, checkpoint=None,
) -> list[SourceRecord]:
    """Follow one public listing until its next link disappears or repeats."""

    records: list[SourceRecord] = []
    seen_pages: set[str] = set()
    page_url = start_url
    page_number = 0
    while page_url and page_url not in seen_pages and page_number < max_pages:
        seen_pages.add(page_url)
        page_number += 1
        try:
            document = http_get(page_url).decode("utf-8", errors="replace")
        except Exception as error:  # The other discovery sources can still succeed.
            print(f"Warning: {source} page {page_number} failed: {error}", file=sys.stderr)
            break
        page_records = parse_listing_records(document, source)
        records.extend(page_records)
        if checkpoint is not None:
            checkpoint(page_records)
        if page_number == 1 or page_number % 10 == 0:
            print(f"{source}: read {page_number} pages and found {len(records)} candidates")
        page_url = parse_next_url(document)
    return records


def discover_from_cdx(
    cache_path: Path, *, url_pattern: str | None = None, refresh: bool = False,
) -> list[SourceRecord]:
    """Use Internet Archive's index to enumerate historical article URLs."""

    params = [
        ("url", url_pattern or "www.eleconomista.com.mx/politica/AMLOTrackingPoll*"),
        ("output", "json"),
        ("fl", "timestamp,original"),
        ("collapse", "urlkey"),
    ]
    if not refresh and cache_path.is_file() and cache_path.stat().st_size:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        raw_payload = http_get(f"{CDX_URL}?{urllib.parse.urlencode(params)}")
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(raw_payload)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_bytes(raw_payload)
        temporary.replace(cache_path)
    if not payload:
        return []
    header = payload[0]
    records: list[SourceRecord] = []
    for raw in payload[1:]:
        item = dict(zip(header, raw))
        article_url = clean_article_url(item.get("original", ""))
        if not article_url:
            continue
        timestamp = item.get("timestamp", "")
        archive_url = (
            f"https://web.archive.org/web/{timestamp}id_/{article_url}" if timestamp else ""
        )
        records.append(
            SourceRecord(
                article_url=article_url,
                publication_date=publication_date_from_url(article_url),
                archive_url=archive_url,
                discovery_sources={"internet_archive_cdx"},
            )
        )
    print(f"internet_archive_cdx: found {len(records)} indexed candidates")
    return records


def merge_source_records(records: Iterable[SourceRecord]) -> list[SourceRecord]:
    """Merge duplicated candidates without losing discovery provenance."""

    merged: dict[str, SourceRecord] = {}
    for record in records:
        current = merged.get(record.article_url)
        if current is None:
            merged[record.article_url] = record
            continue
        current.discovery_sources.update(record.discovery_sources)
        current.publication_date = current.publication_date or record.publication_date
        current.image_url = current.image_url or record.image_url
        current.archive_url = current.archive_url or record.archive_url
    return sorted(merged.values(), key=lambda item: (item.publication_date, item.article_url))


def extract_image_url(document: str) -> str:
    """Read the primary image URL from article metadata."""

    patterns = [
        r'<meta\b[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)',
        r'<meta\b[^>]*name=["\']twitter:image["\'][^>]*content=["\']([^"\']+)',
        r'<meta\b[^>]*content=["\']([^"\']+)["\'][^>]*(?:property=["\']og:image|name=["\']twitter:image)',
    ]
    for pattern in patterns:
        match = re.search(pattern, document, flags=re.I)
        if match:
            return full_size_image_url(match[1])
    return ""


def enrich_record(record: SourceRecord) -> SourceRecord:
    """Fetch an article only when discovery did not expose its primary image."""

    if record.image_url:
        return record
    errors: list[str] = []
    for url in (record.article_url, record.archive_url):
        if not url:
            continue
        try:
            document = http_get(url).decode("utf-8", errors="replace")
            record.image_url = extract_image_url(document)
            if record.image_url:
                return record
        except Exception as error:
            errors.append(str(error))
    if errors:
        print(f"Warning: no article image for {record.article_url}: {errors[-1]}", file=sys.stderr)
    return record


def enrich_records(
    records: list[SourceRecord], workers: int, *, manifest_path: Path | None = None,
) -> list[SourceRecord]:
    """Resolve missing image URLs concurrently while preserving record order."""

    pending = [record for record in records if not record.image_url]
    print(f"Resolving image metadata for {len(pending)} articles")
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(enrich_record, record): record for record in pending}
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 50 == 0 or completed == len(pending):
                if manifest_path is not None:
                    write_jsonl(manifest_path, (record.to_dict() for record in records))
                print(f"Resolved article metadata: {completed}/{len(pending)}")
    return records


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """Write newline-delimited JSON atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def read_source_manifest(path: Path) -> list[SourceRecord]:
    """Restore source records from a prior discovery run."""

    records: list[SourceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        raw["article_url"] = clean_article_url(raw["article_url"]) or raw["article_url"]
        raw["discovery_sources"] = set(raw.get("discovery_sources", []))
        if raw.get("image_url"):
            raw["image_url"] = full_size_image_url(raw["image_url"])
        records.append(SourceRecord(**raw))
    return merge_source_records(records)


def image_filename(record: SourceRecord) -> str:
    """Create a collision-resistant image filename with a readable date prefix."""

    digest = hashlib.sha1(record.article_url.encode("utf-8")).hexdigest()[:12]
    extension = Path(urllib.parse.urlsplit(record.image_url).path).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".img"
    return f"{record.publication_date or 'unknown-date'}_{digest}_full{extension}"


def download_image(record: SourceRecord, image_dir: Path) -> Path | None:
    """Download and verify one source graphic, retaining successful cached files."""

    if not record.image_url:
        return None
    target = image_dir / image_filename(record)
    if target.is_file() and target.stat().st_size > 1_000:
        return target
    try:
        payload = http_get(record.image_url)
        with Image.open(io.BytesIO(payload)) as source:
            source.verify()
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)
        return target
    except Exception as error:
        print(f"Warning: image download failed for {record.article_url}: {error}", file=sys.stderr)
        return None


def download_images(records: list[SourceRecord], image_dir: Path, workers: int) -> dict[str, Path]:
    """Download source graphics concurrently and return paths by article URL."""

    image_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    completed = 0
    print(f"Downloading or checking {len(records)} source graphics")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_image, record, image_dir): record for record in records}
        for future in as_completed(futures):
            record = futures[future]
            path = future.result()
            if path:
                paths[record.article_url] = path
            completed += 1
            if completed % 50 == 0 or completed == len(records):
                print(f"Checked source graphics: {completed}/{len(records)} ({len(paths)} available)")
    return paths


def run_tesseract(
    image: Image.Image,
    tesseract: str,
    *,
    variant: str,
    offset_x: int = 0,
    offset_y: int = 0,
) -> tuple[str, list[dict[str, Any]]]:
    """OCR an image crop and return plain text plus positioned word records."""

    with tempfile.TemporaryDirectory(prefix="amlo-ocr-") as temporary_dir:
        image_path = Path(temporary_dir) / "crop.png"
        image.save(image_path)
        common = [
            tesseract,
            str(image_path),
            "stdout",
            "--psm",
            "11",
            "-c",
            "tessedit_char_whitelist=0123456789.,/-",
        ]
        tsv = subprocess.run([*common, "tsv"], check=True, capture_output=True, text=True).stdout

    words: list[dict[str, Any]] = []
    # Tesseract's word column can contain literal quotes. TSV has no CSV quoting;
    # treating those quotes as delimiters can swallow the remaining word rows.
    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            words.append(
                {
                    "text": text,
                    "left": int(row["left"]) + offset_x,
                    "top": int(row["top"]) + offset_y,
                    "width": int(row["width"]),
                    "height": int(row["height"]),
                    "confidence": float(row["conf"]),
                    "variant": variant,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    plain = "\n".join(word["text"] for word in sorted(words, key=lambda item: (item["top"], item["left"])))
    return plain, words


def prepare_ocr_crops(source: Image.Image) -> list[tuple[str, Image.Image, int, int]]:
    """Return general and focused crops containing the current observation."""

    image = ImageOps.exif_transpose(source).convert("RGB")
    width, height = image.size
    general_x = int(width * 0.70)
    edge_x = int(width * 0.84)
    crops = [
        ("general", image.crop((general_x, 0, width, height)), general_x, 0),
        ("right_edge", image.crop((edge_x, 0, width, height)), edge_x, 0),
    ]
    if height / width >= 0.70:
        box_x = int(width * 0.84)
        box_right = int(width * 0.99)
        box_top = int(width * 0.28)
        box_bottom = min(height, int(width * 0.56))
        crops.append(
            (
                "square_result_box",
                image.crop((box_x, box_top, box_right, box_bottom)),
                box_x,
                box_top,
            )
        )
    return crops


def white_text_mask(image: Image.Image) -> Image.Image:
    """Create a binary image that isolates white numeric labels on dark fills."""

    source = image.convert("RGB")
    output = Image.new("L", source.size, 255)
    source_pixels = source.load()
    output_pixels = output.load()
    for y in range(source.height):
        for x in range(source.width):
            red, green, blue = source_pixels[x, y]
            if min(red, green, blue) >= 150 and max(red, green, blue) - min(red, green, blue) <= 45:
                output_pixels[x, y] = 0
    return output


def light_pixel_mask(image: Image.Image) -> Image.Image:
    """Retain light pixels to recover white labels inside colored result boxes."""

    return ImageOps.grayscale(image).point(lambda value: 0 if value > 100 else 255)


def parse_ocr_date(text: str) -> str:
    """Convert the first valid numeric date in OCR text to ISO format."""

    for day_text, month_text, year_text in DATE_PATTERN.findall(text):
        year = int(year_text)
        if year < 100:
            year += 2000
        if not 2018 <= year <= 2025:
            continue
        try:
            return date(year, int(month_text), int(day_text)).isoformat()
        except ValueError:
            continue
    return ""


def numeric_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return positioned OCR words that can represent approval percentages."""

    values: list[dict[str, Any]] = []
    for word in words:
        token = word["text"].strip()
        match = VALUE_PATTERN.search(token)
        compact = COMPACT_VALUE_PATTERN.search(token) if not match else None
        if match:
            value = float(f"{match[1]}.{match[2]}")
            compact_ocr = False
        elif compact:
            value = int(compact[1]) / 10
            compact_ocr = True
        else:
            continue
        if 20.0 <= value <= 80.0:
            values.append(
                {
                    "value": value,
                    "center_x": word["left"] + word["width"] / 2,
                    "center_y": word["top"] + word["height"] / 2,
                    "confidence": word["confidence"],
                    "variant": word.get("variant", "unknown"),
                    "compact_ocr": compact_ocr,
                    "role": word.get("role", "unknown"),
                }
            )
    values.sort(key=lambda item: (item["center_x"], item["center_y"]))
    return values


def numeric_role_from_image(source: Image.Image, word: dict[str, Any]) -> str:
    """Identify the green agreement or red disagreement associated with a label."""

    def role_in_box(box):
        crop = source.crop(box).convert("RGB")
        green = red = 0
        for r, g, b in getattr(crop, "get_flattened_data", crop.getdata)():
            green += int(g > r + 20 and g > b + 10 and g > 65)
            red += int(r > g + 45 and r > b + 35 and r > 85)
        minimum = max(8, crop.width * crop.height * 0.08)
        if green >= minimum and green > red * 3:
            return "approval"
        if red >= minimum and red > green * 3:
            return "disapproval"
        return "unknown"

    left, top = word["left"], word["top"]
    width, height = word["width"], word["height"]
    # Colored result boxes surround the text itself. This is stronger evidence
    # than the relative vertical positions or the previous day's percentages.
    box = (max(0, left - 4), max(0, top - 4),
           min(source.width, left + width + 4), min(source.height, top + height + 4))
    role = role_in_box(box)
    if role != "unknown":
        return role
    local = source.crop(box).convert("RGB")
    brightness = sorted((r + g + b) / 3
                        for r, g, b in getattr(local, "get_flattened_data", local.getdata)())
    if brightness and brightness[len(brightness) // 2] > 170:
        # Black labels above bars refer to the bar below them, rather than a
        # neighboring bar to the left (which may represent the other response).
        center_x = left + width // 2
        for distance in (4, 10, 20, 35):
            box = (max(0, center_x - 8), min(source.height - 1, top + height + distance),
                   min(source.width, center_x + 8), min(source.height, top + height + distance + 5))
            role = role_in_box(box)
            if role != "unknown":
                return role
        # Earlier line charts place disagreement values below their red line.
        for distance in (3, 8, 15, 25):
            box = (max(0, center_x - 8), max(0, top - distance - 4),
                   min(source.width, center_x + 8), max(1, top - distance + 1))
            role = role_in_box(box)
            if role != "unknown":
                return role
        return "unknown"
    # More recent graphics print white endpoint labels beside the colored area.
    # Sample just below the label center, moving left toward its chart endpoint.
    center_y = top + int(height * 0.70)
    strip_height = max(2, height // 5)
    for distance in (20, 40, 70, 110, 160):
        box = (max(0, left - distance), max(0, center_y),
               max(1, left), min(source.height, center_y + strip_height))
        role = role_in_box(box)
        if role != "unknown":
            return role
    return "unknown"


def deduplicate_ocr_values(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse the same label recognized in both raw and white-mask images."""

    selected: list[dict[str, Any]] = []
    for value in sorted(values, key=lambda item: item["confidence"], reverse=True):
        duplicate = any(
            abs(value["value"] - prior["value"]) < 0.05
            and abs(value["center_x"] - prior["center_x"]) < 25
            and abs(value["center_y"] - prior["center_y"]) < 25
            for prior in selected
        )
        if not duplicate:
            selected.append(value)
    return selected


def choose_current_values(
    values: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Choose the rightmost plausible current approval/disapproval labels."""

    pairs: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    for approval in values:
        for disapproval in values:
            if approval is disapproval:
                continue
            if approval.get("role") == "disapproval" or disapproval.get("role") == "approval":
                continue
            verified = approval.get("role") == "approval" and disapproval.get("role") == "disapproval"
            if not verified and approval["center_y"] >= disapproval["center_y"]:
                continue
            total = approval["value"] + disapproval["value"]
            if not 98.0 <= total <= 101.0:
                continue
            score = (
                min(approval["center_x"], disapproval["center_x"]) * 1000
                + approval["center_x"]
                + disapproval["center_x"]
                + approval["confidence"]
                + disapproval["confidence"]
                - abs(total - 100.0) * 10
                + int(verified) * 2_000_000
            )
            pairs.append((score, approval, disapproval))
    if pairs:
        _, approval, disapproval = max(pairs, key=lambda item: item[0])
        return approval, disapproval
    if values:
        candidates = [item for item in values if item.get("role") == "approval"]
        if not candidates:
            candidates = [item for item in values if item.get("role") != "disapproval"]
        if not candidates:
            return None, None
        approval = max(candidates, key=lambda item: (item["center_x"], item["confidence"]))
        return approval, None
    return None, None


def extract_observation(
    record: SourceRecord,
    image_path: Path | None,
    tesseract: str,
    output_root: Path,
) -> SeriesObservation:
    """Extract approval and disapproval and attach conservative review flags."""

    if image_path is None:
        return SeriesObservation(
            measurement_date=record.publication_date,
            approval=None,
            disapproval=None,
            disapproval_complement=None,
            disapproval_effective=None,
            disapproval_source="missing",
            publication_date=record.publication_date,
            date_source="publication_url" if record.publication_date else "missing",
            article_url=record.article_url,
            image_url=record.image_url,
            archive_url=record.archive_url,
            image_path="",
            discovery_sources=";".join(sorted(record.discovery_sources)),
            extraction_method="none",
            ocr_text="",
            approval_confidence=None,
            disapproval_confidence=None,
            sum_percent=None,
            review_status="needs_review",
            review_flags="image_unavailable",
        )

    flags: list[str] = []
    try:
        with Image.open(image_path) as source:
            full_image = ImageOps.exif_transpose(source).convert("RGB")
            crops = prepare_ocr_crops(source)
        all_words: list[dict[str, Any]] = []
        plain_parts: list[str] = []
        for crop_name, crop, offset_x, offset_y in crops:
            prepared_variants = [
                ("raw", crop),
                ("white_text_mask", white_text_mask(crop)),
            ]
            if crop_name == "square_result_box":
                prepared_variants.append(("light_pixel_mask", light_pixel_mask(crop)))
            for variant, prepared in prepared_variants:
                label = f"{crop_name}_{variant}"
                crop_plain, crop_words = run_tesseract(
                    prepared,
                    tesseract,
                    variant=label,
                    offset_x=offset_x,
                    offset_y=offset_y,
                )
                all_words.extend(crop_words)
                plain_parts.append(f"{label.upper()}: {crop_plain.strip()}")
        plain = " | ".join(plain_parts)
        for word in all_words:
            word["role"] = numeric_role_from_image(full_image, word)
        values = deduplicate_ocr_values(numeric_words(all_words))
    except Exception as error:
        plain = f"OCR_ERROR: {error}"
        values = []

    image_date = parse_ocr_date(plain)
    approval_word, disapproval_word = choose_current_values(values)
    approval = approval_word["value"] if approval_word else None
    disapproval = disapproval_word["value"] if disapproval_word else None
    approval_confidence = approval_word["confidence"] if approval_word else None
    disapproval_confidence = disapproval_word["confidence"] if disapproval_word else None
    role_verified = (approval_word is not None and approval_word.get("role") == "approval"
                     and (disapproval_word is None or disapproval_word.get("role") == "disapproval"))
    flags.append("percentage_roles_verified_by_chart_colors" if role_verified else "percentage_roles_not_verified")
    disapproval_complement = round(100.0 - approval, 1) if approval is not None else None
    disapproval_effective = disapproval if disapproval is not None else disapproval_complement
    disapproval_source = "image_ocr" if disapproval is not None else (
        "complement_100_minus_approval" if disapproval_complement is not None else "missing"
    )
    if len(values) > 2:
        flags.append("extra_numeric_ocr_tokens")
    if approval_word and approval_word.get("compact_ocr"):
        flags.append("approval_decimal_inferred_from_compact_ocr")
    if disapproval_word and disapproval_word.get("compact_ocr"):
        flags.append("disapproval_decimal_inferred_from_compact_ocr")

    measurement_date = record.publication_date
    date_source = "publication_url" if measurement_date else "missing"
    if image_date and record.publication_date:
        day_difference = abs(
            (date.fromisoformat(image_date) - date.fromisoformat(record.publication_date)).days
        )
        if day_difference <= 3:
            measurement_date = image_date
            date_source = "image_ocr"
        else:
            flags.append("implausible_image_date_ignored")
    elif image_date:
        measurement_date = image_date
        date_source = "image_ocr"
    else:
        flags.append("image_date_not_read")
    if image_date and record.publication_date and image_date != record.publication_date:
        flags.append("image_publication_date_mismatch")
    if approval is None:
        flags.append("approval_missing")
    if disapproval is None:
        flags.append("disapproval_not_printed_or_not_read")

    sum_percent = round(approval + disapproval, 1) if approval is not None and disapproval is not None else None
    if sum_percent is not None and not 97.0 <= sum_percent <= 101.0:
        flags.append("percentages_do_not_sum_near_100")
    for confidence in (approval_confidence, disapproval_confidence):
        if confidence is not None and confidence < 50.0:
            flags.append("low_ocr_confidence")
            break

    serious_flags = {"approval_missing", "percentages_do_not_sum_near_100", "low_ocr_confidence",
                     "percentage_roles_not_verified"}
    if serious_flags.intersection(flags):
        review_status = "needs_review"
    elif disapproval is None:
        review_status = "validated_approval_only"
    else:
        review_status = "validated_pair"
    relative_image_path = image_path.relative_to(output_root).as_posix()
    return SeriesObservation(
        measurement_date=measurement_date,
        approval=approval,
        disapproval=disapproval,
        disapproval_complement=disapproval_complement,
        disapproval_effective=disapproval_effective,
        disapproval_source=disapproval_source,
        publication_date=record.publication_date,
        date_source=date_source,
        article_url=record.article_url,
        image_url=record.image_url,
        archive_url=record.archive_url,
        image_path=relative_image_path,
        discovery_sources=";".join(sorted(record.discovery_sources)),
        extraction_method="tesseract_chart_color_roles_v1",
        ocr_text=" | ".join(line.strip() for line in plain.splitlines() if line.strip()),
        approval_confidence=approval_confidence,
        disapproval_confidence=disapproval_confidence,
        sum_percent=sum_percent,
        review_status=review_status,
        review_flags=";".join(sorted(set(flags))),
    )


def extract_all(
    records: list[SourceRecord],
    image_paths: dict[str, Path],
    tesseract: str,
    output_root: Path,
    workers: int,
    *,
    redo_ocr: bool = False,
    retry_review: bool = False,
) -> list[SeriesObservation]:
    """Resume OCR from checkpoints and persist completed results in batches."""

    cache_path = output_root / "extraction_checkpoint.jsonl"
    cached: dict[str, SeriesObservation] = {}
    if not redo_ocr:
        if cache_path.is_file():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = SeriesObservation(**json.loads(line))
                    cached[item.article_url] = item
        else:
            prior_csv = output_root / "all_extractions.csv"
            if prior_csv.is_file():
                with prior_csv.open(encoding="utf-8", newline="") as stream:
                    for raw in csv.DictReader(stream):
                        for key in ("approval", "disapproval", "disapproval_complement",
                                    "disapproval_effective", "approval_confidence",
                                    "disapproval_confidence", "sum_percent"):
                            raw[key] = float(raw[key]) if raw.get(key) else None
                        item = SeriesObservation(**raw)
                        cached[item.article_url] = item

    observations: list[SeriesObservation] = []
    pending: list[SourceRecord] = []
    for record in records:
        prior = cached.get(record.article_url)
        image_path = image_paths.get(record.article_url)
        if (prior is not None and image_path is not None
                and prior.image_path == image_path.relative_to(output_root).as_posix()
                and full_size_image_url(prior.image_url) == record.image_url
                and prior.extraction_method == "tesseract_chart_color_roles_v1"
                and not (retry_review and prior.review_status != "validated_pair")
                and not prior.ocr_text.startswith("OCR_ERROR:")):
            prior.discovery_sources = ";".join(sorted(record.discovery_sources))
            prior.archive_url = record.archive_url or prior.archive_url
            prior.image_url = record.image_url
            observations.append(prior)
        else:
            pending.append(record)

    def save_checkpoint():
        complete = {item.article_url: item for item in observations}
        # Retain earlier results even during a limited run or interruption.
        write_jsonl(cache_path, (asdict(item) for item in {**cached, **complete}.values()))

    save_checkpoint()
    completed = 0
    print(f"Reusing {len(observations)} OCR results; extracting {len(pending)} graphics")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                extract_observation,
                record,
                image_paths.get(record.article_url),
                tesseract,
                output_root,
            ): record
            for record in pending
        }
        for future in as_completed(futures):
            observations.append(future.result())
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                save_checkpoint()
                print(f"OCR progress: {completed}/{len(pending)}")
    return sorted(observations, key=lambda item: (item.measurement_date, item.article_url))


def observation_score(observation: SeriesObservation) -> tuple[int, int, int, float]:
    """Rank duplicate observations by validation, direct date, and OCR confidence."""

    confidence = (observation.approval_confidence or 0) + (observation.disapproval_confidence or 0)
    return (
        int("manual_verified" in observation.review_flags.split(";")),
        int(observation.review_status == "validated_pair") * 2
        + int(observation.review_status == "validated_approval_only"),
        {"image_ocr": 2, "article_slug_title": 1, "graphic_historical_date": 3,
         "graphic_relative_day": 2, "pdf_printed_date": 3,
         "transcript_explicit_date": 3, "social_post_context_date": 3,
         "video_printed_date": 3, "news_reported_date": 3}.get(observation.date_source, 0),
        confidence,
    )


def deduplicate_observations(
    observations: list[SeriesObservation],
) -> tuple[list[SeriesObservation], list[SeriesObservation]]:
    """Keep the strongest observation per measurement date and audit alternatives."""

    grouped: dict[str, list[SeriesObservation]] = defaultdict(list)
    undated: list[SeriesObservation] = []
    for observation in observations:
        if observation.measurement_date:
            grouped[observation.measurement_date].append(observation)
        else:
            undated.append(observation)

    selected: list[SeriesObservation] = []
    duplicates: list[SeriesObservation] = list(undated)
    for measurement_date, candidates in grouped.items():
        candidates.sort(key=observation_score, reverse=True)
        selected.append(candidates[0])
        duplicates.extend(candidates[1:])
    selected.sort(key=lambda item: item.measurement_date)
    return selected, duplicates


def add_review_flag(observation: SeriesObservation, flag: str) -> None:
    """Append one unique review flag to a mutable observation."""

    flags = {item for item in observation.review_flags.split(";") if item}
    flags.add(flag)
    observation.review_flags = ";".join(sorted(flags))


def flag_temporal_outliers(observations: list[SeriesObservation]) -> None:
    """Demote isolated OCR values that conflict with nearby tracking values."""

    usable = [item for item in observations if item.approval is not None]
    for index, observation in enumerate(usable):
        value = observation.approval
        assert value is not None
        flags: list[str] = []
        if not 40.0 <= value <= 75.0:
            flags.append("approval_outside_plausible_range")

        neighbors: list[float] = []
        current_date = date.fromisoformat(observation.measurement_date)
        if index > 0:
            previous = usable[index - 1]
            if (current_date - date.fromisoformat(previous.measurement_date)).days <= 4:
                assert previous.approval is not None
                neighbors.append(previous.approval)
        if index + 1 < len(usable):
            following = usable[index + 1]
            if (date.fromisoformat(following.measurement_date) - current_date).days <= 4:
                assert following.approval is not None
                neighbors.append(following.approval)
        if len(neighbors) == 2:
            local_center = sum(neighbors) / 2
            if abs(value - local_center) > 3.0 and abs(neighbors[0] - neighbors[1]) <= 3.0:
                flags.append("isolated_temporal_outlier")

        if flags:
            for flag in flags:
                add_review_flag(observation, flag)
            observation.review_status = "needs_review"


def write_csv(path: Path, records: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write a CSV with explicit, stable column order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(path)


def write_weekly_series(path: Path, daily: list[SeriesObservation]) -> None:
    """Aggregate validated daily observations by ISO week."""

    groups: dict[tuple[int, int], list[SeriesObservation]] = defaultdict(list)
    for observation in daily:
        if (
            observation.review_status == "needs_review"
            or observation.approval is None
            or observation.disapproval_effective is None
        ):
            continue
        parsed = date.fromisoformat(observation.measurement_date)
        iso_year, iso_week, _ = parsed.isocalendar()
        groups[(iso_year, iso_week)].append(observation)

    rows: list[dict[str, Any]] = []
    for (iso_year, iso_week), observations in sorted(groups.items()):
        observations.sort(key=lambda item: item.measurement_date)
        last = observations[-1]
        rows.append(
            {
                "iso_year": iso_year,
                "iso_week": iso_week,
                "week_start": date.fromisocalendar(iso_year, iso_week, 1).isoformat(),
                "week_end": date.fromisocalendar(iso_year, iso_week, 7).isoformat(),
                "observations": len(observations),
                "approval_mean": round(sum(item.approval for item in observations if item.approval is not None) / len(observations), 3),
                "disapproval_effective_mean": round(
                    sum(
                        item.disapproval_effective
                        for item in observations
                        if item.disapproval_effective is not None
                    )
                    / len(observations),
                    3,
                ),
                "approval_last": last.approval,
                "disapproval_effective_last": last.disapproval_effective,
                "disapproval_last_source": last.disapproval_source,
                "last_observation_date": last.measurement_date,
            }
        )
    write_csv(path, rows, list(rows[0]) if rows else ["iso_year", "iso_week"])


def export_series(output_root: Path, records: list[SourceRecord], observations: list[SeriesObservation], image_count: int) -> int:
    """Merge audited supplemental observations and regenerate reproducible exports."""

    for item in observations:
        if item.date_source == "publication_url":
            title_date = measurement_date_from_slug(item.article_url)
            if title_date:
                item.measurement_date = title_date
                item.date_source = "article_slug_title"
                if title_date != item.publication_date:
                    add_review_flag(item, "title_publication_date_mismatch")
    supplement_path = output_root / "supplemental_observations.jsonl"
    supplements = [SeriesObservation(**json.loads(line)) for line in supplement_path.read_text().splitlines()] if supplement_path.is_file() else []
    observations = [*observations, *supplements]
    selected, duplicates = deduplicate_observations(observations)
    flag_temporal_outliers(selected)
    fields = list(SeriesObservation.__dataclass_fields__)
    write_csv(output_root / "approval_series_daily.csv", (asdict(item) for item in selected), fields)
    write_csv(
        output_root / "approval_series_daily_validated.csv",
        (asdict(item) for item in selected if item.review_status != "needs_review"),
        fields,
    )
    write_csv(output_root / "all_extractions.csv", (asdict(item) for item in observations), fields)
    write_csv(output_root / "duplicate_extractions.csv", (asdict(item) for item in duplicates), fields)
    write_weekly_series(output_root / "approval_series_weekly.csv", selected)

    coverage = []
    if selected:
        daily_by_date = {item.measurement_date: item for item in selected}
        publications = defaultdict(int)
        for record in records:
            publications[record.publication_date] += 1
        current = date.fromisoformat(selected[0].measurement_date)
        end = date.fromisoformat(selected[-1].measurement_date)
        while current <= end:
            iso = current.isoformat()
            item = daily_by_date.get(iso)
            coverage.append({
                "date": iso, "weekday": current.isoweekday(),
                "article_count": publications[iso],
                "status": item.review_status if item else "no_observation_found",
                "article_url": item.article_url if item else "",
            })
            current += timedelta(days=1)
    write_csv(output_root / "daily_coverage.csv", coverage,
              ["date", "weekday", "article_count", "status", "article_url"])

    valid_pairs = sum(item.review_status == "validated_pair" for item in selected)
    valid_approval_only = sum(
        item.review_status == "validated_approval_only" for item in selected
    )
    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "unique_article_urls": len(records),
        "images_available": image_count,
        "supplemental_observations": len(supplements),
        "unique_measurement_dates": len(selected),
        "validated_pairs": valid_pairs,
        "validated_approval_only": valid_approval_only,
        "dates_needing_review": len(selected) - valid_pairs - valid_approval_only,
        "duplicate_or_undated_extractions": len(duplicates),
        "date_range": [selected[0].measurement_date, selected[-1].measurement_date] if selected else [],
        "calendar_days_in_range": len(coverage),
        "calendar_days_without_observation": sum(row["status"] == "no_observation_found" for row in coverage),
        "weekdays_without_observation": sum(row["status"] == "no_observation_found" and row["weekday"] <= 5 for row in coverage),
    }
    (output_root / "series_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0



def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORK_ROOT)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--exports-only", action="store_true", help="Rebuild exports from cached primary and supplemental observations without network access.")
    parser.add_argument("--max-listing-pages", type=int, default=300)
    parser.add_argument(
        "--use-existing-manifest",
        action="store_true",
        help="Skip URL discovery and reuse output/source_manifest.jsonl.",
    )
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="Build the source manifest without downloading or reading images.",
    )
    parser.add_argument("--limit", type=int, help="Process only the first N discovered articles.")
    parser.add_argument("--refresh-cdx", action="store_true", help="Refresh the complete historical URL indexes.")
    parser.add_argument("--redo-ocr", action="store_true", help="Re-read all graphics instead of resuming saved extractions.")
    parser.add_argument("--retry-review", action="store_true", help="Re-read review rows and incomplete percentage pairs.")
    return parser.parse_args()


def main() -> int:
    """Run discovery, image acquisition, OCR, validation, and aggregation."""

    args = parse_args()
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = output_root / "source_manifest.jsonl"

    if args.exports_only:
        records = read_source_manifest(manifest_path)
        observations = [SeriesObservation(**json.loads(line)) for line in (output_root / "extraction_checkpoint.jsonl").read_text().splitlines()]
        image_count = sum(bool(item.image_path) and (output_root / item.image_path).is_file() for item in observations)
        return export_series(output_root, records, observations, image_count)

    if args.use_existing_manifest:
        if not manifest_path.is_file():
            raise SystemExit(f"Manifest does not exist: {manifest_path}")
        records = read_source_manifest(manifest_path)
    else:
        discovered = read_source_manifest(manifest_path) if manifest_path.is_file() else []

        def checkpoint(additions):
            discovered.extend(additions)
            write_jsonl(manifest_path, (item.to_dict() for item in merge_source_records(discovered)))

        for filename, pattern in (
            ("cdx_index.json", "www.eleconomista.com.mx/politica/AMLOTrackingPoll*"),
            ("cdx_complete_index.json", "www.eleconomista.com.mx/politica/AMLOTrackingPoll*"),
            ("cdx_amp_index.json", "www.eleconomista.com.mx/amp/politica/AMLOTrackingPoll*"),
        ):
            try:
                checkpoint(discover_from_cdx(output_root / filename, url_pattern=pattern,
                                             refresh=args.refresh_cdx and filename != "cdx_index.json"))
            except Exception as error:
                print(f"Warning: {filename} discovery failed: {error}", file=sys.stderr)
        discover_from_listing(AUTHOR_URL, "mitofsky_author", args.max_listing_pages, checkpoint=checkpoint)
        discover_from_listing(TAG_URL, "tracking_poll_tag", args.max_listing_pages, checkpoint=checkpoint)
        records = merge_source_records(discovered)
        print(f"Combined discovery: {len(records)} unique article URLs")
        records = enrich_records(records, max(1, args.workers), manifest_path=manifest_path)
        write_jsonl(manifest_path, (record.to_dict() for record in records))

    if args.limit is not None:
        records = records[: args.limit]
    if args.discovery_only:
        print(f"Wrote {len(records)} source records to {manifest_path}")
        return 0

    # A resumed manifest may still contain unresolved article image URLs.
    if args.use_existing_manifest:
        records = enrich_records(records, max(1, args.workers),
                                 manifest_path=manifest_path if args.limit is None else None)
    if args.limit is None:
        write_jsonl(manifest_path, (record.to_dict() for record in records))

    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise SystemExit("Tesseract is required for OCR but was not found on PATH.")

    image_paths = download_images(records, output_root / "images", max(1, args.workers))
    observations = extract_all(
        records,
        image_paths,
        tesseract,
        output_root,
        max(1, min(args.workers, 8)),
        redo_ocr=args.redo_ocr,
        retry_review=args.retry_review,
    )
    return export_series(output_root, records, observations, len(image_paths))


if __name__ == "__main__":
    raise SystemExit(main())
