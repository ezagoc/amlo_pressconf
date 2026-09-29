#!/usr/bin/env python3
"""Archive AMLO Tracking Poll video metadata and available transcripts."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import WORK_ROOT  # noqa: E402


API_ROOT = "https://www.googleapis.com/youtube/v3"
DEFAULT_CHANNEL_HANDLE = "@ElEconomistaTV"
VERIFIED_CHANNEL_ID = "UCXmAOGwFYxIq5qrScJeeV4g"
DEFAULT_HASHTAG = "AMLOTrackingPoll"
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class YouTubeApiError(RuntimeError):
    """Represent a YouTube Data API error without exposing the API key."""

    def __init__(self, message: str, *, reason: str = ""):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Video:
    """Store the YouTube metadata needed for filtering and provenance."""

    video_id: str
    title: str
    description: str
    published_at: str
    channel_id: str
    channel_title: str
    tags: tuple[str, ...]
    duration: str
    privacy_status: str
    match_locations: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        """Return the canonical watch URL."""

        return f"https://www.youtube.com/watch?v={self.video_id}"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable record."""

        record = asdict(self)
        record["tags"] = list(self.tags)
        record["match_locations"] = list(self.match_locations)
        record["url"] = self.url
        return record


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse the simple KEY=VALUE subset shared by .env and .Renviron files."""

    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_api_key(explicit_env_file: Path | None, variable_names: Sequence[str]) -> str:
    """Load an API key without replacing variables already in the environment."""

    candidates = []
    if explicit_env_file is not None:
        candidates.append(explicit_env_file.expanduser())
    candidates.extend(
        [Path.cwd() / ".env", Path.cwd() / ".Renviron", Path.home() / ".Renviron"]
    )

    file_values: dict[str, str] = {}
    for path in candidates:
        for key, value in parse_env_file(path).items():
            file_values.setdefault(key, value)

    for name in variable_names:
        value = os.environ.get(name) or file_values.get(name)
        if value:
            return value

    checked = ", ".join(variable_names)
    raise RuntimeError(
        f"No YouTube API key found. Set one of: {checked}; or pass --env-file."
    )


class YouTubeDataApi:
    """Small dependency-free client for the read-only YouTube Data API calls."""

    def __init__(self, api_key: str, *, max_retries: int = 5, timeout: int = 30):
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout = timeout

    def get(self, resource: str, **params: Any) -> dict[str, Any]:
        """Issue a GET request with bounded exponential retry behavior."""

        query = urllib.parse.urlencode({**params, "key": self.api_key})
        url = f"{API_ROOT}/{resource}?{query}"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "amlo-tracking-poll/0.1"},
        )

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                payload = error.read().decode("utf-8", errors="replace")
                if error.code in RETRYABLE_HTTP_CODES and attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                message, reason = self._format_http_error(error.code, payload)
                raise YouTubeApiError(message, reason=reason) from error
            except urllib.error.URLError as error:
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise YouTubeApiError(f"YouTube API network error: {error.reason}") from error

        raise AssertionError("The retry loop should always return or raise")

    @staticmethod
    def _sleep(attempt: int) -> None:
        time.sleep(min(30.0, (2**attempt) + random.random()))

    @staticmethod
    def _format_http_error(status: int, payload: str) -> tuple[str, str]:
        message = payload
        reason = ""
        try:
            error = json.loads(payload).get("error", {})
            message = error.get("message", payload)
            details = error.get("errors") or []
            reason = details[0].get("reason", "") if details else ""
            detailed_reasons = [
                detail.get("reason", "")
                for detail in error.get("details", [])
                if detail.get("reason")
            ]
            if detailed_reasons:
                reason = detailed_reasons[0]
        except json.JSONDecodeError:
            pass

        hint = ""
        if reason == "API_KEY_SERVICE_BLOCKED":
            hint = (
                " Add YouTube Data API v3 to this credential's API restrictions, "
                "or use --discovery yt-dlp."
            )
        elif reason in {"accessNotConfigured", "serviceDisabled", "SERVICE_DISABLED"} or "disabled" in message.lower():
            hint = " Enable YouTube Data API v3 for the Google Cloud project, then retry."
        elif reason in {"dailyLimitExceeded", "quotaExceeded"}:
            hint = " The project's YouTube API quota is exhausted; retry after reset."
        message = message.rstrip().rstrip(".")
        return f"YouTube API HTTP {status} ({reason or 'unknown'}): {message}.{hint}", reason

    def resolve_channel(self, handle_or_id: str) -> dict[str, Any]:
        """Resolve a channel handle or ID and return its uploads playlist."""

        selector = (
            {"id": handle_or_id}
            if handle_or_id.startswith("UC")
            else {"forHandle": handle_or_id.lstrip("@")}
        )
        response = self.get(
            "channels",
            part="id,snippet,contentDetails",
            **selector,
        )
        items = response.get("items", [])
        if not items:
            raise YouTubeApiError(f"Channel not found: {handle_or_id}")
        channel = items[0]
        return {
            "channel_id": channel["id"],
            "channel_title": channel["snippet"]["title"],
            "uploads_playlist_id": channel["contentDetails"]["relatedPlaylists"]["uploads"],
        }

    def iter_upload_ids(self, playlist_id: str) -> Iterator[str]:
        """Yield every accessible video ID in a channel uploads playlist."""

        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            response = self.get("playlistItems", **params)
            for item in response.get("items", []):
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    yield video_id
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def iter_search_ids(self, channel_id: str, query: str) -> Iterator[str]:
        """Yield channel video IDs returned by a targeted metadata search."""

        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "part": "id",
                "channelId": channel_id,
                "q": query,
                "type": "video",
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            response = self.get("search", **params)
            for item in response.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                if video_id:
                    yield video_id
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    def get_videos(self, video_ids: Sequence[str]) -> list[Video]:
        """Fetch complete video metadata in API-sized batches."""

        videos: list[Video] = []
        for batch in chunks(video_ids, 50):
            response = self.get(
                "videos",
                part="snippet,contentDetails,status",
                id=",".join(batch),
                maxResults=50,
            )
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                videos.append(
                    Video(
                        video_id=item["id"],
                        title=snippet.get("title", ""),
                        description=snippet.get("description", ""),
                        published_at=snippet.get("publishedAt", ""),
                        channel_id=snippet.get("channelId", ""),
                        channel_title=snippet.get("channelTitle", ""),
                        tags=tuple(snippet.get("tags", [])),
                        duration=item.get("contentDetails", {}).get("duration", ""),
                        privacy_status=item.get("status", {}).get("privacyStatus", ""),
                    )
                )
        return videos


def chunks(values: Sequence[str], size: int) -> Iterator[Sequence[str]]:
    """Yield fixed-size slices from a sequence."""

    for start in range(0, len(values), size):
        yield values[start : start + size]


def canonical_text(value: str) -> str:
    """Normalize text so hashtag spelling variants can be matched consistently."""

    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def matching_locations(video: Video, hashtag: str, *, strict: bool) -> tuple[str, ...]:
    """Return metadata fields that contain the requested hashtag or phrase."""

    needle = hashtag.lstrip("#")
    fields: dict[str, Iterable[str]] = {
        "title": (video.title,),
        "description": (video.description,),
        "tags": video.tags,
    }
    locations: list[str] = []

    if strict:
        pattern = re.compile(rf"(?<![\w])#{re.escape(needle)}(?![\w])", re.IGNORECASE)
        for field, values in fields.items():
            if any(pattern.search(value) for value in values):
                locations.append(field)
    else:
        normalized_needle = canonical_text(needle)
        for field, values in fields.items():
            if any(normalized_needle in canonical_text(value) for value in values):
                locations.append(field)
    return tuple(locations)


def filter_videos(
    videos: Iterable[Video],
    hashtag: str,
    *,
    strict: bool,
    published_after: str | None,
    published_before: str | None,
) -> list[Video]:
    """Filter videos by metadata match and optional inclusive ISO dates."""

    matches: list[Video] = []
    for video in videos:
        day = video.published_at[:10]
        if published_after and day < published_after:
            continue
        if published_before and day > published_before:
            continue
        locations = matching_locations(video, hashtag, strict=strict)
        if locations:
            matches.append(
                Video(**{**asdict(video), "match_locations": locations})
            )
    return sorted(matches, key=lambda item: (item.published_at, item.video_id))


def javascript_runtime_options() -> dict[str, Any]:
    """Return yt-dlp configuration for the first supported runtime on PATH."""

    for runtime, executable in (
        ("deno", "deno"),
        ("node", "node"),
        ("quickjs", "qjs"),
        ("bun", "bun"),
    ):
        path = shutil.which(executable)
        if path:
            return {"js_runtimes": {runtime: {"path": path}}}
    return {}


def seconds_to_iso_duration(value: Any) -> str:
    """Convert a numeric duration to the ISO 8601 form used by the Data API."""

    if value is None:
        return ""
    total = max(0, round(float(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = "PT"
    if hours:
        parts += f"{hours}H"
    if minutes:
        parts += f"{minutes}M"
    if seconds or parts == "PT":
        parts += f"{seconds}S"
    return parts


def published_at_from_ydl(info: dict[str, Any]) -> str:
    """Create an API-compatible UTC publication timestamp from yt-dlp metadata."""

    timestamp = info.get("timestamp") or info.get("release_timestamp")
    if timestamp is not None:
        return datetime.fromtimestamp(float(timestamp), timezone.utc).isoformat().replace("+00:00", "Z")
    upload_date = info.get("upload_date") or info.get("release_date")
    if upload_date and re.fullmatch(r"\d{8}", str(upload_date)):
        return datetime.strptime(str(upload_date), "%Y%m%d").replace(tzinfo=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return ""


def video_from_ydl(info: dict[str, Any], fallback_channel_id: str = "") -> Video:
    """Map flat or full yt-dlp metadata to the common video representation."""

    return Video(
        video_id=str(info.get("id", "")),
        title=str(info.get("title") or ""),
        description=str(info.get("description") or ""),
        published_at=published_at_from_ydl(info),
        channel_id=str(info.get("channel_id") or fallback_channel_id),
        channel_title=str(info.get("channel") or info.get("uploader") or ""),
        tags=tuple(str(tag) for tag in (info.get("tags") or [])),
        duration=seconds_to_iso_duration(info.get("duration")),
        privacy_status=str(info.get("availability") or ""),
    )


def channel_videos_url(handle_or_id: str) -> str:
    """Build an explicit YouTube Videos-tab URL from a handle or channel ID."""

    if handle_or_id.startswith("UC"):
        return f"https://www.youtube.com/channel/{handle_or_id}/videos"
    handle = handle_or_id if handle_or_id.startswith("@") else f"@{handle_or_id}"
    return f"https://www.youtube.com/{handle}/videos"


def inventory_with_ytdlp(
    channel_handle: str,
    hashtag: str,
    *,
    strict: bool,
) -> tuple[dict[str, Any], list[Video], int]:
    """Inventory a channel by title when API-key restrictions block the Data API."""

    try:
        import yt_dlp
    except ImportError as error:
        raise RuntimeError("yt-dlp is missing. Run `uv sync` first.") from error

    flat_options: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignoreerrors": True,
        **javascript_runtime_options(),
    }
    url = channel_videos_url(channel_handle)
    print(f"Scanning video titles directly from {url}...")
    with yt_dlp.YoutubeDL(flat_options) as ydl:
        playlist = ydl.extract_info(url, download=False)
    if not playlist:
        raise RuntimeError(f"yt-dlp could not read the channel: {url}")

    channel_id = str(playlist.get("channel_id") or playlist.get("id") or "")
    if channel_handle == DEFAULT_CHANNEL_HANDLE and channel_id != VERIFIED_CHANNEL_ID:
        raise RuntimeError("The default handle resolved to an unexpected channel ID; refusing to continue.")

    flat_videos = [
        video_from_ydl(entry, channel_id)
        for entry in (playlist.get("entries") or [])
        if entry and entry.get("id") and entry.get("title")
    ]
    candidate_ids = [
        video.video_id
        for video in flat_videos
        if matching_locations(video, hashtag, strict=strict)
    ]
    print(
        f"Found {len(candidate_ids)} title matches among {len(flat_videos)} channel videos; "
        "fetching their full metadata..."
    )

    full_videos: dict[str, Video] = {}
    failures = 0
    metadata_options: dict[str, Any] = {
        "skip_download": True,
        "noplaylist": True,
        **javascript_runtime_options(),
    }
    with yt_dlp.YoutubeDL(metadata_options) as ydl:
        for index, video_id in enumerate(candidate_ids, start=1):
            print(f"[{index}/{len(candidate_ids)}] Reading metadata for {video_id}")
            try:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
                if info:
                    full_videos[video_id] = video_from_ydl(info, channel_id)
                else:
                    failures += 1
            except Exception as error:
                failures += 1
                print(f"WARNING: Could not read metadata for {video_id}: {error}", file=sys.stderr)

    # Preserve a complete title-level channel inventory while enriching every
    # match that could be fetched with dates, descriptions, tags, and duration.
    all_videos = [full_videos.get(video.video_id, video) for video in flat_videos]
    channel = {
        "channel_id": channel_id,
        "channel_title": str(playlist.get("channel") or playlist.get("uploader") or playlist.get("title") or ""),
        "uploads_playlist_id": f"UU{channel_id[2:]}" if channel_id.startswith("UC") else "",
        "discovery_method": "yt-dlp-title-scan",
        "metadata_fetch_failures": failures,
        "discovery_note": (
            "Fallback inventory matched channel video titles because the API key was blocked. "
            "Re-run with --discovery api after fixing the key restriction to also match descriptions and tags."
        ),
    }
    return channel, all_videos, 0


def atomic_write_text(path: Path, content: str) -> None:
    """Replace a text file atomically to preserve valid progress files."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    """Write indented UTF-8 JSON atomically."""

    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    """Write one UTF-8 JSON object per line atomically."""

    content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    atomic_write_text(path, content)


def read_video_inventory(path: Path) -> list[Video]:
    """Load videos from a JSONL inventory written by this program."""

    if not path.is_file():
        raise RuntimeError(f"Existing inventory not found: {path}")
    videos: list[Video] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            videos.append(
                Video(
                    video_id=record["video_id"],
                    title=record.get("title", ""),
                    description=record.get("description", ""),
                    published_at=record.get("published_at", ""),
                    channel_id=record.get("channel_id", ""),
                    channel_title=record.get("channel_title", ""),
                    tags=tuple(record.get("tags", [])),
                    duration=record.get("duration", ""),
                    privacy_status=record.get("privacy_status", ""),
                    match_locations=tuple(record.get("match_locations", [])),
                )
            )
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise RuntimeError(f"Invalid inventory record at {path}:{line_number}: {error}") from error
    return sorted(videos, key=lambda item: (item.published_at, item.video_id))


def write_inventory(
    output_dir: Path,
    all_videos: Sequence[Video],
    matched_videos: Sequence[Video],
    channel: dict[str, Any],
    args: argparse.Namespace,
    inaccessible_count: int,
) -> None:
    """Write complete and filtered inventories in reproducible formats."""

    inventory_dir = output_dir / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(inventory_dir / "all_uploads.jsonl", (video.to_dict() for video in all_videos))
    write_jsonl(
        inventory_dir / "matching_videos.jsonl",
        (video.to_dict() for video in matched_videos),
    )

    csv_path = inventory_dir / "matching_videos.csv"
    temporary = csv_path.with_suffix(".csv.tmp")
    fieldnames = [
        "video_id",
        "url",
        "published_at",
        "title",
        "duration",
        "privacy_status",
        "match_locations",
        "tags",
        "description",
    ]
    with temporary.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for video in matched_videos:
            record = video.to_dict()
            writer.writerow(
                {
                    key: ";".join(record[key]) if isinstance(record[key], list) else record[key]
                    for key in fieldnames
                }
            )
    temporary.replace(csv_path)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **channel,
        "hashtag": args.hashtag,
        "strict_hashtag": args.strict_hashtag,
        "published_after": args.published_after,
        "published_before": args.published_before,
        "upload_ids_seen": len(all_videos) + inaccessible_count,
        "accessible_uploads": len(all_videos),
        "inaccessible_or_deleted_uploads": inaccessible_count,
        "matching_videos": len(matched_videos),
    }
    write_json(inventory_dir / "summary.json", summary)


def caption_language(path: Path, video_id: str) -> str:
    """Infer the subtitle language from yt-dlp's deterministic filename."""

    prefix = f"{video_id}."
    name = path.name
    if name.startswith(prefix) and name.endswith(".json3"):
        language = name[len(prefix) : -len(".json3")]
        return language or "und"
    return "und"


