#!/usr/bin/env python3
"""Build a cached, fidelity-preserving reference-video analysis pack.

The source video is decoded once to create dense evidence frames, cut/baseline
frames, and analysis-only audio. Compact overview sheets are generated from the
dense evidence so a vision model can understand the whole timeline with fewer
image reads, then inspect original evidence frames only where detail matters.

Nothing created here is an online Seedance reference asset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ANALYZER_VERSION = "1.3.0"
PTS_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def _resolve_binary(value: str) -> str | None:
    return shutil.which(value) or (value if Path(value).is_file() else None)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _file_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "resolved_path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _cache_key(signature: dict[str, Any], settings: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"analyzer_version": ANALYZER_VERSION, "source": signature, "settings": settings},
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:24]


def _manifest_outputs_exist(manifest: dict[str, Any]) -> bool:
    required_paths: list[str] = []
    required_paths.extend(str(item) for item in manifest.get("dense_frames", []))
    required_paths.extend(str(item) for item in manifest.get("cut_candidate_frames", []))
    required_paths.extend(
        str(item.get("path"))
        for item in manifest.get("overview_sheets", [])
        if isinstance(item, dict) and item.get("path")
    )
    audio = manifest.get("analysis_audio")
    if audio:
        required_paths.append(str(audio))
    return bool(manifest.get("dense_frames")) and all(Path(item).is_file() for item in required_paths)


def _read_valid_manifest(path: Path, cache_key: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if manifest.get("cache_key") != cache_key or not _manifest_outputs_exist(manifest):
        return None
    return manifest


def _find_ffprobe(ffmpeg: str, configured: str) -> str | None:
    resolved = _resolve_binary(configured)
    if resolved:
        return resolved
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(sibling) if sibling.is_file() else None


def _has_audio(input_path: str, ffprobe: str | None) -> bool | None:
    if not ffprobe:
        return None
    result = _run([
        ffprobe,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        input_path,
    ])
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def _dense_filter(dense_fps: float, max_width: int) -> str:
    filters = [f"fps={dense_fps}"]
    if max_width > 0:
        filters.append(f"scale='min(iw,{max_width})':-2:force_original_aspect_ratio=decrease")
    return ",".join(filters)


def _clean_generated_images(directory: Path, pattern: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()


def _create_overview_sheets(
    ffmpeg: str,
    dense_dir: Path,
    sheet_dir: Path,
    frame_count: int,
    dense_fps: float,
    columns: int,
    rows: int,
    cell_width: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    _clean_generated_images(sheet_dir, "overview-*.jpg")
    if frame_count <= 0:
        return [], ["overview sheets were not created because no dense frames exist"]
    per_sheet = columns * rows
    sheet_count = (frame_count + per_sheet - 1) // per_sheet
    padding_frames = (per_sheet - frame_count % per_sheet) % per_sheet
    filters = [f"scale={cell_width}:-2:force_original_aspect_ratio=decrease"]
    if padding_frames:
        filters.append(f"tpad=stop_mode=clone:stop_duration={padding_frames / dense_fps:.6f}")
    filters.append(f"tile={columns}x{rows}:nb_frames={per_sheet}:padding=4:margin=4:color=black")
    command = [
        ffmpeg,
        "-hide_banner", "-loglevel", "error", "-y",
        "-framerate", str(dense_fps),
        "-start_number", "1",
        "-i", str(dense_dir / "frame-%06d.jpg"),
        "-vf", ",".join(filters),
        "-frames:v", str(sheet_count),
        "-fps_mode", "vfr",
        "-q:v", "3",
        str(sheet_dir / "overview-%03d.jpg"),
    ]
    result = _run(command)
    generated = sorted(sheet_dir.glob("overview-*.jpg"))
    if result.returncode != 0 or len(generated) != sheet_count:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown ffmpeg error"
        return [], [f"overview sheet batch failed: {detail}"]

    sheets: list[dict[str, Any]] = []
    for sheet_index, output in enumerate(generated):
        offset = sheet_index * per_sheet
        count = min(per_sheet, frame_count - offset)
        first_index = offset + 1
        start_ms = round(offset / dense_fps * 1000)
        end_ms = round((offset + count) / dense_fps * 1000)
        sheets.append({
            "path": str(output),
            "start_ms": start_ms,
            "end_ms": end_ms,
            "first_dense_frame_index": first_index,
            "frame_count": count,
        })
    return sheets, []


def scene_extraction_failed(returncode: int, stderr: str, cut_times_ms: list[int]) -> bool:
    """Retained for backwards-compatible tests and separate scene extraction."""
    if returncode == 0:
        return False
    no_selected_frames = (
        not cut_times_ms
        and ("No filtered frames" in stderr or "Nothing was written into output file" in stderr)
    )
    return not no_selected_frames


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a cached full-timeline video analysis pack")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--dense-fps", type=float, default=6.0)
    parser.add_argument("--scene-threshold", type=float, default=0.22)
    parser.add_argument("--dense-max-width", type=int, default=0, help="0 keeps original evidence resolution")
    parser.add_argument("--sheet-columns", type=int, default=4)
    parser.add_argument("--sheet-rows", type=int, default=4)
    parser.add_argument("--sheet-cell-width", type=int, default=320)
    parser.add_argument("--force", action="store_true", help="Ignore a valid cached analysis pack")
    parser.add_argument("--ffmpeg", default=os.environ.get("FFMPEG_BIN", "ffmpeg"))
    parser.add_argument("--ffprobe", default=os.environ.get("FFPROBE_BIN", "ffprobe"))
    args = parser.parse_args()

    if args.dense_fps <= 0:
        parser.error("--dense-fps must be positive")
    if not 0 < args.scene_threshold < 1:
        parser.error("--scene-threshold must be between 0 and 1")
    if args.dense_max_width < 0:
        parser.error("--dense-max-width cannot be negative")
    if min(args.sheet_columns, args.sheet_rows, args.sheet_cell_width) <= 0:
        parser.error("overview sheet dimensions must be positive")

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"Input video was not found: {input_path}", file=sys.stderr)
        return 2
    ffmpeg = _resolve_binary(args.ffmpeg)
    if not ffmpeg:
        print("ffmpeg was not found. Set FFMPEG_BIN or provide --ffmpeg.", file=sys.stderr)
        return 2

    requested_output = Path(args.output_dir)
    requested_output.mkdir(parents=True, exist_ok=True)
    settings = {
        "dense_fps": args.dense_fps,
        "scene_threshold": args.scene_threshold,
        "dense_max_width": args.dense_max_width,
        "sheet_columns": args.sheet_columns,
        "sheet_rows": args.sheet_rows,
        "sheet_cell_width": args.sheet_cell_width,
    }
    signature = _file_signature(input_path)
    cache_key = _cache_key(signature, settings)
    cache_root = Path(args.cache_dir) if args.cache_dir else requested_output.parent / ".product-video-remake-cache"
    cache_output = cache_root / cache_key
    cache_manifest_path = cache_output / "analysis-pack.json"
    requested_manifest_path = requested_output / "analysis-pack.json"

    if not args.force:
        cached = _read_valid_manifest(requested_manifest_path, cache_key)
        if cached:
            delivered = dict(cached)
            delivered["cache_hit"] = True
            _write_json(requested_manifest_path, delivered)
            print(f"CACHE HIT: {requested_manifest_path}")
            return 0
        cached = _read_valid_manifest(cache_manifest_path, cache_key)
        if cached:
            delivered = dict(cached)
            delivered["cache_hit"] = True
            _write_json(requested_manifest_path, delivered)
            print(f"CACHE HIT: {cache_manifest_path}")
            print(f"Wrote analysis manifest: {requested_manifest_path}")
            return 0

    dense_dir = cache_output / "dense-frames"
    cut_dir = cache_output / "cut-candidates"
    sheet_dir = cache_output / "overview-sheets"
    _clean_generated_images(dense_dir, "frame-*.jpg")
    _clean_generated_images(cut_dir, "cut-*.jpg")
    audio_path = cache_output / "analysis-audio.wav"
    if audio_path.is_file():
        audio_path.unlink()

    ffprobe = _find_ffprobe(ffmpeg, args.ffprobe)
    has_audio = _has_audio(str(input_path), ffprobe)
    warnings: list[str] = []
    if has_audio is None:
        warnings.append("audio presence could not be probed; audio extraction used a compatibility pass")

    dense_filter = _dense_filter(args.dense_fps, args.dense_max_width)
    # Include frame zero on the cut branch so a zero-cut video remains a valid
    # single-process extraction. Zero is removed from cut_candidate_times_ms.
    cut_filter = f"select='eq(n,0)+gt(scene,{args.scene_threshold})',showinfo"
    filter_complex = f"[0:v]split=2[dense_in][cut_in];[dense_in]{dense_filter}[dense];[cut_in]{cut_filter}[cuts]"
    command = [
        ffmpeg,
        "-hide_banner", "-loglevel", "info", "-y",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[dense]", "-q:v", "2", str(dense_dir / "frame-%06d.jpg"),
        "-map", "[cuts]", "-fps_mode", "vfr", "-q:v", "2", str(cut_dir / "cut-%06d.jpg"),
    ]
    if has_audio is True:
        command.extend(["-map", "0:a:0", "-ac", "1", "-ar", "16000", str(audio_path)])
    result = _run(command)
    if result.returncode != 0:
        print(result.stderr.strip() or "single-pass analysis extraction failed", file=sys.stderr)
        return result.returncode or 1

    if has_audio is None:
        audio_result = _run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(input_path),
            "-vn", "-ac", "1", "-ar", "16000", str(audio_path),
        ])
        if audio_result.returncode != 0:
            warnings.append("audio extraction failed or the source has no audio")
            if audio_path.is_file():
                audio_path.unlink()

    dense_frames = [str(path) for path in sorted(dense_dir.glob("frame-*.jpg"))]
    cut_frames = [str(path) for path in sorted(cut_dir.glob("cut-*.jpg"))]
    parsed_times = sorted({round(float(value) * 1000) for value in PTS_PATTERN.findall(result.stderr)})
    cut_times_ms = [value for value in parsed_times if value > 0]
    overview_sheets, overview_warnings = _create_overview_sheets(
        ffmpeg,
        dense_dir,
        sheet_dir,
        len(dense_frames),
        args.dense_fps,
        args.sheet_columns,
        args.sheet_rows,
        args.sheet_cell_width,
    )
    warnings.extend(overview_warnings)

    manifest = {
        "schema_version": "1.2",
        "analysis_strategy_version": ANALYZER_VERSION,
        "cache_key": cache_key,
        "cache_hit": False,
        "source": str(input_path),
        "source_signature": signature,
        "settings": settings,
        "decode_strategy": "single_source_decode_with_parallel_video_branches_and_audio_output",
        "dense_fps": args.dense_fps,
        "scene_threshold": args.scene_threshold,
        "dense_frames": dense_frames,
        "cut_candidate_frames": cut_frames,
        "cut_candidate_times_ms": cut_times_ms,
        "cut_frames_include_zero_ms_baseline": True,
        "overview_sheets": overview_sheets,
        "analysis_audio": str(audio_path) if audio_path.is_file() else None,
        "analysis_audio_is_api_reference": False,
        "review_protocol": {
            "first_pass": "inspect every overview sheet in chronological order",
            "detail_pass": "inspect original dense/cut frames for every shot boundary, transformation, product interaction, text, face, body, skin, object or scene uncertainty",
            "fallback": "if shot coverage or timing remains uncertain, inspect all dense frames in that interval; never guess or silently omit",
        },
        "warnings": warnings,
    }
    _write_json(cache_manifest_path, manifest)
    _write_json(requested_manifest_path, manifest)
    print(f"CACHE MISS: {cache_key}")
    print(f"Wrote cached analysis pack: {cache_manifest_path}")
    print(f"Wrote analysis manifest: {requested_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
