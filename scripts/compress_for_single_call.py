#!/usr/bin/env python3
"""Create one 4-15 second remake-plan candidate from Source Video DNA."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remake_core import build_single_call_plan, load_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a single-call Seedance remake plan")
    parser.add_argument("--video-dna", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--product-distance", default="same", choices=["same", "adjacent", "functionally_related", "distant"])
    parser.add_argument("--ratio")
    parser.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    parser.add_argument("--model", default="${SEEDANCE_MODEL_ID}")
    parser.add_argument("--generate-audio", choices=["auto", "true", "false"], default="auto")
    args = parser.parse_args()

    generate_audio = None if args.generate_audio == "auto" else args.generate_audio == "true"
    plan = build_single_call_plan(
        load_json(args.video_dna),
        target_duration_s=args.duration,
        product_distance=args.product_distance,
        resolution=args.resolution,
        ratio=args.ratio,
        generate_audio=generate_audio,
        model=args.model,
    )
    write_json(args.output, plan)
    print(f"Wrote single-call remake plan: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
