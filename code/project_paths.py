"""Path helpers for code that reads from and writes to the Dropbox Media tree."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_MEDIA_ROOT = Path(r"C:\Users\Dell\Dropbox\Media")


def _load_dotenv() -> None:
    """Load simple KEY=VALUE pairs from the repo .env file without extra dependencies."""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def media_root() -> Path:
    """Return the configured Dropbox Media root."""
    return Path(os.environ.get("MEDIA_ROOT", DEFAULT_MEDIA_ROOT)).expanduser()


def required_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return value


def env_list(name: str) -> list[str]:
    """Return a comma- or semicolon-separated environment variable as a list."""
    value = required_env(name)
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def _relative_parts(parts: tuple[str | os.PathLike[str], ...]) -> tuple[Path, ...]:
    relative_parts = tuple(Path(part) for part in parts)
    absolute_parts = [str(part) for part in relative_parts if part.is_absolute()]
    if absolute_parts:
        raise ValueError(
            "Media paths must be relative to MEDIA_ROOT, not absolute: "
            + ", ".join(absolute_parts)
        )
    return relative_parts


def media_path(*parts: str | os.PathLike[str], must_exist: bool = False) -> Path:
    """Return a path inside MEDIA_ROOT."""
    path = media_root().joinpath(*_relative_parts(parts))
    if must_exist and not path.exists():
        raise FileNotFoundError(f"Media path does not exist: {path}")
    return path


def media_input_path(*parts: str | os.PathLike[str]) -> Path:
    """Return an existing input path inside MEDIA_ROOT."""
    return media_path(*parts, must_exist=True)


def media_output_path(*parts: str | os.PathLike[str]) -> Path:
    """Return an output path inside MEDIA_ROOT, creating its parent directory."""
    path = media_path(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def relative_to_media(path: str | os.PathLike[str]) -> Path:
    """Return a path relative to MEDIA_ROOT."""
    return Path(path).resolve().relative_to(media_root().resolve())
