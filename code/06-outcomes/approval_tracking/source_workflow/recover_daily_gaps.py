#!/usr/bin/env python3
"""Recover printed daily observations from cached charts and public press PDFs."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import json
import subprocess
import xml.etree.ElementTree as ET
import csv
import io
import re
import tempfile
import unicodedata
import hashlib
import html
import urllib.parse
from datetime import timedelta
from PIL import Image, ImageOps
from collections import defaultdict
from dataclasses import asdict
from difflib import SequenceMatcher

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402

import build_approval_series as b


ROOT = WORK_ROOT
RECOVERY = ROOT / "recovery"
MONTH_NAMES = {name.upper(): number for name, number in b.SPANISH_MONTHS.items()}
MONTH_NAMES.update({"ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5,
                    "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SEPT": 9,
                    "OCT": 10, "NOV": 11, "DIC": 12})


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.upper()) if not unicodedata.combining(c))


def full_ocr(path: Path, *, axis_rotation: bool = False) -> list[dict]:
    cache = RECOVERY / "ocr" / (path.stem + ("_axis" if axis_rotation else "_full") + ".json")
    if cache.is_file():
        cached = json.loads(cache.read_text())
        if not any("\n" in w["text"] or "\t" in w["text"] for w in cached):
            return cached
    with Image.open(path) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        image_height = source.height
        axis_top = int(source.height * 0.73)
        if axis_rotation:
            source = source.crop((0, axis_top, source.width, int(source.height * 0.93)))
            axis_height = source.height
            source = source.transpose(Image.Transpose.ROTATE_270)
        source = source.resize((source.width * 2, source.height * 2))
        with tempfile.TemporaryDirectory(prefix="amlo-recovery-") as temporary:
            temporary_image = Path(temporary) / "ocr.png"
            source.save(temporary_image)
            payload = subprocess.run(["tesseract", str(temporary_image), "stdout", "--psm", "11", "tsv"],
                                     check=True, capture_output=True, text=True).stdout
    words = []
    for order, raw in enumerate(csv.DictReader(io.StringIO(payload), delimiter="\t", quoting=csv.QUOTE_NONE)):
        if not raw.get("text", "").strip():
            continue
        left, top, width, height = [int(raw[key]) / 2 for key in ("left", "top", "width", "height")]
        if axis_rotation:
            left, top, width, height = top, axis_top + axis_height - left - width, height, width
        words.append({"text": raw["text"], "left": left, "top": top, "width": width,
                      "height": height, "confidence": float(raw["conf"]), "order": order,
                      "line": ":".join(raw[k] for k in ("block_num", "par_num", "line_num")),
                      "variant": "rotated_axis" if axis_rotation else "full_2x"})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words, ensure_ascii=False))
    return words


def focused_ocr(path: Path, box: tuple[int, int, int, int], name: str, *,
                numbers: bool = False, mask: bool = False, psm: int = 11,
                rotate: bool = False, neutral_mask: bool = False) -> list[dict]:
    cache = RECOVERY / "ocr" / f"{path.stem}_{name}.json"
    if cache.is_file():
        cached = json.loads(cache.read_text())
        if not any("\n" in w["text"] or "\t" in w["text"] for w in cached):
            return cached
    with Image.open(path) as source:
        crop = source.convert("RGB").crop(box)
        original_height = crop.height
        if rotate:
            crop = crop.transpose(Image.Transpose.ROTATE_270)
        if neutral_mask:
            text_mask = Image.new("L", crop.size, 255)
            text_mask.putdata([0 if max(r, g, bl) - min(r, g, bl) < 45 and max(r, g, bl) < 175 else 255
                              for r, g, bl in getattr(crop, "get_flattened_data", crop.getdata)()])
            crop = text_mask
        else:
            crop = b.white_text_mask(crop) if mask else ImageOps.autocontrast(ImageOps.grayscale(crop))
        crop = crop.resize((crop.width * 3, crop.height * 3))
        with tempfile.TemporaryDirectory(prefix="amlo-recovery-") as temporary:
            target = Path(temporary) / "crop.png"
            crop.save(target)
            command = ["tesseract", str(target), "stdout", "--psm", str(psm)]
            if numbers:
                command.extend(["-c", "tessedit_char_whitelist=0123456789.,/-"])
            payload = subprocess.run([*command, "tsv"], check=True, capture_output=True, text=True).stdout
    words = []
    for order, row in enumerate(csv.DictReader(io.StringIO(payload), delimiter="\t", quoting=csv.QUOTE_NONE)):
        if not row.get("text", "").strip():
            continue
        left, top, width, height = [int(row[key]) / 3 for key in ("left", "top", "width", "height")]
        if rotate:
            left, top, width, height = top, original_height - left - width, height, width
        words.append({"text": row["text"], "left": left + box[0],
                      "top": top + box[1], "width": width,
                      "height": height, "confidence": float(row["conf"]),
                      "order": order, "line": ":".join(row[k] for k in ("block_num", "par_num", "line_num")),
                      "variant": name})
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(words, ensure_ascii=False))
    return words


def chart_probe(days: list[str]) -> None:
    rows = list(csv.DictReader((ROOT / "all_extractions.csv").open()))
    for day in days:
        row = next(row for row in rows if row["measurement_date"] == day and row["image_path"])
        path = ROOT / row["image_path"]
        words = full_ocr(path)
        with Image.open(path) as image:
            w, h = image.size
        if day.startswith("2019"):
            words += focused_ocr(path, (0, int(h * 0.68), w, int(h * 0.89)), "axis_dates", psm=6)
            words += full_ocr(path, axis_rotation=True)
        elif day >= "2023":
            words += focused_ocr(path, (0, int(h * 0.2), int(w * 0.3), int(h * 0.82)), "left_percent_white", numbers=True, mask=True)
            words += focused_ocr(path, (0, int(h * 0.2), int(w * 0.3), int(h * 0.82)), "left_percent_raw", numbers=True)
        else:
            words += focused_ocr(path, (0, int(h * 0.57), w, int(h * 0.9)), "comparison_numbers", numbers=True)
        groups = {}
        for word in words:
            groups.setdefault(word["variant"] + ":" + word["line"], []).append(word)
        print(json.dumps({"day": day, "image_path": row["image_path"],
                          "lines": [" ".join(w["text"] for w in group) for group in groups.values()]}), flush=True)


def grouped_words(words: list[dict]) -> list[list[dict]]:
    groups = defaultdict(list)
    for word in words:
        groups[(word["variant"], word["line"])].append(word)
    return list(groups.values())


def comparison_categories(words: list[dict]) -> list[tuple]:
    """Split category phrases even when OCR puts all five on one line."""
    results = []
    pattern = re.compile(r"(?<!\w)(AYER|HOY|1\s*SEMANA|1\s*SEM|15\s*DIAS|1\s*MES)(?!\w)")
    for group in grouped_words(words):
        spans, offset = [], 0
        for word in group:
            token = normalized(word["text"])
            spans.append((offset, offset + len(token), word))
            offset += len(token) + 1
        line = " ".join(normalized(w["text"]) for w in group)
        for match in pattern.finditer(line):
            contributing = [w for start, end, w in spans if start < match.end() and end > match.start()]
            x = (min(w["left"] for w in contributing) + max(w["left"] + w["width"] for w in contributing)) / 2
            y = min(w["top"] for w in contributing)
            results.append((x, y, match[0], match[0].replace(" ", ""), contributing))
    return results


def explicit_dates(words: list[dict], anchor: date, width: int, height: int) -> list[dict]:
    """Read printed dates; infer only an omitted year from the dated source."""
    results = []
    month_pattern = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))
    pattern = re.compile(r"(?<!\w)(\d{1,2})\s*(" + month_pattern + r")(?:\s*(20\d{2}))?(?!\w)")
    for group in grouped_words(words):
        line = " ".join(normalized(w["text"]) for w in group)
        spans = []
        offset = 0
        for word in group:
            token = normalized(word["text"])
            spans.append((offset, offset + len(token), word))
            offset += len(token) + 1
        for match in pattern.finditer(line):
            contributing = [w for start, end, w in spans if start < match.end() and end > match.start()]
            if not contributing:
                continue
            if match[3]:
                years = [int(match[3])]
            else:
                years = [anchor.year - 1, anchor.year]
            possible = []
            for year in years:
                try:
                    candidate = date(year, MONTH_NAMES[match[2]], int(match[1]))
                except ValueError:
                    continue
                if 0 <= (anchor - candidate).days <= 185:
                    possible.append(candidate)
            if possible:
                candidate = max(possible)
                results.append({"date": candidate.isoformat(),
                                "x": sum(w["left"] + w["width"] / 2 for w in contributing) / len(contributing),
                                "y": min(w["top"] for w in contributing),
                                "confidence": min(w["confidence"] for w in contributing),
                                "text": match[0], "kind": "explicit_date"})
    # Early 2019 charts place day numbers above their month abbreviations.
    month_words = [w for w in words if normalized(w["text"]) in MONTH_NAMES
                   and w["top"] >= height * 0.65 and w["variant"] != "rotated_axis"]
    for month_word in month_words:
        month_x = month_word["left"] + month_word["width"] / 2
        candidates = [w for w in words if re.fullmatch(r"\d{1,2}", w["text"])
                      and w["variant"] == month_word["variant"]
                      and 0 < month_word["top"] - w["top"] <= height * 0.10
                      and abs(w["left"] + w["width"] / 2 - month_x) <= width * 0.025]
        if not candidates:
            continue
        day_word = min(candidates, key=lambda w: abs(w["left"] + w["width"] / 2 - month_x))
        try:
            candidate = date(anchor.year, MONTH_NAMES[normalized(month_word["text"])], int(day_word["text"]))
        except ValueError:
            continue
        if 0 <= (anchor - candidate).days <= 12:
            results.append({"date": candidate.isoformat(), "x": month_x, "y": day_word["top"],
                            "confidence": min(day_word["confidence"], month_word["confidence"]),
                            "text": day_word["text"] + " " + month_word["text"], "kind": "explicit_date"})
    return results


def role_at_endpoint(image: Image.Image, word: dict, *, left_endpoint: bool = False) -> str:
    # Use the existing chart-color check for ordinary labels and comparison bars.
    integer_word = {**word, **{key: int(word[key]) for key in ("left", "top", "width", "height")}}
    if not left_endpoint:
        return b.numeric_role_from_image(image, integer_word)
    # The historical endpoint is printed to the left of its green/red region.
    top = int(word["top"] + word["height"] * 0.65)
    left = int(word["left"] + word["width"])
    for distance in (20, 40, 70, 110, 160):
        crop = image.crop((left, top, min(image.width, left + distance),
                           min(image.height, top + max(3, int(word["height"] * 0.25)))))
        green = red = 0
        for r, g, bl in getattr(crop, "get_flattened_data", crop.getdata)():
            green += int(g > r + 20 and g > bl + 10 and g > 65)
            red += int(r > g + 45 and r > bl + 35 and r > 85)
        minimum = max(8, crop.width * crop.height * 0.08)
        if green > minimum and green > red * 3:
            return "approval"
        if red > minimum and red > green * 3:
            return "disapproval"
    return "unknown"


def decimal_labels(words: list[dict]) -> list[dict]:
    labels = []
    for word in words:
        token = word["text"].replace(",", ".")
        if re.fullmatch(r"\d{2}\.\d", token):
            value = float(token)
            if 20 <= value <= 80:
                labels.append({**word, "value": value,
                               "x": word["left"] + word["width"] / 2,
                               "y": word["top"] + word["height"] / 2})
    # One label can be recognized in several OCR variants.
    selected = []
    for label in sorted(labels, key=lambda w: w["confidence"], reverse=True):
        if not any(abs(label["x"] - other["x"]) < 15 and abs(label["y"] - other["y"]) < 15
                   and label["value"] == other["value"] for other in selected):
            selected.append(label)
    return selected


def recovery_candidate(row: dict, printed_date: dict, approval: dict,
                       disapproval: dict | None, kind: str) -> dict:
    confidences = [printed_date["confidence"], approval["confidence"]]
    if disapproval:
        confidences.append(disapproval["confidence"])
    return {"measurement_date": printed_date["date"], "approval": approval["value"],
            "disapproval": disapproval["value"] if disapproval else None,
            "confidence": min(confidences), "article_url": row["article_url"],
            "image_url": row["image_url"], "image_path": row["image_path"],
            "publication_date": row["publication_date"], "source_measurement_date": row["measurement_date"],
            "archive_url": row["archive_url"], "kind": kind,
            "evidence": {"date": printed_date, "approval_label": approval, "disapproval_label": disapproval}}


def recover_chart(row: dict) -> list[dict]:
    path = ROOT / row["image_path"]
    anchor = date.fromisoformat(row["measurement_date"])
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    width, height = image.size
    words = full_ocr(path)
    dark_chart = sum(image.getpixel((int(width * 0.05), int(height * 0.35)))) < 240
    if dark_chart:
        words += focused_ocr(path, (0, int(height * .20), int(width * .30), int(height * .82)),
                             "left_percent_white", numbers=True, mask=True)
        words += focused_ocr(path, (0, int(height * .20), int(width * .30), int(height * .82)),
                             "left_percent_raw", numbers=True)
        dates = explicit_dates(words, anchor, width, height)
        labels = decimal_labels(words)
        results = []
        for printed_date in dates:
            if printed_date["y"] < height * .60:
                continue
            side = "left" if printed_date["x"] < width * .5 else "right"
            candidates = [w for w in labels if height * .20 < w["y"] < printed_date["y"] - 10
                          and ((w["x"] < width * .29) if side == "left" else (w["x"] > width * .75))]
            for word in candidates:
                word["role"] = role_at_endpoint(image, word, left_endpoint=side == "left")
            approved = [w for w in candidates if w["role"] == "approval"]
            rejected = [w for w in candidates if w["role"] == "disapproval"]
            pairs = [(a, d) for a in approved for d in rejected
                     if 97 <= a["value"] + d["value"] <= 101 and abs(a["x"] - d["x"]) < width * .06]
            if pairs:
                a, d = max(pairs, key=lambda pair: min(pair[0]["confidence"], pair[1]["confidence"]))
                results.append(recovery_candidate(row, printed_date, a, d, "printed_chart_endpoint"))
        return results

    results = []
    # Read dated points in the early 2019 charts, including weekends.
    legacy_single = anchor < date(2020, 3, 31) and not any("DESACUERDO" in normalized(w["text"]) for w in words)
    if anchor.year == 2019:
        words += focused_ocr(path, (0, int(height * .68), width, int(height * .89)), "axis_dates", psm=6)
        words += full_ocr(path, axis_rotation=True)
        words += focused_ocr(path, (0, int(height * .30), width, int(height * .74)), "historical_numbers", numbers=True)
        dates = explicit_dates(words, anchor, width, height)
        labels = decimal_labels(words)
        plot = image.crop((int(width * .05), int(height * .3), int(width * .85), int(height * .75)))
        pixels = list(getattr(plot, "get_flattened_data", plot.getdata)())
        green_only = sum(g > r + 20 and g > bl + 10 for r, g, bl in pixels) > len(pixels) * .15 \
            and sum(r > g + 45 and r > bl + 35 and g < 130 for r, g, bl in pixels) < len(pixels) * .015
        for printed_date in dates:
            if printed_date["y"] < height * .64:
                continue
            candidates = [w for w in labels if height * .30 < w["y"] < printed_date["y"] - 8
                          and abs(w["x"] - printed_date["x"]) <= width * .028]
            for word in candidates:
                word["role"] = "approval" if green_only else role_at_endpoint(image, word)
            approved = [w for w in candidates if w["role"] == "approval"]
            rejected = [w for w in candidates if w["role"] == "disapproval"]
            if not approved:
                continue
            a = min(approved, key=lambda w: (abs(w["x"] - printed_date["x"]), -w["confidence"]))
            rejected = [w for w in rejected if 97 <= a["value"] + w["value"] <= 101]
            d = min(rejected, key=lambda w: abs(w["x"] - printed_date["x"])) if rejected else None
            if d or green_only:
                results.append(recovery_candidate(row, printed_date, a, d, "printed_chart_axis_date"))

    # Compare possible interpretations of the longer period labels against
    # known dates before accepting them. Only AYER and a week are unambiguous.
    small_table = anchor.year == 2022 and height / width > .85
    if small_table:
        words += focused_ocr(path, (0, int(height * .62), int(width * .50), int(height * .94)),
                             "comparison_rotated", numbers=True, rotate=True)
        words += focused_ocr(path, (0, int(height * .84), int(width * .50), int(height * .96)),
                             "table_categories", psm=6)
        words += focused_ocr(path, (int(width * .03), int(height * .64), int(width * .47), int(height * .85)),
                             "comparison_neutral", neutral_mask=True, rotate=True)
        words += focused_ocr(path, (int(width * .03), int(height * .64), int(width * .47), int(height * .85)),
                             "comparison_neutral_numeric", numbers=True, neutral_mask=True, rotate=True)
    words += focused_ocr(path, (0, int(height * .57), width, int(height * .90)),
                         "comparison_numbers", numbers=True)
    if legacy_single:
        words += focused_ocr(path, (0, int(height * .4), width, int(height * .95)), "legacy_bar_numbers", numbers=True)
    labels = decimal_labels(words)
    categories = []
    for label_x, label_y, label_text, compact, group in comparison_categories(words):
        if label_y < height * (.4 if legacy_single else .75) or (small_table and label_x > width * .50):
            continue
        categories.append((label_x, label_y, label_text, compact, group))
    centers = sorted({round(category[0], 1) for category in categories})
    for label_x, label_y, label_text, compact, group in categories:
        if compact == "HOY":
            continue
        lags = {"AYER": [1], "1SEMANA": [7], "1SEM": [7], "15DIAS": [14, 15], "1MES": [30, 31]}[compact]
        if legacy_single:
            if compact not in {"AYER", "1SEMANA", "1SEM"}:
                continue
            nearby = [w for w in labels if abs(w["x"] - label_x) < width * .05
                      and 0 < label_y - w["top"] - w["height"] < height * .12]
            if nearby:
                a = min(nearby, key=lambda w: label_y - w["top"] - w["height"])
                printed_date = {"date": (anchor-timedelta(days=lags[0])).isoformat(), "x": label_x,
                                "y": label_y, "text": label_text, "confidence": min(w["confidence"] for w in group),
                                "kind": "explicit_relative_day"}
                results.append(recovery_candidate(row, printed_date, a, None, "printed_comparison_"+str(lags[0])+"_days"))
            continue
        left_neighbor = max((x for x in centers if x < label_x - 15), default=label_x - width * .18)
        right_neighbor = min((x for x in centers if x > label_x + 15), default=label_x + width * .18)
        left_boundary = (left_neighbor + label_x) / 2
        right_boundary = (right_neighbor + label_x) / 2
        candidates = [w for w in labels if height * .52 < w["y"] < label_y - 5
                      and left_boundary < w["x"] < right_boundary]
        for word in candidates:
            word["role"] = role_at_endpoint(image, word)
        approved = [w for w in candidates if w["role"] == "approval"]
        rejected = [w for w in candidates if w["role"] == "disapproval"]
        pairs = [(a, d) for a in approved for d in rejected
                 if 97 <= a["value"] + d["value"] <= 101 and abs((a["x"] + d["x"]) / 2 - label_x) < width * .04]
        if pairs:
            a, d = min(pairs, key=lambda pair: (abs((pair[0]["x"] + pair[1]["x"]) / 2 - label_x),
                                               -min(pair[0]["confidence"], pair[1]["confidence"])))
            for lag in lags:
                printed_date = {"date": (anchor - timedelta(days=lag)).isoformat(), "x": label_x,
                                "y": label_y, "text": label_text, "confidence": min(w["confidence"] for w in group),
                                "kind": "explicit_relative_day" if compact in {"AYER", "1SEM", "1SEMANA"} else "period_needs_calibration"}
                kind = "printed_comparison_" + str(lag) + "_days"
                if compact == "15DIAS":
                    kind = "fortnight_label_" + str(lag) + "_days"
                elif compact == "1MES":
                    kind = "month_label_" + str(lag) + "_days"
                results.append(recovery_candidate(row, printed_date, a, d, kind))
    return results


def recover_charts(days: list[str] | None, workers: int = 6):
    rows = list(csv.DictReader((ROOT / "all_extractions.csv").open()))
    rows = [row for row in rows if row["image_path"] and row["extraction_method"] == "tesseract_chart_color_roles_v1"
            and (not days or row["measurement_date"] in days)]
    all_candidates = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(recover_chart, row): row for row in rows}
        for completed, future in enumerate(as_completed(futures), 1):
            try:
                all_candidates.extend(future.result())
            except Exception as error:
                print(json.dumps({"image": futures[future]["image_path"], "error": str(error)}), flush=True)
            if completed % 25 == 0 or completed == len(rows):
                b.write_jsonl(RECOVERY / "chart_candidates.jsonl", all_candidates)
                print(json.dumps({"charts": completed, "total": len(rows), "candidates": len(all_candidates),
                                  "dates": len({r["measurement_date"] for r in all_candidates})}), flush=True)
    if days:
        print(json.dumps([{k: r[k] for k in ("measurement_date", "approval", "disapproval", "confidence", "kind")}
                          for r in all_candidates], ensure_ascii=False, indent=2), flush=True)


def pdf_url(day: str) -> str:
    stamp = date.fromisoformat(day).strftime("%d%m%Y")
    return "https://www.jefaturadegobierno.cdmx.gob.mx/storage/app/media/Sintesis%20Informativa/" + stamp + "m-primerasplanas.pdf"


def discover_scjn_pdfs(years: list[int], workers: int = 4) -> None:
    """Read the Court's public archive; use its actual PDF filenames."""
    base_url = "https://www.scjn.gob.mx"
    cache_dir = RECOVERY / "scjn_index"
    cache_dir.mkdir(parents=True, exist_ok=True)
    homepage = RECOVERY / "scjn_archive.html"
    if not homepage.is_file():
        homepage.write_bytes(b.http_get(base_url + "/multimedia/sintesis-informativa", timeout=30, retries=1))
    year_options = {int(year): value for value, year in re.findall(
        r'<option\s+value="(\d+)"[^>]*>\s*(20\d{2})\s*</option>', homepage.read_text())}
    def fetch_page(year, page):
        cache = cache_dir / f"{year}_{page:02d}.html"
        if not cache.is_file():
            query = urllib.parse.urlencode({"field_fecha_sintesis_informativa_value": year_options[year], "page": page})
            cache.write_bytes(b.http_get(base_url + "/multimedia/sintesis-informativa?" + query, timeout=30, retries=1))
        records = []
        for link in re.findall(r'href="([^"]+\.pdf[^"]*)"', cache.read_text()):
            link = html.unescape(link)
            match = re.search(r"(\d{2})(" + "|".join(b.SPANISH_MONTHS) + r")(20\d{2})", link, re.I)
            if not match:
                continue
            try:
                day = date(int(match[3]), b.SPANISH_MONTHS[match[2].lower()], int(match[1])).isoformat()
            except ValueError:
                continue
            url = urllib.parse.quote(urllib.parse.urljoin(base_url, link), safe=":/?&=%")
            records.append({"date": day, "url": url, "index_page": page, "index_year": year})
        return records
    records = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_page, year, page): (year, page)
                   for year in years if year in year_options for page in range(14)}
        for future in as_completed(futures):
            try:
                records.extend(future.result())
            except Exception as error:
                print(json.dumps({"index": futures[future], "error": str(error)}), flush=True)
            unique = {r["url"]: r for r in records}
            b.write_jsonl(RECOVERY / "scjn_pdf_index.jsonl", sorted(unique.values(), key=lambda r: r["date"]))
    print(json.dumps({"indexed_pdfs": len(unique), "years": years}), flush=True)


