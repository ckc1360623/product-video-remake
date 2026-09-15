#!/usr/bin/env python3
"""Validate fidelity coverage and one independently submitted request."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remake_core import SCHEMA_VERSION, ensure_editing_contract, load_json, validate_bundle, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a compiled Seedance request package")
    parser.add_argument("--product-profile", required=True)
    parser.add_argument("--video-dna", required=True)
    parser.add_argument("--remake-plan", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--upload-manifest", required=True)
    parser.add_argument("--seedance-request", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    prompt = Path(args.prompt).read_text(encoding="utf-8")
    plan = ensure_editing_contract(load_json(args.remake_plan))
    bundle = {
        "schema_version": SCHEMA_VERSION,
        "contract": plan.get("contract", {}),
        "prompt": prompt,
        "upload_manifest": load_json(args.upload_manifest),
        "api_request": load_json(args.seedance_request),
    }
    report = validate_bundle(load_json(args.product_profile), load_json(args.video_dna), plan, bundle)
    write_json(args.output, report)
    if report["ready"]:
        print(f"READY: {args.output}")
        return 0
    print(f"NOT READY: {args.output}")
    for error in report["errors"]:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
