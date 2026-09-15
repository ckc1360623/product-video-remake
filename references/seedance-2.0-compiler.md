# Seedance 2.0 request compiler

Official references, verified 2026-09-03:

- Prompt guide: https://www.volcengine.com/docs/82379/2222480?lang=zh
- Create video task API: https://api.volcengine.com/api-explorer/debug?action=CreateContentsGenerationsTasks&groupName=%E8%A7%86%E9%A2%91%E7%94%9F%E6%88%90API&serviceCode=ark&version=2024-01-01
- Multimodal overview: https://developer.volcengine.com/articles/7606009619928449070

Re-check official documentation before changing API constraints because model capabilities can change.

## Current request contract

The API request uses `model`, `content`, `resolution`, `ratio`, `duration`, `generate_audio`, `seed`, and `watermark`.

For Seedance 2.0:

- `duration` is an integer from 4 through 15, or `-1`; use an explicit 4-15 value for reproducible compilation.
- `frames` is not supported.
- Ratios: `16:9`, `4:3`, `1:1`, `3:4`, `9:16`, `21:9`, or `adaptive`.
- Resolutions: `480p`, `720p`, or `1080p`; Seedance 2.0 fast does not support `1080p`.
- `camera_fixed` is not supported by Seedance 2.0.
- The platform supports multiple media types, but this skill intentionally emits only text and product reference images.

The standard compiler emits one request. High-fidelity mode may emit 2-3 independent requests and an assembly plan. Neither mode calls the endpoint.

## Material binding

Order request content deterministically:

1. Text prompt.
2. Product images as `图片1`, `图片2`, etc., each with `role: reference_image`.

Product images are the only online reference assets and are authoritative for target product appearance. The source video and extracted audio remain offline evidence only. Before compiling, translate their shot structure, subjects, state changes, actions, camera, scene, effects, and audio grammar into explicit target instructions.

## Prompt order

1. State the target-video or target-segment goal without mentioning replacement or a source video.
2. Bind every product image.
3. State duration, ratio, resolution, and audio target.
4. State the highest-priority editing contract: exact shot count, hard-cut count, cut positions, drift tolerance, and no-merge rule.
5. State global target details once.
6. State target product actions and appearance requirements without describing the old product.
7. Provide a numbered timestamped timeline such as `镜头1（0.00-1.20秒）`.
8. State identity, state, text, audio, and continuity constraints.

Prefer one dominant action and one dominant camera movement per timeline unit. Describe observable perspective and depth instead of unsupported exact lens metadata. Quote dialogue to improve synchronized audio generation. The prompt must stand alone: it may use `图片1`, but must not contain `视频1`, `参考视频`, `原视频`, `原商品`, source file names, local paths, source URLs, or source-only brands.

Internal timeline IDs such as `T001` belong only in JSON. Never emit `执行于：T001` or a bare internal ID. Convert coverage references to defined human shot numbers. When several adjacent shots share a scene or action, explicitly state the visible difference and repeat that each is an independent hard-cut shot.

Before compilation, fill `remake-plan.prompt_exclusion_terms` with every source-only brand, old product name, visible label, media file name, URL, and asset ID. Preflight rejects any listed term that leaks into the prompt.

## Local asset placeholders

Local product images cannot be inserted as Windows paths into the remote request. Put only their paths in `upload-manifest.json` and placeholders such as `${PRODUCT_IMAGE_1_URL}` in the request. If a product image is already an HTTPS URL or `asset://` URI, pass it through. Never create `${REFERENCE_VIDEO_URL}` or any audio/video upload record.