def download_pdf(day: str, url: str | None = None) -> dict:
    url = url or pdf_url(day)
    tag = urllib.parse.urlsplit(url).hostname.replace(".", "_") + "_" + hashlib.sha1(url.encode()).hexdigest()[:8]
    target = RECOVERY / "pdfs" / (day + "_" + tag + ".pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not target.is_file():
            raw = b.http_get(url, timeout=35, retries=0)
            if not raw.startswith(b"%PDF"):
                raise ValueError("Response is not a PDF")
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(raw)
            temporary.replace(target)
        bbox = target.with_suffix(".html")
        if not bbox.is_file():
            subprocess.run(["pdftotext", "-bbox-layout", str(target), str(bbox)],
                           check=True, capture_output=True)
        tree = ET.parse(bbox)
        pages = []
        for page_number, page in enumerate(tree.iter("{http://www.w3.org/1999/xhtml}page"), 1):
            lines = []
            for line in page.iter("{http://www.w3.org/1999/xhtml}line"):
                words = [{"text": word.text or "", **{k: float(v) for k, v in word.attrib.items()}}
                         for word in line.iter("{http://www.w3.org/1999/xhtml}word")]
                text = " ".join(w["text"] for w in words)
                lines.append({"text": text, "words": words, **{k: float(v) for k, v in line.attrib.items()}})
            if any("trackingpoll" in row["text"].lower().replace(" ", "") for row in lines):
                pages.append({"page": page_number, "width": float(page.attrib["width"]),
                              "height": float(page.attrib["height"]), "lines": lines})
        analysis = target.with_suffix(".json")
        analysis.write_text(json.dumps(pages, ensure_ascii=False, indent=2))
        return {"date": day, "url": url, "path": target.relative_to(ROOT).as_posix(), "bytes": target.stat().st_size,
                "poll_pages": [{"page": p["page"], "lines": len(p["lines"])} for p in pages]}
    except Exception as error:
        return {"date": day, "url": url, "error": str(error)}


def extract_pdf_covers():
    for pdf in sorted((RECOVERY / "pdfs").glob("*.pdf")):
        destination = RECOVERY / "pdf_pages" / pdf.stem
        destination.mkdir(parents=True, exist_ok=True)
        prefix = destination / "image"
        if not list(destination.glob("*.jpg")):
            subprocess.run(["pdfimages", "-f", "3", "-l", "25", "-j", str(pdf), str(prefix)],
                           check=True, capture_output=True)
        for path in sorted(destination.glob("*.jpg")):
            with Image.open(path) as image:
                width, height = image.size
            if height < 900 or width < 750:
                continue
            words = focused_ocr(path, (0, 0, width, int(height * .15)), "newspaper_header", psm=11)
            text = " ".join(w["text"] for w in words)
            print(json.dumps({"image": path.relative_to(ROOT).as_posix(), "header": text,
                              "economista": "CONOMISTA" in normalized(text)}), flush=True)


def find_economista_cover(record: dict) -> dict:
    """Locate the newspaper among press-review covers, preserving only its page."""
    pdf = ROOT / record["path"]
    destination = RECOVERY / "economista_covers"
    destination.mkdir(parents=True, exist_ok=True)
    metadata = destination / (pdf.stem + ".json")
    if metadata.is_file():
        previous = json.loads(metadata.read_text())
        if previous.get("cover_found") or previous.get("cover_search_version") == 2:
            return previous
    listing = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True, check=True).stdout
    pages = []
    for line in listing.splitlines()[2:]:
        columns = line.split()
        if len(columns) < 6:
            continue
        page, width, height = int(columns[0]), int(columns[3]), int(columns[4])
        if 3 <= page <= 25 and width >= 750 and height >= 900 and columns[2] == "image":
            pages.append(page)
    preferred = [13, 11, 10, 12, 9, 8, 14, 7, 6, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    result = {"date": record["date"], "url": record["url"], "pdf_path": record["path"],
              "cover_found": False, "cover_search_version": 2}
    with tempfile.TemporaryDirectory(prefix="amlo-cover-") as temporary:
        for page in sorted(set(pages), key=lambda n: preferred.index(n) if n in preferred else 99):
            prefix = Path(temporary) / f"page-{page}"
            subprocess.run(["pdfimages", "-f", str(page), "-l", str(page), "-png", str(pdf), str(prefix)],
                           capture_output=True, check=True)
            for path in sorted(Path(temporary).glob(f"page-{page}-*.png")):
                with Image.open(path) as image:
                    width, height = image.size
                if width < 750 or height < 900:
                    continue
                # Unique basename prevents OCR cache collisions across PDF dates.
                renamed = path.with_name(pdf.stem + "_" + path.name)
                path.rename(renamed)
                words = focused_ocr(renamed, (0, 0, width, int(height * .17)), "cover_header")
                header = normalized(" ".join(w["text"] for w in words))
                title_matches = any(SequenceMatcher(None, re.sub(r"[^A-Z@]", "", normalized(w["text"])), "ECONOMISTA").ratio() >= .78
                                    for w in words if w["height"] > 15)
                if "CONOMISTA" not in header and not title_matches:
                    continue
                target = destination / (pdf.stem + ".png")
                with Image.open(renamed) as image:
                    image.save(target)
                result.update({"cover_found": True, "page": page, "image_path": target.relative_to(ROOT).as_posix(),
                               "header": header, "width": width, "height": height})
                metadata.write_text(json.dumps(result, ensure_ascii=False, indent=2))
                return result
    metadata.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def find_pdf_covers(workers=4):
    reports = [json.loads(line) for line in (RECOVERY / "pdf_download_report.jsonl").read_text().splitlines()]
    records = [r for r in reports if r.get("path") and "scjn.gob.mx" in r["url"]]
    found = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(find_economista_cover, row): row for row in records}
        for future in as_completed(futures):
            try:
                result = future.result()
                found.append(result)
                print(json.dumps({"date": result["date"], "found": result["cover_found"], "page": result.get("page")}), flush=True)
            except Exception as error:
                print(json.dumps({"date": futures[future]["date"], "error": str(error)}), flush=True)
            b.write_jsonl(RECOVERY / "economista_cover_index.jsonl", sorted(found, key=lambda r: r["date"]))


