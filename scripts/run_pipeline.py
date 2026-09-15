#!/usr/bin/env python3
"""Build and validate an offline standard or high-fidelity request package.

Inputs are structured product and video analyses created by the skill. This
script never uploads assets, submits requests, or calls Seedance.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remake_core import (
    build_single_call_plan,
    compile_bundle,
    compile_fidelity_package,
    ensure_editing_contract,
    load_json,
    validate_bundle,
    write_compiled_outputs,
    write_fidelity_outputs,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a validated Seedance remake package")
    parser.add_argument("--product-profile", required=True)
    parser.add_argument("--video-dna", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--product-distance", default="same", choices=["same", "adjacent", "functionally_related", "distant"])
    parser.add_argument("--ratio")
    parser.add_argument("--resolution", default="720p", choices=["480p", "720p", "1080p"])
    parser.add_argument("--model", default="${SEEDANCE_MODEL_ID}")
    parser.add_argument("--generate-audio", choices=["auto", "true", "false"], default="auto")
    parser.add_argument("--generation-mode", choices=["auto", "single", "high-fidelity"], default="auto")
    args = parser.parse_args()

    product = load_json(args.product_profile)
    video = load_json(args.video_dna)
    generate_audio = None if args.generate_audio == "auto" else args.generate_audio == "true"
    plan = build_single_call_plan(
        video,
        target_duration_s=args.duration,
        product_distance=args.product_distance,
        resolution=args.resolution,
        ratio=args.ratio,
        generate_audio=generate_audio,
        model=args.model,
    )
    plan = ensure_editing_contract(plan)
    bundle = compile_bundle(product, video, plan)
    report = validate_bundle(product, video, plan, bundle)
    recommended_mode = plan["generation_strategy"]["recommended_mode"]
    selected_mode = (
        "high_fidelity_segmented"
        if args.generation_mode == "high-fidelity" or (args.generation_mode == "auto" and recommended_mode == "high_fidelity_segmented")
        else "standard_single_call"
    )
    report["summary"]["selected_generation_mode"] = selected_mode
    if selected_mode == "high_fidelity_segmented":
        report["warnings"].append("high-fidelity segmented package selected because the timeline is dense; each request still requires external submission")

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "product-profile.json", product)
    write_json(output / "source-video-dna.json", video)
    write_json(output / "remake-plan.json", plan)
    write_compiled_outputs(output, bundle)
    write_json(output / "preflight-validation-report.json", report)
    if selected_mode == "high_fidelity_segmented":
        fidelity_package = compile_fidelity_package(product, video, plan)
        fidelity_manifest = write_fidelity_outputs(output / "high-fidelity-package", fidelity_package)
        if not fidelity_manifest["ready"]:
            report["ready"] = False
            report["errors"].append("one or more high-fidelity segment requests failed preflight")
            write_json(output / "preflight-validation-report.json", report)

    print(f"Wrote offline request package to: {output}")
    print(f"Preflight ready: {str(report['ready']).lower()}")
    print(f"Selected generation mode: {selected_mode}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
