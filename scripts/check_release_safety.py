#!/usr/bin/env python3
"""Fail when a release tree contains likely secrets, personal paths, or media."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


IGNORED_DIRS = {
    ".git",
    ".product-video-remake-cache",
    ".pytest_cache",
    "__pycache__",
    "analysis-pack",
    "generated",
    "high-fidelity-package",
    "output",
    "outputs",
}

BLOCKED_SUFFIXES = {
    ".avi",
    ".env",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".pem",
    ".pfx",
    ".pyc",
    ".wav",
    ".webm",
}

TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}

CONTENT_RULES = (
    (
        "Windows user directory",
        re.compile(r"[A-Za-z]:[\\/]Users[\\/](?!<|%|\{)[^\\/\s\"']+[\\/]", re.IGNORECASE),
    ),
    (
        "Unix home directory",
        re.compile(r"/(?:Users|home)/(?!<|\$|\{)[^/\s\"']+/", re.IGNORECASE),
    ),
    (
        "private key",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "likely assigned secret",
        re.compile(
            r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)"
            r"\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
    ),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    ("OpenAI-style secret", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
)


def iter_release_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRS for part in relative.parts):
            continue
        yield path, relative


def audit(root: Path) -> list[str]:
    findings: list[str] = []
    this_script = Path(__file__).resolve()
    for path, relative in iter_release_files(root):
        suffix = path.suffix.lower()
        if suffix in BLOCKED_SUFFIXES:
            findings.append(f"blocked file type: {relative}")
            continue
        if suffix not in TEXT_SUFFIXES or path.resolve() == this_script:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF-8 text file: {relative}")
            continue
        for label, pattern in CONTENT_RULES:
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                findings.append(f"{label}: {relative}:{line}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a skill tree before publishing it")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    findings = audit(root)
    if findings:
        print("Release safety audit failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print(f"Release safety audit passed: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
