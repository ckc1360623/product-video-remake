#!/usr/bin/env python3
"""Compile a high-fidelity multi-request package without calling any API."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remake_core import compile_fidelity_package, load_json, write_fidelity_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile segmented Seedance requests and an assembly plan")
    parser.add_argument("--product-profile", required=True)
    parser.add_argument("--video-dna", required=True)
    parser.add_argument("--remake-plan", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    package = compile_fidelity_package(
        load_json(args.product_profile),
        load_json(args.video_dna),
        load_json(args.remake_plan),
    )
    manifest = write_fidelity_outputs(args.output_dir, package)
    print(f"Wrote high-fidelity offline package to: {args.output_dir}")
    print(f"Segments: {package['generation_call_count']}; ready: {str(manifest['ready']).lower()}")
    return 0 if manifest["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