def parse_json3_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert YouTube JSON3 caption events into clean timed text segments."""

    rows: list[dict[str, Any]] = []
    for event in payload.get("events", []):
        fragments = event.get("segs") or []
        text = "".join(str(fragment.get("utf8", "")) for fragment in fragments)
        text = html.unescape(" ".join(text.split()))
        if not text:
            continue
        rows.append(
            {
                "start_seconds": round(float(event.get("tStartMs", 0)) / 1000, 3),
                "duration_seconds": round(float(event.get("dDurationMs", 0)) / 1000, 3),
                "text": text,
            }
        )
    return rows


def format_timestamp(seconds: float) -> str:
    """Format seconds as a stable HH:MM:SS.mmm timestamp."""

    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def convert_caption_file(path: Path, output_dir: Path, video_id: str) -> tuple[Path, Path]:
    """Create readable text and machine-readable JSONL from a JSON3 track."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = parse_json3_events(payload)
    language = caption_language(path, video_id)
    text_path = output_dir / "transcripts" / "text" / f"{video_id}.{language}.txt"
    jsonl_path = output_dir / "transcripts" / "jsonl" / f"{video_id}.{language}.jsonl"

    text_content = "".join(
        f"[{format_timestamp(row['start_seconds'])}] {row['text']}\n" for row in rows
    )
    atomic_write_text(text_path, text_content)
    write_jsonl(
        jsonl_path,
        ({"video_id": video_id, "language": language, **row} for row in rows),
    )
    return text_path, jsonl_path


