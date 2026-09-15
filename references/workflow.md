# Runtime workflow

This skill is an analysis, request-compilation, and optional result-validation workflow. It never uploads assets or calls a generation API.

## 0. Exact-cache reuse and parallel preparation

Run the cached analysis-pack builder before visual review. Reuse preprocessing only when the manifest cache key matches the source signature, analyzer version, and extraction settings. Reuse a verified Source Video DNA for a different product only when the exact source signature is unchanged. A parameter-only change should rebuild the plan and compiled outputs, not re-analyze media.

Product-image understanding and video preprocessing may run concurrently because they are independent. Do not parallelize steps that depend on unresolved shot boundaries or state transitions.

## 1. Intake

Accept product images and one reference video. Do not require a product asset pack, product name, or selling points. The reference video is analysis-only input and never enters the upload manifest or API request. Product-image local paths may appear only in the upload manifest.

## 2. Media facts and hierarchical evidence review

Capture duration, ratio, width, height, frame rate, audio presence, and rotation. These facts constrain the legal Seedance request and the target timeline. Do not infer exact frame timing from prose when media tooling can measure it. For local videos, use `scripts/prepare_analysis_pack.py`: review every chronological overview sheet first, then open original evidence frames around all boundaries and important state changes. If evidence is uncertain, inspect every dense frame in that interval or extract an exact full-resolution frame. Analysis images and audio never become API reference assets.

## 3. Product profile

Read packaging with OCR where possible. Separate visible facts, model inference, user-confirmed facts, and unknowns. Capture product shape, color, material, logo, label layout, visible sides, likely use actions, and candidate selling points.

## 4. Source Video DNA

Watch or sample the entire video, including transitions. Detect cuts densely, then record shot semantics, camera, composition, subject state, product state, scene state, text, effects, dialogue, music, sound effects, and beat anchors. Do not analyze only the product.

## 5. Adaptation decision

Classify product distance as same, adjacent, functionally related, or distant. Preserve the source literally where physically possible. Change only the original product identity and product actions that cannot work for the new product.

## 6. Fidelity contract

Create a ledger from source elements to target instructions. Every must-keep element needs a target timeline unit and verification note. Never let a detail disappear between analysis and compilation.

## 7. Editing contract and mode selection

Create an editing contract from the target timeline: exact shot count, hard-cut count, expected cut times, drift tolerance, and all adjacent pairs that may not be merged. Mark each timeline item as a distinct shot and record the visible difference from its predecessor.

Use standard single-call mode unless the timeline is execution-dense. Recommend high-fidelity segmented mode when a video of 12 seconds or less has more than 8 shots, or when average shot duration is below 1.2 seconds. An explicit user choice overrides the recommendation. Segment only at existing timeline boundaries, keep every API duration within 4-15 seconds, and record deterministic trim ranges when integer API durations exceed the intended segment span.

## 8. Prompt compilation

Compile the offline findings into direct target instructions:

- Product images define the target product identity.
- Video DNA supplies shot grammar, people, changes, movement, scene, effects, and audio structure during compilation, but the final prompt must describe those details directly.
- Do not tell Seedance to inspect, inherit from, compare with, or replace anything in a source video; it will not receive that video.
- Fill `remake-plan.prompt_exclusion_terms` with source-only brand names, old product names, visible labels, file names, URLs, and asset identifiers that must never leak into the final prompt or request.

Write a standalone editing contract followed by global rules, a numbered timestamped target timeline, and consistency constraints. Use Chinese unless the user asks for another language. Internal IDs remain in JSON only; use `镜头1`, `镜头2`, and so on in the prompt. Remove source-only brands, file names, URLs, local paths, asset IDs, and phrases such as `视频1`, `参考视频`, `原视频`, or `原商品`.

## 9. Request compilation

Every request contains exactly one text item followed by 1-9 product `reference_image` items. Standard mode emits one request. High-fidelity mode emits 2-3 independent request directories and `assembly-plan.json`. Do not include `video_url`, `audio_url`, `reference_video`, or `reference_audio`. Produce URL placeholders only for local product images.

## 10. Preflight

Validate API fields, product-image mappings, target-only prompt wording, editing-contract consistency, timeline coverage, must-keep coverage, and the absence of internal timeline IDs in prompts. Return errors rather than silently repairing an ambiguous semantic plan.

## 11. Postflight when a result is supplied

Run `scripts/validate_generated_video.py` with the generated video and its remake plan. Treat duration, ratio, major-cut count, and cut-position drift as structural checks. Review the generated contact sheet against the semantic checklist for every shot. Report structural and semantic status separately; never label a video as successfully remade based on request preflight alone.