def newspaper_numeric_role(image: Image.Image, word: dict) -> str:
    """Newspaper agreement is gold, whereas online charts use green."""
    x0, x1 = int(word["left"]), int(word["left"] + word["width"])
    y = int(word["top"] + word["height"] * .7)
    for distance in (12, 24, 45, 70):
        for left, right in ((max(0, x0-distance), x0), (x1, min(image.width, x1+distance))):
            crop = image.crop((left, y, right, min(image.height, y + max(2, int(word["height"] * .2)))))
            gold = red = 0
            for r, g, bl in getattr(crop, "get_flattened_data", crop.getdata)():
                gold += int(150 < r < 250 and 110 < g < r - 15 and bl < g - 40)
                red += int(r > 100 and r > g * 1.6 and r > bl * 1.4)
            minimum = max(3, crop.width * crop.height * .12)
            if gold > minimum and gold > red * 3:
                return "approval"
            if red > minimum and red > gold * 3:
                return "disapproval"
    return "unknown"


def cover_heading_words(words, height):
    """Find the poll title itself, avoiding unrelated words in a noisy OCR line."""
    return [w for w in words if w["top"] > height * .25 and w["height"] > 8
            and SequenceMatcher(None, re.sub(r"[^A-Z]", "", normalized(w["text"])), "AMLOTRACKINGPOLL").ratio() >= .76]