def relative_paths(paths: Iterable[Path], root: Path) -> list[str]:
    """Return sorted POSIX paths relative to the archive root."""

    return sorted(path.relative_to(root).as_posix() for path in paths)


def build_ydl_options(args: argparse.Namespace, output_dir: Path) -> dict[str, Any]:
    """Build yt-dlp options for captions and optional video media."""

    raw_dir = output_dir / "transcripts" / "raw"
    metadata_dir = output_dir / "metadata"
    media_dir = output_dir / "media"
    for directory in (raw_dir, metadata_dir, media_dir):
        directory.mkdir(parents=True, exist_ok=True)

    options: dict[str, Any] = {
        "noplaylist": True,
        "skip_download": not args.download_videos,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": [part.strip() for part in args.subtitle_langs.split(",") if part.strip()],
        "subtitlesformat": "json3",
        "writeinfojson": True,
        "outtmpl": {
            "default": str(media_dir / "%(upload_date)s_%(id)s_%(title).150B.%(ext)s"),
            "subtitle": str(raw_dir / "%(id)s.%(ext)s"),
            "infojson": str(metadata_dir / "%(id)s.%(ext)s"),
        },
        "continuedl": True,
        "overwrites": False,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": args.concurrent_fragments,
    }
    # YouTube now presents JavaScript challenges during extraction.
    options.update(javascript_runtime_options())
    if args.download_videos:
        options.update({"format": args.video_format, "merge_output_format": "mp4"})
    if args.cookies:
        options["cookiefile"] = str(args.cookies.expanduser())
    if args.cookies_from_browser:
        options["cookiesfrombrowser"] = (args.cookies_from_browser, None, None, None)
    return options


