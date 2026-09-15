# Data contracts

Machine-readable schemas live in `schemas/`. This document explains the semantic contracts.

## product-profile.json

- `source_images`: product image paths or URLs in prompt-reference order.
- `identity`: name, brand, and category with provenance and confidence.
- `visual_identity`: shape, colors, material, logo, label, visible sides, and text.
- `usage`: likely actions and scenes.
- `selling_points`: observed, inferred, or user-confirmed candidates.
- `unknowns`: unresolved facts.

## source-video-dna.json

- `source_asset`: exactly one original reference video. For safe semantic-cache reuse, also copy `analysis_cache_key`, `analysis_strategy_version`, and `source_signature` from the analysis-pack manifest when available.
- `media`: measured technical facts.
- `summary`: style, narrative, audience, palette, and type vector.
- `audio`: dialogue, music, beats, sound effects, and synchronization.
- `shots`: ordered shot records with millisecond timing.
- `source_elements`: cross-shot changes and details that need fidelity accounting.

## remake-plan.json

- `contract`: invariants for the current request; every compiled API request remains independently valid and contains product images only.
- `target`: model, integer duration, ratio, resolution, audio, seed, and watermark.
- `product_distance`: level and reasons.
- `adaptation_ledger`: each physically necessary product-action change and the surrounding details that remain locked.
- `global_locked_details`: details that apply across the video.
- `allowed_changes`: product-only or physically necessary adaptations.
- `prompt_exclusion_terms`: source-only brand names, labels, file names, URLs, or identifiers that the final prompt and API request must not contain.
- `timeline`: complete target timeline, each unit mapped to source shots.
- `editing_contract`: expected shot count, expected hard-cut count and times, cut drift tolerance, and adjacent pairs that may not be merged.
- `generation_strategy`: standard single-call or high-fidelity segmented recommendation based on shot density.
- Each timeline item keeps its internal `id`, but also records `shot_number`, `must_be_distinct`, `must_cut_before`, `must_cut_after`, `visual_delta`, `required_action`, `required_outfit`, and `required_scene`.
- `coverage`: one row per source element.
- `compression`: source duration, target duration, strategy, and omitted details.

## upload-manifest.json

Contains local path or source URL, generated placeholder, API content type, API role, and prompt reference name for each product image only. The analyzed reference video and analysis audio are deliberately excluded.

## seedance-request.json

One JSON object accepted by the external integration after product-image placeholder replacement. Its `content` array contains exactly one standalone target prompt plus 1-9 product reference images. It must not contain credentials, local paths, source-video references, video/audio content items, multiple request objects, or postproduction instructions.

## preflight-validation-report.json

Contains `ready`, `errors`, `warnings`, and summary counts. `ready` is true only when errors are empty, every must-keep source detail is represented by a target-only instruction, and the request contains zero video/audio inputs.

## fidelity-package.json and assembly-plan.json

High-fidelity mode emits 2-3 independently valid request directories plus an assembly plan. Segment requests use legal integer durations; `assembly-plan.json` records deterministic trim endpoints and hard-cut order needed to recover the original target duration. Compilation does not submit requests or assemble media.

## postflight-validation-report.json

Records measured duration, dimensions, ratio, detected hard cuts, matched and missing planned cut positions, and a per-shot semantic review checklist. `structural_ready` covers measurable media structure. `fidelity_ready` remains null until a human or visual model verifies actions, outfits, scenes, identity, and product fidelity.