def recover_cover(record: dict) -> list[dict]:
    path = ROOT / record["image_path"]
    with Image.open(path) as source:
        image = source.convert("RGB")
    width, height = image.size
    full_words = full_ocr(path)
    headings = [[w] for w in cover_heading_words(full_words, height)]
    results = []
    for heading in headings:
        left = max(0, int(min(w["left"] for w in heading) - width * .015))
        right = min(width, max(int(max(w["left"] + w["width"] for w in heading) + width * .07), int(left + width * .24)))
        top = int(min(w["top"] for w in heading))
        bottom = min(height, int(top + height * .33))
        box = (left, top, right, bottom)
        words = [w for w in full_words if left <= w["left"] < right and top <= w["top"] < bottom]
        words += focused_ocr(path, box, "poll_column_v3")
        # A second reading focuses on numerals but date words remain from normal OCR.
        words += focused_ocr(path, box, "poll_column_numeric_v3", numbers=True)
        dates = explicit_dates(words, date.fromisoformat(record["date"]), width, height)
        labels = decimal_labels(words)
        for printed_date in dates:
            if not left <= printed_date["x"] <= right or printed_date["y"] < top + 50:
                continue
            lag = (date.fromisoformat(record["date"]) - date.fromisoformat(printed_date["date"])).days
            if lag not in {0, 28, 29, 30, 31}:
                continue
            side = "left" if printed_date["x"] < (left + right) / 2 else "right"
            candidates = [w for w in labels if top + 30 < w["y"] < printed_date["y"] - 5
                          and (w["x"] < left + (right-left)*.4 if side == "left" else w["x"] > left+(right-left)*.6)]
            for word in candidates:
                word["role"] = newspaper_numeric_role(image, word)
            approved = [w for w in candidates if w["role"] == "approval"]
            rejected = [w for w in candidates if w["role"] == "disapproval"]
            pairs = [(a, d) for a in approved for d in rejected if 97 <= a["value"]+d["value"] <= 101
                     and abs(a["x"]-d["x"]) < (right-left)*.15]
            if pairs:
                a, d = max(pairs, key=lambda pair: min(pair[0]["confidence"], pair[1]["confidence"]))
                source_row = {"article_url": record["url"]+"#page="+str(record["page"]), "image_url": record["url"]+"#page="+str(record["page"]),
                              "image_path": record["image_path"], "publication_date": record["date"],
                              "measurement_date": record["date"], "archive_url": record["url"]}
                candidate = recovery_candidate(source_row, printed_date, a, d, "newspaper_cover_explicit_date")
                candidate["evidence"]["crop_box"] = box
                results.append(candidate)
    return results