def download_videos(
    videos: Sequence[Video], args: argparse.Namespace, output_dir: Path
) -> list[dict[str, Any]]:
    """Download selected videos one at a time and checkpoint the report."""

    try:
        import yt_dlp
    except ImportError as error:
        raise RuntimeError("yt-dlp is missing. Run `uv sync` first.") from error

    report_path = output_dir / "download_report.json"
    report: list[dict[str, Any]] = []
    ydl_options = build_ydl_options(args, output_dir)

    for index, video in enumerate(videos, start=1):
        print(f"[{index}/{len(videos)}] Processing {video.video_id}: {video.title}")
        record: dict[str, Any] = {
            "video_id": video.video_id,
            "url": video.url,
            "title": video.title,
            "status": "pending",
            "error": None,
            "raw_subtitles": [],
            "text_transcripts": [],
            "jsonl_transcripts": [],
            "media_files": [],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                result = ydl.download([video.url])
            if result != 0:
                raise RuntimeError(f"yt-dlp returned exit code {result}")

            raw_files = sorted(
                (output_dir / "transcripts" / "raw").glob(f"{video.video_id}*.json3")
            )
            text_files: list[Path] = []
            jsonl_files: list[Path] = []
            for raw_file in raw_files:
                text_file, jsonl_file = convert_caption_file(raw_file, output_dir, video.video_id)
                text_files.append(text_file)
                jsonl_files.append(jsonl_file)

            media_files = [
                path
                for path in (output_dir / "media").glob(f"*{video.video_id}*")
                if path.is_file() and path.suffix not in {".part", ".ytdl"}
            ]
            record.update(
                {
                    "status": "downloaded" if raw_files else "no_transcript_available",
                    "raw_subtitles": relative_paths(raw_files, output_dir),
                    "text_transcripts": relative_paths(text_files, output_dir),
                    "jsonl_transcripts": relative_paths(jsonl_files, output_dir),
                    "media_files": relative_paths(media_files, output_dir),
                }
            )
        except Exception as error:  # Continue so one unavailable video does not lose the batch.
            record.update({"status": "error", "error": str(error)})
            print(f"ERROR: {video.video_id}: {error}", file=sys.stderr)
            if args.fail_fast:
                report.append(record)
                write_json(report_path, report)
                raise
        report.append(record)
        write_json(report_path, report)
    return report


def valid_iso_date(value: str) -> str:
    """Validate an inclusive YYYY-MM-DD command-line date."""

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as error:
        raise argparse.ArgumentTypeError("Date must use YYYY-MM-DD format") from error
    return value


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line interface."""

    parser = argparse.ArgumentParser(
        description="Download #AMLOTrackingPoll metadata, captions, and optional videos."
    )
    parser.add_argument("--channel", default=DEFAULT_CHANNEL_HANDLE, help="YouTube handle or UC... ID")
    parser.add_argument("--hashtag", default=DEFAULT_HASHTAG, help="Hashtag or phrase to match")
    parser.add_argument(
        "--strict-hashtag",
        action="store_true",
        help="Require a literal #hashtag instead of accepting spacing variants",
    )
    parser.add_argument("--published-after", type=valid_iso_date, help="Inclusive YYYY-MM-DD filter")
    parser.add_argument("--published-before", type=valid_iso_date, help="Inclusive YYYY-MM-DD filter")
    parser.add_argument("--output-dir", type=Path, default=WORK_ROOT / "youtube")
    parser.add_argument(
        "--discovery",
        choices=("auto", "api", "yt-dlp"),
        default="auto",
        help="Inventory method; auto falls back to a title scan when the API key is blocked",
    )
    parser.add_argument("--env-file", type=Path, help="Additional .env or .Renviron file")
    parser.add_argument(
        "--api-key-env",
        action="append",
        dest="api_key_envs",
        help="API-key variable name; may be repeated",
    )
    parser.add_argument("--inventory-only", action="store_true", help="Do not download captions or media")
    parser.add_argument(
        "--use-existing-inventory",
        action="store_true",
        help="Skip discovery and download from the existing inventory in Media",
    )
    parser.add_argument("--download-videos", action="store_true", help="Also download video media")
    parser.add_argument(
        "--subtitle-langs",
        default="es.*,es,-live_chat",
        help="Comma-separated yt-dlp subtitle language selectors",
    )
    parser.add_argument(
        "--video-format",
        default="bv*[height<=720]+ba/b[height<=720]/b",
        help="yt-dlp format selector used with --download-videos",
    )
    parser.add_argument("--cookies", type=Path, help="Netscape-format cookies file")
    parser.add_argument(
        "--cookies-from-browser",
        help="Browser name from which yt-dlp should load cookies, such as chrome or firefox",
    )
    parser.add_argument(
        "--concurrent-fragments",
        type=int,
        default=4,
        help="Concurrent fragments per video (default: 4)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Download only the first N chronological matches; inventory remains complete",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first download error")
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute inventory, filtering, and optional downloads."""

    if args.concurrent_fragments < 1:
        raise RuntimeError("--concurrent-fragments must be at least 1")
    if args.limit is not None and args.limit < 1:
        raise RuntimeError("--limit must be at least 1")
    if args.published_after and args.published_before:
        if args.published_after > args.published_before:
            raise RuntimeError("--published-after cannot be later than --published-before")

    output_dir = args.output_dir.resolve()
    if args.use_existing_inventory:
        matched_videos = read_video_inventory(
            output_dir / "inventory" / "matching_videos.jsonl"
        )
        print(f"Loaded {len(matched_videos)} videos from the existing inventory.")
        if args.inventory_only:
            return 0
        videos_to_download = (
            matched_videos[: args.limit] if args.limit is not None else matched_videos
        )
        if args.limit is not None:
            print(f"Limiting downloads to {len(videos_to_download)} chronological matches.")
        report = download_videos(videos_to_download, args, output_dir)
        errors = sum(item["status"] == "error" for item in report)
        missing = sum(item["status"] == "no_transcript_available" for item in report)
        print(
            f"Finished: {len(report) - errors} processed, {missing} without captions, "
            f"{errors} errors."
        )
        return 1 if errors else 0

    channel: dict[str, Any]
    all_videos: list[Video]
    inaccessible_count: int
    if args.discovery in {"auto", "api"}:
        try:
            variable_names = args.api_key_envs or [
                "YT_API_KEY",
                "YOUTUBE_API_KEY",
                "GOOGLE_API_KEY",
            ]
            api_key = load_api_key(args.env_file, variable_names)
            api = YouTubeDataApi(api_key)
            channel = api.resolve_channel(args.channel)
            if args.channel == DEFAULT_CHANNEL_HANDLE and channel["channel_id"] != VERIFIED_CHANNEL_ID:
                raise RuntimeError(
                    "The default handle resolved to an unexpected channel ID; refusing to continue."
                )
            channel["discovery_method"] = "youtube-data-api"
            print(
                f"Inventorying all uploads from {channel['channel_title']} "
                f"({channel['channel_id']})..."
            )
            upload_ids = list(api.iter_upload_ids(channel["uploads_playlist_id"]))
            search_ids = list(api.iter_search_ids(channel["channel_id"], args.hashtag))
            combined_ids = list(dict.fromkeys([*upload_ids, *search_ids]))
            channel["uploads_playlist_ids"] = len(upload_ids)
            channel["search_candidate_ids"] = len(set(search_ids))
            all_videos = api.get_videos(combined_ids)
            inaccessible_count = len(combined_ids) - len(all_videos)
        except (RuntimeError, YouTubeApiError) as error:
            if args.discovery == "api":
                raise
            print(f"WARNING: API discovery failed: {error}", file=sys.stderr)
            print("Falling back to a direct yt-dlp title scan.", file=sys.stderr)
            channel, all_videos, inaccessible_count = inventory_with_ytdlp(
                args.channel,
                args.hashtag,
                strict=args.strict_hashtag,
            )
    else:
        channel, all_videos, inaccessible_count = inventory_with_ytdlp(
            args.channel,
            args.hashtag,
            strict=args.strict_hashtag,
        )

    all_videos.sort(key=lambda item: (item.published_at, item.video_id))
    matched_videos = filter_videos(
        all_videos,
        args.hashtag,
        strict=args.strict_hashtag,
        published_after=args.published_after,
        published_before=args.published_before,
    )
    write_inventory(
        output_dir,
        all_videos,
        matched_videos,
        channel,
        args,
        inaccessible_count,
    )
    print(
        f"Found {len(matched_videos)} matching videos among {len(all_videos)} accessible uploads."
    )
    print(f"Inventory written to {output_dir / 'inventory'}")

    if args.inventory_only:
        return 0
    videos_to_download = matched_videos[: args.limit] if args.limit is not None else matched_videos
    if args.limit is not None:
        print(f"Limiting downloads to {len(videos_to_download)} chronological matches.")
    report = download_videos(videos_to_download, args, output_dir)
    errors = sum(item["status"] == "error" for item in report)
    missing = sum(item["status"] == "no_transcript_available" for item in report)
    print(f"Finished: {len(report) - errors} processed, {missing} without captions, {errors} errors.")
    return 1 if errors else 0


def main() -> int:
    """Parse arguments and render concise command-line errors."""

    args = build_parser().parse_args()
    try:
        return run(args)
    except (RuntimeError, YouTubeApiError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
