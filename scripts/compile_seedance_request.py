#!/usr/bin/env python3
"""Compile prompt, upload manifest, and one Seedance request without calling it."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remake_core import compile_bundle, ensure_editing_contract, load_json, write_compiled_outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile one Seedance 2.0 request package")
    parser.add_argument("--product-profile", required=True)
    parser.add_argument("--video-dna", required=True)
    parser.add_argument("--remake-plan", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    plan = ensure_editing_contract(load_json(args.remake_plan))
    bundle = compile_bundle(load_json(args.product_profile), load_json(args.video_dna), plan)
    write_compiled_outputs(args.output_dir, bundle)
    print(f"Wrote prompt, upload manifest, and one API request to: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