def recover_covers(workers=4):
    records = [json.loads(s) for s in (RECOVERY / "economista_cover_index.jsonl").read_text().splitlines()]
    records = [r for r in records if r["cover_found"]]
    candidates = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(recover_cover, r): r for r in records}
        for future in as_completed(futures):
            try:
                extracted = future.result()
                candidates.extend(extracted)
                print(json.dumps({"date": futures[future]["date"], "candidates": len(extracted)}), flush=True)
            except Exception as error:
                print(json.dumps({"date": futures[future]["date"], "error": str(error)}), flush=True)
            b.write_jsonl(RECOVERY / "pdf_candidates.jsonl", candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--dates", nargs="*")
    parser.add_argument("--charts", action="store_true")
    parser.add_argument("--urls", nargs="*")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--standard-agent", action="store_true")
    parser.add_argument("--pdf-pages", action="store_true")
    parser.add_argument("--scjn-index", action="store_true")
    parser.add_argument("--years", nargs="+", type=int, default=[2022, 2023, 2024])
    parser.add_argument("--scjn-missing", action="store_true")
    parser.add_argument("--find-covers", action="store_true")
    parser.add_argument("--ocr-covers", action="store_true")
    args = parser.parse_args()
    if args.standard_agent:
        b.USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"
    if args.scjn_index:
        discover_scjn_pdfs(args.years, min(args.workers, 4))
        return
    if args.find_covers:
        find_pdf_covers(min(args.workers, 4))
        return
    if args.ocr_covers:
        recover_covers(min(args.workers, 4))
        return
    if args.pdf_pages:
        extract_pdf_covers()
        return
    if args.charts:
        if args.probe:
            chart_probe(args.dates or ["2019-05-23", "2019-09-17", "2021-06-07", "2023-10-05"])
        else:
            recover_charts(args.dates, args.workers)
        return
    if args.scjn_missing:
        requested = set(args.dates or [r["date"] for r in csv.DictReader((ROOT / "daily_coverage.csv").open())
                                      if r["status"] == "no_observation_found" and int(r["weekday"]) <= 5])
        index = [json.loads(s) for s in (RECOVERY / "scjn_pdf_index.jsonl").read_text().splitlines()]
        targets = [(r["date"], r["url"]) for r in index if r["date"] in requested]
        print(json.dumps({"requested_dates": len(requested), "pdf_urls": len(targets)}), flush=True)
    else:
        dates = args.dates or ["2023-09-05", "2024-05-24", "2020-06-03"]
        targets = [(day, args.urls[i] if args.urls else None) for i, day in enumerate(dates)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(download_pdf, day, url): day for day, url in targets}
        for future in as_completed(futures):
            result = future.result()
            report_path = RECOVERY / "pdf_download_report.jsonl"
            previous = [json.loads(line) for line in report_path.read_text().splitlines()] if report_path.is_file() else []
            combined = {row["url"]: row for row in [*previous, result]}
            b.write_jsonl(report_path, combined.values())
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
