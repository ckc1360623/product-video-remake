# Fidelity, preflight, and postflight validation

Validation occurs before generation. It proves request completeness and consistency, not the stochastic quality of a future generated video.

## Hard gates

- Exactly one API request object.
- `generation_call_count` equals 1.
- `segmented_generation`, `post_editing`, and `video_assembly` are false.
- Exactly one text prompt and 1-9 product `reference_image` items are present.
- Zero `video_url`, `audio_url`, `reference_video`, and `reference_audio` items are present.
- Every local asset placeholder has one upload-manifest mapping.
- Duration, ratio, resolution, and model-specific fields are valid.
- Timeline starts at 0, has no gap or overlap, and ends at `duration * 1000`.
- Every must-keep shot and source element is covered.
- The prompt names `图片1` and contains no source-dependent wording such as `视频1`, `参考视频`, `原视频`, or `原商品`.
- The source video's path, URL, file name, asset ID, original product identity, and analysis-audio path do not appear in the prompt or API request.
- The prompt declares the exact expected shot count and hard-cut count.
- The prompt contains no internal `Txxx` IDs or dangling `执行于` references.
- `editing_contract` agrees with the timeline boundaries and all forbidden-merge pairs reference known timeline items.
- Unsupported or multi-call keys are absent.

## Coverage ledger

For each source element record source evidence, target timeline IDs, prompt instruction, status, and reason. Allowed statuses:

- `preserved`
- `approximated`
- `minimally_adapted`
- `omitted_with_reason`

A must-keep element may not be `omitted_with_reason`.

## Reverse comparison

Before compilation, reread the final plan as if it were a target video and compare it against Source Video DNA. Check narrative order, shot-energy curve, beat anchors, subject identity, transformations, product timing, scene changes, transitions, text, and audio. Then read the final prompt without access to the source: every instruction must still be executable and unambiguous. Add missing target details and remove source-dependent wording before deterministic validation.

## Warnings

Warnings describe uncertainty such as estimated lens class, unseen product sides, extreme compression, ambiguous OCR, or single-call controllability. Do not add compliance or advertising judgments.

## Generated-video postflight

When the user supplies generated footage, run `scripts/validate_generated_video.py`. It measures duration, dimensions, ratio, major cut count, and cut-position drift, then produces a chronological contact sheet and semantic checklist. A structural pass does not prove that the correct action occurred in each shot. Keep `fidelity_ready` unset until the checklist confirms shot identity, action, outfit/state, scene, product appearance, and visible difference from the previous shot.

For high-fidelity segmented packages, each request must pass preflight, segment trim ranges must cover the target timeline without gaps or overlaps, and assembly transitions must be hard cuts unless the plan explicitly says otherwise.
