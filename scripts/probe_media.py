#!/usr/bin/env python3
"""Read media facts with ffprobe when available; never modifies the media."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path


def _ratio(width: int, height: int) -> str:
    known = {(16, 9): "16:9", (4, 3): "4:3", (1, 1): "1:1", (3, 4): "3:4", (9, 16): "9:16", (21, 9): "21:9"}
    if width <= 0 or height <= 0:
        return "adaptive"
    from math import gcd
    divisor = gcd(width, height)
    reduced = (width // divisor, height // divisor)
    return known.get(reduced, f"{reduced[0]}:{reduced[1]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe video duration, dimensions, frame rate, and audio")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    parser.add_argument("--ffprobe", default=os.environ.get("FFPROBE_BIN", "ffprobe"))
    args = parser.parse_args()

    binary = shutil.which(args.ffprobe) or (args.ffprobe if Path(args.ffprobe).is_file() else None)
    if not binary:
        print("ffprobe was not found. Set FFPROBE_BIN or provide --ffprobe.", file=sys.stderr)
        return 2
    command = [
        str(binary), "-v", "error", "-show_streams", "-show_format", "-of", "json", args.input
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=False)
    if completed.returncode != 0:
        print(completed.stderr.strip() or "ffprobe failed", file=sys.stderr)
        return completed.returncode or 1
    raw = json.loads(completed.stdout)
    streams = raw.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    duration_s = float(raw.get("format", {}).get("duration") or video.get("duration") or 0)
    fps_value = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        fps = round(float(Fraction(fps_value)), 4)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    result = {
        "duration_ms": round(duration_s * 1000),
        "width": width,
        "height": height,
        "ratio": _ratio(width, height),
        "fps": fps,
        "has_audio": has_audio,
        "rotation": int((video.get("tags") or {}).get("rotate") or 0),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
