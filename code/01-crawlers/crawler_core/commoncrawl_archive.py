"""Read SDP Noticias URLs directly from Common Crawl's public CDXJ files."""

from __future__ import annotations

import gzip
import json
import time
from functools import lru_cache
from urllib.parse import parse_qs, urlparse

import requests
import urllib3


DATA_ROOT = "https://data.commoncrawl.org/cc-index/collections"
ALTERNATE_DATA_ROOT = "https://ds5q9oxwqwsfj.cloudfront.net/cc-index/collections"
SDP_SURT_PREFIX = b"com,sdpnoticias)"
INDEX_CHUNK_SIZE = 65_536
MAX_REQUEST_ATTEMPTS = 5


def fetch_sdp_archive_query(query_url: str, timeout: float, *, body_text_limit: int) -> dict[str, object]:
    """Answer an SDP CDX query from the public index files when the API is unavailable."""
    parsed = urlparse(query_url)
    index_id = parsed.path.strip("/").removesuffix("-index")
    params = parse_qs(parsed.query)
    requested_url = params.get("url", [""])[0]
    requested = urlparse(f"http://{requested_url}")
    if requested.hostname not in {"sdpnoticias.com", "www.sdpnoticias.com"}:
        raise ValueError(f"Unsupported archive query host: {requested.hostname}")
    limit = int(params.get("limit", ["50000"])[0])
    records = load_sdp_archive_records(index_id, timeout)
    prefix = requested.path
    lines = []
    size = 0
    for record in records:
        article_url = urlparse(str(record.get("url", "")))
        if article_url.hostname != requested.hostname or not article_url.path.startswith(prefix):
            continue
        line = json.dumps(record, ensure_ascii=False) + "\n"
        if size + len(line) > body_text_limit:
            break
        lines.append(line)
        size += len(line)
        if len(lines) >= limit:
            break
    return {
        "status": 200,
        "final_url": query_url,
        "content_type": "application/x-ndjson",
        "text": "".join(lines),
        "error": None,
    }


@lru_cache(maxsize=2)
def load_sdp_archive_records(index_id: str, timeout: float) -> tuple[dict[str, object], ...]:
    """Load only the gzip blocks containing SDP's SURT keys in one crawl."""
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    index_root = f"{DATA_ROOT}/{index_id}/indexes"
    cluster_url = f"{index_root}/cluster.idx"
    index_size = head_content_length(session, cluster_url, timeout)
    blocks = find_sdp_blocks(session, cluster_url, index_size, timeout)
    records: list[dict[str, object]] = []
    for filename, offset, length in blocks:
        compressed = read_range(session, f"{index_root}/{filename}", offset, offset + length - 1, timeout)
        for line in gzip.decompress(compressed).splitlines():
            if not line.startswith(SDP_SURT_PREFIX):
                continue
            parts = line.split(b" ", 2)
            if len(parts) != 3:
                continue
            try:
                record = json.loads(parts[2])
            except json.JSONDecodeError:
                continue
            if str(record.get("status")) != "200" or record.get("mime") != "text/html":
                continue
            record["timestamp"] = parts[1].decode("ascii")
            records.append(record)
    return tuple(records)


def find_sdp_blocks(
    session: requests.Session, cluster_url: str, index_size: int, timeout: float
) -> list[tuple[str, int, int]]:
    """Locate SDP's compressed blocks through HTTP range reads of cluster.idx."""
    low, high = 0, index_size
    while high - low > INDEX_CHUNK_SIZE:
        middle = (low + high) // 2
        sample = read_range(
            session, cluster_url, middle, min(index_size - 1, middle + 8191), timeout
        )
        complete_lines = sample.split(b"\n", 2)
        if len(complete_lines) < 3:
            raise ValueError("Short Common Crawl cluster index sample")
        key = complete_lines[1].split(b" ", 1)[0]
        if key < SDP_SURT_PREFIX:
            low = middle
        else:
            high = middle

    offset = max(0, low - INDEX_CHUNK_SIZE)
    first_chunk = True
    carry = b""
    preceding: tuple[str, int, int] | None = None
    matches: list[tuple[str, int, int]] = []
    while offset < index_size:
        end = min(index_size - 1, offset + INDEX_CHUNK_SIZE - 1)
        chunk = read_range(session, cluster_url, offset, end, timeout)
        lines = (carry + chunk).split(b"\n")
        carry = lines.pop()
        if first_chunk and offset:
            lines = lines[1:]
        first_chunk = False
        for line in lines:
            key = line.split(b" ", 1)[0]
            block = parse_cluster_block(line)
            if block is None:
                continue
            if key < SDP_SURT_PREFIX:
                preceding = block
            elif key.startswith(SDP_SURT_PREFIX):
                matches.append(block)
            else:
                return ([preceding] if preceding else []) + matches
        offset = end + 1
    return ([preceding] if preceding else []) + matches


def parse_cluster_block(line: bytes) -> tuple[str, int, int] | None:
    columns = line.split(b"\t")
    if len(columns) < 4:
        return None
    return columns[1].decode("ascii"), int(columns[2]), int(columns[3])


def read_range(
    session: requests.Session, url: str, start: int, end: int, timeout: float
) -> bytes:
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            request_url = archive_url_for_attempt(url, attempt)
            response = session.get(
                request_url,
                headers={"Range": f"bytes={start}-{end}"},
                timeout=timeout,
                verify=False,
            )
            response.raise_for_status()
            if response.status_code != 206 or len(response.content) != end - start + 1:
                raise ValueError(
                    f"Common Crawl did not honor byte range {start}-{end}: {response.status_code}"
                )
            return response.content
        except (requests.RequestException, ValueError):
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(min(0.5 * 2**attempt, 4))
    raise AssertionError("unreachable")


def head_content_length(session: requests.Session, url: str, timeout: float) -> int:
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        try:
            response = session.head(
                archive_url_for_attempt(url, attempt), timeout=timeout, verify=False
            )
            response.raise_for_status()
            return int(response.headers["Content-Length"])
        except (requests.RequestException, KeyError, ValueError):
            if attempt == MAX_REQUEST_ATTEMPTS - 1:
                raise
            time.sleep(min(0.5 * 2**attempt, 4))
    raise AssertionError("unreachable")


def archive_url_for_attempt(url: str, attempt: int) -> str:
    if attempt % 2 and url.startswith(DATA_ROOT):
        return url.replace(DATA_ROOT, ALTERNATE_DATA_ROOT, 1)
    return url
