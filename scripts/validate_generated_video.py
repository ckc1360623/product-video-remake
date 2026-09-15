#!/usr/bin/env python3
"""Validate a generated video against the compiled editing contract."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from remake_core import ensure_editing_contract, load_json, write_json


PTS_PATTERN = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def _run(command: List[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)


def _ratio_value(label: str) -> float | None:
    if label == "adaptive" or ":" not in label:
        return None
    left, right = label.split(":", 1)
    try:
        return float(left) / float(right)
    except (ValueError, ZeroDivisionError):
        return None


def _probe(video: str, ffprobe: str) -> Dict[str, Any]:
    result = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate:format=duration",
            "-of",
            "json",
            video,
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return {
        "duration_ms": round(float(payload["format"]["duration"]) * 1000),
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate": stream.get("r_frame_rate"),
    }


def _detect_cuts(video: str, ffmpeg: str, threshold: float) -> List[int]:
    result = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            video,
            "-vf",
            f"select=gt(scene\\,{threshold}),showinfo",
            "-an",
            "-f",
            "null",
            "NUL",
        ]
    )
    return sorted({round(float(value) * 1000) for value in PTS_PATTERN.findall(result.stderr)})


def compare_structure(plan: Dict[str, Any], media: Dict[str, Any], cut_times_ms: List[int], ratio_tolerance: float = 0.03) -> Dict[str, Any]:
    effective = ensure_editing_contract(plan)
    target = effective["target"]
    editing = effective["editing_contract"]
    errors: List[str] = []
    warnings: List[str] = []
    target_duration_ms = int(target["duration_s"]) * 1000
    duration_delta = abs(int(media["duration_ms"]) - target_duration_ms)
    if duration_delta > 350:
        errors.append(f"duration differs by {duration_delta}ms")

    expected_ratio = _ratio_value(str(target.get("ratio", "adaptive")))
    actual_ratio = float(media["width"]) / max(1.0, float(media["height"]))
    ratio_error = None if expected_ratio is None else abs(actual_ratio - expected_ratio) / expected_ratio
    if ratio_error is not None and ratio_error > ratio_tolerance:
        errors.append(f"frame ratio differs by {ratio_error:.1%}: expected {target['ratio']}, got {media['width']}x{media['height']}")

    expected_cuts = int(editing["expected_cut_count"])
    if len(cut_times_ms) < max(0, expected_cuts - 1):
        errors.append(f"detected only {len(cut_times_ms)} major cuts; expected {expected_cuts}")
    elif len(cut_times_ms) != expected_cuts:
        warnings.append(f"detected {len(cut_times_ms)} major cuts; expected {expected_cuts}")

    drift = int(editing.get("max_cut_drift_ms", 300))
    expected_times = [int(value) for value in editing.get("expected_cut_times_ms", [])]
    matched = []
    missing = []
    for expected in expected_times:
        nearby = [actual for actual in cut_times_ms if abs(actual - expected) <= drift]
        if nearby:
            matched.append({"expected_ms": expected, "actual_ms": min(nearby, key=lambda value: abs(value - expected))})
        else:
            missing.append(expected)
    if len(missing) > 1:
        errors.append(f"{len(missing)} expected cut positions were not detected within {drift}ms")
    elif missing:
        warnings.append(f"one expected cut position was not detected within {drift}ms")

    checklist = []
    for index, item in enumerate(effective.get("timeline", []), start=1):
        checklist.append(
            {
                "shot": index,
                "time_range_ms": [item["target_start_ms"], item["target_end_ms"]],
                "required_action": item.get("required_action", ""),
                "required_outfit": item.get("required_outfit", ""),
                "required_scene": item.get("required_scene", ""),
                "visual_delta": item.get("visual_delta", ""),
                "status": "requires_visual_review",
            }
        )
    return {
        "schema_version": "1.3",
        "structural_ready": not errors,
        "fidelity_ready": None,
        "semantic_review_required": True,
        "errors": errors,
        "warnings": warnings,
        "measured": {
            **media,
            "actual_ratio": round(actual_ratio, 6),
            "detected_cut_count": len(cut_times_ms),
            "detected_cut_times_ms": cut_times_ms,
        },
        "expected": {
            "duration_ms": target_duration_ms,
            "ratio": target.get("ratio"),
            "shot_count": editing["expected_shot_count"],
            "cut_count": expected_cuts,
            "cut_times_ms": expected_times,
        },
        "cut_matches": matched,
        "missing_cut_times_ms": missing,
        "semantic_review_checklist": checklist,
    }


def _make_contact_sheet(video: str, output: Path, ffmpeg: str, duration_ms: int) -> None:
    columns = 6
    frame_count = max(1, math.ceil(duration_ms / 500))
    rows = max(1, math.ceil(frame_count / columns))
    result = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            video,
            "-vf",
            f"fps=2,scale=360:-2,tile={columns}x{rows}:padding=4:margin=4",
            "-frames:v",
            "1",
            str(output),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "contact-sheet generation failed")


def main() -> int:
    parser = argparse.ArgumentParser(description="Postflight structural validation for a generated remake video")
    parser.add_argument("--result-video", required=True)
    parser.add_argument("--remake-plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--contact-sheet")
    parser.add_argument("--scene-threshold", type=float, default=0.18)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args()

    ffmpeg = shutil.which(args.ffmpeg)
    ffprobe = shutil.which(args.ffprobe)
    if not ffmpeg or not ffprobe:
        parser.error("ffmpeg and ffprobe must be available")
    media = _probe(args.result_video, ffprobe)
    cuts = _detect_cuts(args.result_video, ffmpeg, args.scene_threshold)
    report = compare_structure(load_json(args.remake_plan), media, cuts)
    if args.contact_sheet:
        contact_sheet = Path(args.contact_sheet)
        contact_sheet.parent.mkdir(parents=True, exist_ok=True)
        _make_contact_sheet(args.result_video, contact_sheet, ffmpeg, media["duration_ms"])
        report["contact_sheet"] = str(contact_sheet)
    write_json(args.output, report)
    print(f"Structural ready: {str(report['structural_ready']).lower()}")
    print("Semantic review required: true")
    return 0 if report["structural_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
