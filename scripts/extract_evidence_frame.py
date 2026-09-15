#!/usr/bin/env python3
"""Extract one original-resolution offline evidence frame at an exact time."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract a full-resolution evidence frame")
    parser.add_argument("--input", required=True)
    parser.add_argument("--timestamp-ms", required=True, type=int)
    parser.add_argument("--output", required=True)
    parser.add_argument("--ffmpeg", default=os.environ.get("FFMPEG_BIN", "ffmpeg"))
    args = parser.parse_args()
    if args.timestamp_ms < 0:
        parser.error("--timestamp-ms cannot be negative")
    ffmpeg = shutil.which(args.ffmpeg) or (args.ffmpeg if Path(args.ffmpeg).is_file() else None)
    if not ffmpeg:
        print("ffmpeg was not found. Set FFMPEG_BIN or provide --ffmpeg.", file=sys.stderr)
        return 2
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{args.timestamp_ms / 1000:.3f}",
        "-i", args.input,
        "-frames:v", "1",
        "-q:v", "2",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode != 0 or not output.is_file():
        print(result.stderr.strip() or "evidence-frame extraction failed", file=sys.stderr)
        return result.returncode or 1
    print(f"Wrote evidence frame: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
