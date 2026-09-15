#!/usr/bin/env python3
"""Deterministic planning, compilation, and validation for product-video-remake.

This module never uploads assets or calls a generation API.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


SCHEMA_VERSION = "1.3"
ALLOWED_RATIOS = {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"}
ALLOWED_RESOLUTIONS = {"480p", "720p", "1080p"}
ALLOWED_COVERAGE = {"preserved", "approximated", "minimally_adapted", "omitted_with_reason"}
FORBIDDEN_REQUEST_KEYS = {
    "frames",
    "camera_fixed",
    "draft",
    "return_last_frame",
    "segments",
    "requests",
    "clips",
    "post_editing",
    "video_assembly",
}
FORBIDDEN_PROMPT_MARKERS = (
    "视频1",
    "参考视频",
    "原视频",
    "原商品",
    "reference video",
    "source video",
    "${REFERENCE_VIDEO_URL}",
)


def load_json(path: str | os.PathLike[str]) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path: str | os.PathLike[str], value: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _evidence_value(value: Any, default: str = "未知") -> str:
    if isinstance(value, dict):
        raw = value.get("value")
        return str(raw) if raw not in (None, "") else default
    if value not in (None, ""):
        return str(value)
    return default


def _flatten(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "；".join(part for part in (_flatten(item) for item in value) if part)
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _flatten(item)
            if text:
                parts.append(f"{key}：{text}")
        return "；".join(parts)
    return str(value)


def _target_direct_text(value: Any) -> str:
    """Remove generic source-dependent phrasing from target execution text.

    This is deliberately conservative. Brand names and other source-only terms
    must be listed in remake-plan.prompt_exclusion_terms and removed during the
    required semantic review before compilation.
    """
    text = _flatten(value)
    replacements = {
        "参考视频": "既定成片",
        "原视频": "既定成片",
        "视频1": "既定成片",
        "原商品": "目标商品",
        "reference video": "target video",
        "source video": "target video",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    # Timeline IDs are useful in JSON ledgers but are meaningless control
    # tokens to a video model unless the prompt defines them. Keep them out of
    # natural-language execution text and render human shot numbers instead.
    text = re.sub(r"[；;]?\s*执行于[:：]\s*T\d{3}(?:\s*[、,，]\s*T\d{3})*[。.]?", "", text)
    return re.sub(r"\bT\d{3}\b", "", text).strip("；;，,。 ")


def _prompt_text(value: Any, max_chars: int) -> str:
    """Keep model-facing prose concise while the JSON plan retains full evidence."""
    text = _target_direct_text(value)
    if len(text) <= max_chars:
        return text
    candidate = text[:max_chars]
    boundary = max(candidate.rfind(mark) for mark in ("。", "；", ";", "，", ","))
    if boundary >= max_chars // 2:
        candidate = candidate[:boundary]
    return candidate.rstrip("；;，,。 ") + "…"


def _is_remote(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith(("https://", "http://", "asset://"))


def choose_target_duration(source_duration_ms: int, requested: int | None = None) -> int:
    if requested is not None:
        if isinstance(requested, bool) or not isinstance(requested, int) or not 4 <= requested <= 15:
            raise ValueError("target duration must be an integer from 4 through 15")
        return requested
    rounded = int(math.floor(source_duration_ms / 1000.0 + 0.5))
    return max(4, min(15, rounded))


def _shot_score(shot: Dict[str, Any]) -> float:
    score = float(shot.get("importance", 0.5)) * 10.0
    role = str(shot.get("narrative_role", "")).lower()
    if shot.get("must_keep"):
        score += 100.0
    if shot.get("signature"):
        score += 30.0
    if any(token in role for token in ("hook", "reveal", "product", "transform", "payoff", "result", "cta")):
        score += 20.0
    if shot.get("states"):
        score += 10.0
    if shot.get("product"):
        score += 8.0
    if shot.get("audio"):
        score += 4.0
    return score


def _minimum_target_ms(shot: Dict[str, Any]) -> int:
    explicit = shot.get("min_target_ms")
    if isinstance(explicit, int) and explicit > 0:
        return explicit
    audio_text = _flatten(shot.get("audio", ""))
    if any(token in audio_text.lower() for token in ("dialogue", "speech", "voice", "对白", "口播", "旁白")):
        return 700
    if shot.get("must_keep") or shot.get("signature"):
        return 450
    return 300


def _partition_contiguous(items: List[Dict[str, Any]], max_groups: int) -> List[List[Dict[str, Any]]]:
    if len(items) <= max_groups:
        return [[item] for item in items]
    groups: List[List[Dict[str, Any]]] = []
    for group_index in range(max_groups):
        start = round(group_index * len(items) / max_groups)
        end = round((group_index + 1) * len(items) / max_groups)
        groups.append(items[start:end])
    return [group for group in groups if group]


def _allocate_exact(total_ms: int, groups: List[List[Dict[str, Any]]]) -> List[int]:
    count = len(groups)
    if count == 0:
        raise ValueError("cannot allocate an empty timeline")
    floor_ms = min(300, max(80, total_ms // count))
    floor_total = floor_ms * count
    remaining = max(0, total_ms - floor_total)
    weights = []
    for group in groups:
        source_ms = sum(max(1, int(shot["source_end_ms"]) - int(shot["source_start_ms"])) for shot in group)
        importance = sum(max(1.0, _shot_score(shot)) for shot in group)
        weights.append(math.sqrt(source_ms) * importance)
    weight_sum = sum(weights) or 1.0
    durations = [floor_ms + int(remaining * weight / weight_sum) for weight in weights]
    durations[-1] += total_ms - sum(durations)
    return durations


def _visual_delta(previous: Dict[str, Any] | None, current: Dict[str, Any]) -> str:
    if previous is None:
        return "开场建立人物、环境和初始状态。"
    changed = []
    for label, key in (("场景", "scene"), ("人物状态或服装", "subject_and_state"), ("动作", "product_action"), ("景别或机位", "camera")):
        if _flatten(previous.get(key)) != _flatten(current.get(key)):
            changed.append(label)
    if not changed:
        changed = ["构图、姿态或动作阶段"]
    return "与上一镜头形成肉眼可见差异：" + "、".join(changed) + "。"


def ensure_editing_contract(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy with explicit shot-count and no-merge controls."""
    enriched = dict(plan)
    timeline = [dict(item) for item in plan.get("timeline", [])]
    for index, item in enumerate(timeline, start=1):
        previous = timeline[index - 2] if index > 1 else None
        item.setdefault("shot_number", index)
        item.setdefault("must_be_distinct", True)
        item.setdefault("must_cut_before", index > 1)
        item.setdefault("must_cut_after", index < len(timeline))
        item.setdefault("visual_delta", _visual_delta(previous, item))
        item.setdefault("required_action", _target_direct_text(item.get("product_action") or item.get("description")))
        item.setdefault("required_outfit", _target_direct_text(item.get("subject_and_state")))
        item.setdefault("required_scene", _target_direct_text(item.get("scene")))
    enriched["timeline"] = timeline
    cut_times = [int(item["target_start_ms"]) for item in timeline[1:]]
    enriched["editing_contract"] = {
        "expected_shot_count": len(timeline),
        "expected_cut_count": max(0, len(timeline) - 1),
        "expected_cut_times_ms": cut_times,
        "max_cut_drift_ms": 300,
        "merge_forbidden": [[timeline[i]["id"], timeline[i + 1]["id"]] for i in range(max(0, len(timeline) - 1))],
    }
    duration_ms = int(enriched.get("target", {}).get("duration_s", 0)) * 1000
    average_shot_ms = round(duration_ms / len(timeline)) if timeline else 0
    high_density = (len(timeline) > 8 and duration_ms <= 12000) or (timeline and average_shot_ms < 1200)
    enriched["generation_strategy"] = {
        "recommended_mode": "high_fidelity_segmented" if high_density else "standard_single_call",
        "shot_count": len(timeline),
        "average_shot_ms": average_shot_ms,
        "reasons": (["短时长内镜头密度高，单次生成容易合并相邻镜头。"] if high_density else ["镜头密度适合单次生成。"]),
    }
    return enriched


def build_single_call_plan(
    video_dna: Dict[str, Any],
    target_duration_s: int | None = None,
    product_distance: str = "same",
    resolution: str = "720p",
    ratio: str | None = None,
    generate_audio: bool | None = None,
    model: str = "${SEEDANCE_MODEL_ID}",
) -> Dict[str, Any]:
    media = video_dna.get("media", {})
    source_duration_ms = int(media.get("duration_ms", 0))
    if source_duration_ms <= 0:
        raise ValueError("video DNA media.duration_ms must be positive")
    shots = list(video_dna.get("shots", []))
    if not shots:
        raise ValueError("video DNA must contain at least one shot")
    if product_distance not in {"same", "adjacent", "functionally_related", "distant"}:
        raise ValueError("invalid product distance")
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError("invalid resolution")

    duration_s = choose_target_duration(source_duration_ms, target_duration_s)
    target_ms = duration_s * 1000
    target_ratio = ratio or str(media.get("ratio") or "adaptive")
    if target_ratio not in ALLOWED_RATIOS:
        target_ratio = "adaptive"
    if generate_audio is None:
        generate_audio = bool(video_dna.get("audio", {}).get("has_audio", media.get("has_audio", False)))

    elements = list(video_dna.get("source_elements", []))
    forced_shot_ids = {str(shot.get("id")) for shot in shots if shot.get("must_keep") or shot.get("signature")}
    for element in elements:
        if element.get("must_keep"):
            forced_shot_ids.update(str(item) for item in element.get("source_shot_ids", []))

    ordered = sorted(shots, key=lambda shot: (int(shot.get("source_start_ms", 0)), str(shot.get("id", ""))))
    compressed = source_duration_ms > target_ms
    if not compressed:
        selected = ordered
    else:
        forced = [shot for shot in ordered if str(shot.get("id")) in forced_shot_ids]
        optional = sorted(
            [shot for shot in ordered if str(shot.get("id")) not in forced_shot_ids],
            key=lambda shot: (-_shot_score(shot), int(shot.get("source_start_ms", 0))),
        )
        selected_by_id = {str(shot.get("id")): shot for shot in forced}
        min_total = sum(_minimum_target_ms(shot) for shot in forced)
        for shot in optional:
            # A long source should lose repetitive exposition before unique
            # visual, state, product, narrative, or audio information.
            if _shot_score(shot) < 8.0:
                continue
            proposed = min_total + _minimum_target_ms(shot)
            if proposed <= target_ms and len(selected_by_id) < 24:
                selected_by_id[str(shot.get("id"))] = shot
                min_total = proposed
        selected = sorted(selected_by_id.values(), key=lambda shot: int(shot.get("source_start_ms", 0)))
        if not selected:
            selected = [max(ordered, key=_shot_score)]

    groups = _partition_contiguous(selected, max_groups=12)
    durations = _allocate_exact(target_ms, groups)
    timeline: List[Dict[str, Any]] = []
    shot_to_timeline: Dict[str, str] = {}
    source_beat_anchors = [
        int(value)
        for value in video_dna.get("audio", {}).get("beat_anchors_ms", [])
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    cursor = 0
    for index, (group, target_duration) in enumerate(zip(groups, durations), start=1):
        timeline_id = f"T{index:03d}"
        end = cursor + target_duration
        source_ids = [str(shot.get("id")) for shot in group]
        for source_id in source_ids:
            shot_to_timeline[source_id] = timeline_id
        descriptions = [_target_direct_text(shot.get("description")) for shot in group if shot.get("description")]
        roles = [str(shot.get("narrative_role", "")).strip() for shot in group if shot.get("narrative_role")]
        source_group_start = int(group[0].get("source_start_ms", 0))
        source_group_end = int(group[-1].get("source_end_ms", source_group_start + 1))
        source_group_span = max(1, source_group_end - source_group_start)
        target_beat_anchors = []
        for anchor in source_beat_anchors:
            if source_group_start <= anchor <= source_group_end:
                relative = (anchor - source_group_start) / source_group_span
                target_beat_anchors.append(round(cursor + relative * target_duration))
        timeline.append(
            {
                "id": timeline_id,
                "target_start_ms": cursor,
                "target_end_ms": end,
                "source_shot_ids": source_ids,
                "description": "快速连续呈现：" + " → ".join(descriptions) if len(group) > 1 else descriptions[0],
                "narrative_role": " + ".join(roles),
                "camera": [_target_direct_text(shot.get("camera")) for shot in group if _flatten(shot.get("camera"))],
                "composition": [_target_direct_text(shot.get("composition")) for shot in group if _flatten(shot.get("composition"))],
                "subject_and_state": [_target_direct_text(shot.get("states") or shot.get("subjects")) for shot in group if _flatten(shot.get("states") or shot.get("subjects"))],
                "product_action": [_target_direct_text(shot.get("product")) for shot in group if _flatten(shot.get("product"))],
                "scene": [_target_direct_text(shot.get("scene")) for shot in group if _flatten(shot.get("scene"))],
                "audio": [_target_direct_text(shot.get("audio")) for shot in group if _flatten(shot.get("audio"))],
                "target_beat_anchors_ms": sorted(set(target_beat_anchors)),
                "text_and_effects": [_target_direct_text(shot.get("text_overlays")) for shot in group if _flatten(shot.get("text_overlays"))],
                "transition": _target_direct_text(group[-1].get("transition_out")),
                "locked_details": ["镜头顺序", "人物与状态变化", "运镜与构图", "场景和视效", "音频节奏与踩点"],
                "allowed_changes": ["商品外观以商品图片为准", "商品动作必须符合目标商品的物理属性"],
            }
        )
        cursor = end

    coverage = []
    for element in elements:
        source_ids = [str(item) for item in element.get("source_shot_ids", [])]
        target_ids = sorted({shot_to_timeline[item] for item in source_ids if item in shot_to_timeline})
        must_keep = bool(element.get("must_keep"))
        if not target_ids and must_keep:
            target_ids = [timeline[0]["id"]]
            status = "approximated"
            reason = "Must-keep global detail is carried as a global instruction because no source shot mapping was supplied."
        elif target_ids:
            status = "approximated" if compressed else "preserved"
            reason = "Condensed into the single-call timeline." if compressed else "Mapped directly to the target timeline."
        else:
            status = "omitted_with_reason"
            reason = "Lower-value detail omitted to satisfy the single-call duration; recorded rather than silently dropped."
        coverage.append(
            {
                "source_element_id": str(element.get("id")),
                "status": status,
                "target_timeline_ids": target_ids,
                "instruction": _target_direct_text(element.get("description", "")),
                "reason": reason,
            }
        )

    selected_ids = {str(shot.get("id")) for shot in selected}
    omitted_shots = [str(shot.get("id")) for shot in ordered if str(shot.get("id")) not in selected_ids]
    strategy = "source_aligned" if not compressed else "single_call_semantic_compression"
    plan = {
        "schema_version": SCHEMA_VERSION,
        "contract": {
            "generation_call_count": 1,
            "segmented_generation": False,
            "post_editing": False,
            "video_assembly": False,
        },
        "target": {
            "model": model,
            "duration_s": duration_s,
            "ratio": target_ratio,
            "resolution": resolution,
            "generate_audio": bool(generate_audio),
            "seed": -1,
            "watermark": False,
        },
        "product_distance": {"level": product_distance, "reasons": []},
        "global_locked_details": [
            "严格执行下方时间线规定的镜头语法、顺序、节奏和能量曲线",
            "人物身份、动作、表情及身材、皮肤、服装等状态变化",
            "物体与场景状态变化",
            "运镜、构图、景别、透视、灯光、色彩、字幕、特效和转场",
            "音乐、口播、音效及关键踩点关系",
        ],
        "allowed_changes": [
            "商品身份、名称、包装、相关字幕和口播均以目标商品信息为准",
            "仅在目标商品物理属性冲突时最小调整交互动作",
        ],
        "prompt_exclusion_terms": [],
        "timeline": timeline,
        "coverage": coverage,
        "compression": {
            "strategy": strategy,
            "source_duration_ms": source_duration_ms,
            "target_duration_ms": target_ms,
            "compression_ratio": round(target_ms / source_duration_ms, 4),
            "omitted_source_shot_ids": omitted_shots,
            "requires_semantic_review": compressed or len(groups) < len(selected),
        },
    }
    return ensure_editing_contract(plan)


def _asset_entry(asset_id: str, source: str, placeholder: str, content_type: str, role: str, prompt_name: str) -> Dict[str, Any]:
    remote = _is_remote(source)
    return {
        "asset_id": asset_id,
        "source": source,
        "api_placeholder": source if remote else placeholder,
        "content_type": content_type,
        "role": role,
        "prompt_reference_name": prompt_name,
        "requires_upload": not remote,
    }


def build_upload_manifest(product_profile: Dict[str, Any], _video_dna: Dict[str, Any]) -> Dict[str, Any]:
    assets = []
    for index, image in enumerate(product_profile.get("source_images", []), start=1):
        source = str(image.get("source", ""))
        assets.append(
            _asset_entry(
                str(image.get("asset_id") or f"product_image_{index}"),
                source,
                f"${{PRODUCT_IMAGE_{index}_URL}}",
                "image_url",
                "reference_image",
                f"图片{index}",
            )
        )
    return {"schema_version": SCHEMA_VERSION, "assets": assets}


def build_prompt(product_profile: Dict[str, Any], _video_dna: Dict[str, Any], plan: Dict[str, Any], manifest: Dict[str, Any]) -> str:
    plan = ensure_editing_contract(plan)
    identity = product_profile.get("identity", {})
    product_name = _evidence_value(identity.get("name"), "目标商品")
    category = _evidence_value(identity.get("category"), "未知品类")
    visual_identity = _flatten(product_profile.get("visual_identity"))
    selling_points = _flatten([item.get("value") if isinstance(item, dict) else item for item in product_profile.get("selling_points", [])])
    target = plan["target"]
    editing = plan["editing_contract"]
    timeline = plan.get("timeline", [])
    segment_context = plan.get("segment_context")
    shot_names = {str(item.get("id")): f"镜头{index}" for index, item in enumerate(timeline, start=1)}
    cut_times = "、".join(f"{value / 1000.0:.2f}秒" for value in editing.get("expected_cut_times_ms", []))
    lines = [
        (
            "任务：生成目标商品短视频中的一个连续高保真片段。镜头数量、硬切位置和禁止合并要求优先于装饰性细节。"
            if segment_context
            else "任务：生成一条完整的目标商品短视频。镜头数量、硬切位置和禁止合并要求优先于装饰性细节。"
        ),
        "",
        "【商品图片绑定】",
    ]
    image_assets = [asset for asset in manifest["assets"] if asset["role"] == "reference_image"]
    for asset in image_assets:
        lines.append(f"- {asset['prompt_reference_name']}：只用于锁定目标商品的真实外观、包装、Logo、文字布局、颜色、材质、形状和比例。")
    lines.extend(
        [
            "",
            "【输出规格】",
            (
                f"- 当前片段时长{target['duration_s']}秒，比例{target['ratio']}，分辨率{target['resolution']}；只生成当前时间段规定的内容。"
                if segment_context
                else f"- 单条完整视频，时长{target['duration_s']}秒，比例{target['ratio']}，分辨率{target['resolution']}。"
            ),
            (
                f"- 同步音频：{'需要' if target['generate_audio'] else '不需要'}。片段首尾动作保持自然，便于按硬切清单拼接。"
                if segment_context
                else f"- 同步音频：{'需要' if target['generate_audio'] else '不需要'}。不依赖后续剪辑、拼接或二次生成。"
            ),
            "",
            "【最高优先级剪辑合同】",
            f"- 全片必须包含{editing['expected_shot_count']}个肉眼可区分的独立镜头和{editing['expected_cut_count']}次清晰硬切。",
            "- 时间线中的每一行都是一个独立镜头；禁止把相邻镜头合并成长镜头，禁止用连续动作、渐变、变形或自然过渡代替硬切。",
            f"- 必须在以下时间附近发生硬切：{cut_times or '无；全片为单镜头'}。允许的单个切点漂移不超过{editing.get('max_cut_drift_ms', 300)}毫秒。",
            "",
            "【目标商品】",
            f"- 名称：{product_name}。品类：{category}。",
            f"- 视觉身份：{visual_identity or '严格参考全部商品图片，不自行改变包装结构。'}",
        ]
    )
    if selling_points:
        lines.append(f"- 商品信息：{selling_points}。")
    lines.extend(["", "【商品呈现与动作】"])
    for row in plan.get("adaptation_ledger", []):
        target_instruction = _target_direct_text(row.get("target_instruction", ""))
        preserved = _flatten(row.get("preserved_features"))
        if target_instruction:
            lines.append(f"- {target_instruction}；保持：{_target_direct_text(preserved) or '人物、镜头、节奏与场景连续'}。")
    lines.extend(["", "【全局执行要求】"])
    lines.extend(f"- {_target_direct_text(item)}" for item in plan.get("global_locked_details", []))
    lines.extend(f"- {_target_direct_text(item)}" for item in plan.get("allowed_changes", []))
    required_coverage = [row for row in plan.get("coverage", []) if row.get("status") != "omitted_with_reason"]
    timeline_evidence = _flatten(timeline)
    supplemental_coverage = [
        row
        for row in required_coverage
        if _target_direct_text(row.get("instruction", ""))
        and _target_direct_text(row.get("instruction", "")) not in timeline_evidence
    ]
    if supplemental_coverage:
        lines.extend(["", "【不可遗漏的画面要求】"])
        for row in supplemental_coverage:
            targets = "、".join(shot_names.get(str(item), "") for item in row.get("target_timeline_ids", []))
            scope = f"对应{targets}" if targets else "适用于全片"
            instruction = _prompt_text(row.get("instruction", ""), 120)
            if instruction:
                lines.append(f"- {instruction}。{scope}。")
    lines.extend(["", "【时间线】"])
    for index, item in enumerate(timeline, start=1):
        start = item["target_start_ms"] / 1000.0
        end = item["target_end_ms"] / 1000.0
        detail_parts = [_prompt_text(item.get("description", ""), 180)]
        for label, key, limit in (
            ("运镜", "camera", 90),
            ("构图", "composition", 90),
            ("人物与状态", "subject_and_state", 120),
            ("商品动作", "product_action", 110),
            ("场景", "scene", 80),
            ("音频与踩点", "audio", 90),
            ("字幕与特效", "text_and_effects", 60),
            ("转场", "transition", 60),
        ):
            value = _prompt_text(item.get(key), limit)
            if value:
                detail_parts.append(f"{label}：{value}")
        beat_anchors = item.get("target_beat_anchors_ms", [])
        if beat_anchors:
            formatted_beats = "、".join(f"{value / 1000.0:.2f}s" for value in beat_anchors)
            detail_parts.append(f"目标踩点：{formatted_beats}")
        visual_delta = _prompt_text(item.get("visual_delta", ""), 70)
        if visual_delta:
            detail_parts.append(f"与前一镜头的可见差异：{visual_delta}")
        cut_rule = "开场直接建立画面" if index == 1 else "开头必须出现清晰硬切"
        lines.append(
            f"- 镜头{index}（{start:.2f}-{end:.2f}秒，独立镜头，{cut_rule}）："
            + "；".join(_target_direct_text(part) for part in detail_parts if _target_direct_text(part))
        )
    lines.extend(
        [
            "",
            "【一致性要求】",
            "- 人物在前后镜头保持同一身份；所有身材、皮肤、表情、服装、物体和场景变化严格按时间线规定的顺序与幅度呈现。",
            "- 商品在所有镜头保持与商品图片一致，Logo、标签、颜色、材质、轮廓和尺寸比例不漂移、不变形。",
            "- 快速分镜、硬切、转场、动作启动、商品出现和情绪变化落在时间线标注的音乐重拍和音效点上。",
            (
                "- 不增加当前片段时间线之外的镜头、人物、道具、剧情、字幕或结尾。"
                if segment_context
                else "- 不增加时间线之外的镜头、人物、道具、剧情、字幕或结尾；不输出分段视频。"
            ),
        ]
    )
    prompt = "\n".join(lines).strip() + "\n"
    if re.search(r"\bT\d{3}\b", prompt):
        raise ValueError("compiled prompt leaked an internal timeline ID")
    return prompt


def compile_bundle(product_profile: Dict[str, Any], video_dna: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    manifest = build_upload_manifest(product_profile, video_dna)
    prompt = build_prompt(product_profile, video_dna, plan, manifest)
    target = plan["target"]
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for asset in manifest["assets"]:
        url = asset["api_placeholder"]
        if asset["content_type"] != "image_url" or asset["role"] != "reference_image":
            raise ValueError("upload manifest may contain only product reference images")
        content.append({"type": "image_url", "image_url": {"url": url}, "role": "reference_image"})
    request = {
        "model": target.get("model") or "${SEEDANCE_MODEL_ID}",
        "content": content,
        "resolution": target["resolution"],
        "ratio": target["ratio"],
        "duration": target["duration_s"],
        "generate_audio": bool(target["generate_audio"]),
        "seed": int(target.get("seed", -1)),
        "watermark": bool(target.get("watermark", False)),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": dict(plan["contract"]),
        "prompt": prompt,
        "upload_manifest": manifest,
        "api_request": request,
    }


def choose_segment_ranges(plan: Dict[str, Any], max_segments: int = 3) -> List[Tuple[int, int]]:
    """Split a dense timeline at existing cuts while keeping API durations legal."""
    timeline = plan.get("timeline", [])
    if not timeline:
        return []
    total_ms = int(timeline[-1]["target_end_ms"])
    feasible_segments = max(1, min(max_segments, total_ms // 4000))
    desired = min(feasible_segments, max(2, math.ceil(len(timeline) / 7)))
    if desired <= 1 or len(timeline) <= 7:
        return [(0, len(timeline))]

    boundaries = [0]
    for part in range(1, desired):
        target = total_ms * part / desired
        remaining_parts = desired - part
        candidates = []
        for index in range(boundaries[-1] + 1, len(timeline)):
            boundary_ms = int(timeline[index]["target_start_ms"])
            previous_ms = int(timeline[boundaries[-1]]["target_start_ms"])
            if boundary_ms - previous_ms < 4000:
                continue
            if total_ms - boundary_ms < 4000 * remaining_parts:
                continue
            candidates.append((abs(boundary_ms - target), index))
        if not candidates:
            return [(0, len(timeline))]
        boundaries.append(min(candidates)[1])
    boundaries.append(len(timeline))
    return list(zip(boundaries[:-1], boundaries[1:]))


def compile_fidelity_package(
    product_profile: Dict[str, Any],
    video_dna: Dict[str, Any],
    plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Compile multiple offline requests plus deterministic trim/assembly metadata."""
    effective = ensure_editing_contract(plan)
    timeline = effective["timeline"]
    ranges = choose_segment_ranges(effective)
    segments = []
    assembly_segments = []
    for segment_number, (start_index, end_index) in enumerate(ranges, start=1):
        selected = copy.deepcopy(timeline[start_index:end_index])
        global_start = int(selected[0]["target_start_ms"])
        global_end = int(selected[-1]["target_end_ms"])
        intended_span = global_end - global_start
        request_duration_s = max(4, min(15, math.ceil(intended_span / 1000)))
        request_duration_ms = request_duration_s * 1000
        selected_ids = {str(item["id"]) for item in selected}
        source_ids = {str(source_id) for item in selected for source_id in item.get("source_shot_ids", [])}
        for item in selected:
            item["target_start_ms"] = int(item["target_start_ms"]) - global_start
            item["target_end_ms"] = int(item["target_end_ms"]) - global_start
            item["target_beat_anchors_ms"] = [
                int(value) - global_start
                for value in item.get("target_beat_anchors_ms", [])
                if global_start <= int(value) <= global_end
            ]
        selected[-1]["target_end_ms"] = request_duration_ms

        segment_plan = copy.deepcopy(effective)
        segment_plan["schema_version"] = SCHEMA_VERSION
        segment_plan["contract"] = {
            "generation_call_count": 1,
            "segmented_generation": False,
            "post_editing": False,
            "video_assembly": False,
        }
        segment_plan["target"]["duration_s"] = request_duration_s
        segment_plan["timeline"] = selected
        segment_plan["coverage"] = [
            dict(row, target_timeline_ids=[item for item in row.get("target_timeline_ids", []) if str(item) in selected_ids])
            for row in effective.get("coverage", [])
            if any(str(item) in selected_ids for item in row.get("target_timeline_ids", []))
        ]
        segment_plan["compression"] = {
            "strategy": "high_fidelity_segment",
            "source_duration_ms": intended_span,
            "target_duration_ms": request_duration_ms,
            "compression_ratio": round(request_duration_ms / max(1, intended_span), 4),
            "omitted_source_shot_ids": [],
            "requires_semantic_review": False,
        }
        segment_plan["segment_context"] = {
            "segment_number": segment_number,
            "global_start_ms": global_start,
            "global_end_ms": global_end,
            "assembly_trim_end_ms": intended_span,
        }
        segment_plan = ensure_editing_contract(segment_plan)
        segment_video = copy.deepcopy(video_dna)
        segment_video["shots"] = [shot for shot in video_dna.get("shots", []) if str(shot.get("id")) in source_ids]
        covered_element_ids = {str(row.get("source_element_id")) for row in segment_plan.get("coverage", [])}
        segment_video["source_elements"] = [
            element for element in video_dna.get("source_elements", []) if str(element.get("id")) in covered_element_ids
        ]
        bundle = compile_bundle(product_profile, segment_video, segment_plan)
        report = validate_bundle(product_profile, segment_video, segment_plan, bundle)
        segments.append({"segment_number": segment_number, "plan": segment_plan, "bundle": bundle, "preflight": report})
        assembly_segments.append(
            {
                "segment_number": segment_number,
                "global_start_ms": global_start,
                "global_end_ms": global_end,
                "generated_duration_s": request_duration_s,
                "trim_start_ms": 0,
                "trim_end_ms": intended_span,
                "transition_to_next": "hard_cut" if segment_number < len(ranges) else "end",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "high_fidelity_segmented",
        "generation_call_count": len(segments),
        "segments": segments,
        "assembly_plan": {
            "target_duration_ms": int(timeline[-1]["target_end_ms"]),
            "ratio": effective["target"]["ratio"],
            "segments": assembly_segments,
            "audio_policy": "preserve segment audio and hard-cut at the declared boundaries; normalize only when needed",
        },
        "external_actions_executed": False,
    }


def write_fidelity_outputs(output_dir: str | os.PathLike[str], package: Dict[str, Any]) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    public_segments = []
    all_ready = True
    for segment in package["segments"]:
        number = int(segment["segment_number"])
        segment_dir = output / f"segment-{number:03d}"
        segment_dir.mkdir(parents=True, exist_ok=True)
        plan = segment["plan"]
        report = segment["preflight"]
        write_json(segment_dir / "remake-plan.json", plan)
        write_compiled_outputs(segment_dir, segment["bundle"])
        write_json(segment_dir / "preflight-validation-report.json", report)
        all_ready = all_ready and bool(report["ready"])
        public_segments.append(
            {
                "segment_number": number,
                "directory": segment_dir.name,
                "ready": bool(report["ready"]),
                "global_start_ms": plan["segment_context"]["global_start_ms"],
                "global_end_ms": plan["segment_context"]["global_end_ms"],
            }
        )
    manifest = {
        "schema_version": package["schema_version"],
        "mode": package["mode"],
        "generation_call_count": package["generation_call_count"],
        "ready": all_ready,
        "segments": public_segments,
        "external_actions_executed": False,
    }
    write_json(output / "fidelity-package.json", manifest)
    write_json(output / "assembly-plan.json", package["assembly_plan"])
    return manifest


def _url_from_content(item: Dict[str, Any]) -> str:
    item_type = item.get("type")
    if item_type in {"image_url", "video_url", "audio_url"}:
        container = item.get(item_type, {})
        if isinstance(container, dict):
            return str(container.get("url", ""))
    return ""


def _is_local_path(value: str) -> bool:
    return (len(value) >= 3 and value[1:3] in {":\\", ":/"}) or value.startswith(("/", "\\\\"))


def validate_plan(video_dna: Dict[str, Any], plan: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    plan = ensure_editing_contract(plan)
    contract = plan.get("contract", {})
    expected_contract = {
        "generation_call_count": 1,
        "segmented_generation": False,
        "post_editing": False,
        "video_assembly": False,
    }
    for key, expected in expected_contract.items():
        if contract.get(key) != expected:
            errors.append(f"contract.{key} must be {expected!r}")
    target = plan.get("target", {})
    duration = target.get("duration_s")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 4 <= duration <= 15:
        errors.append("target.duration_s must be an integer from 4 through 15")
        duration_ms = None
    else:
        duration_ms = duration * 1000
    if target.get("ratio") not in ALLOWED_RATIOS:
        errors.append("target.ratio is not supported")
    if target.get("resolution") not in ALLOWED_RESOLUTIONS:
        errors.append("target.resolution is not supported")
    if not plan.get("product_distance", {}).get("reasons"):
        warnings.append("product distance has no evidence notes; add concrete category, shape, use-action, and scene reasons before final delivery")
    if plan.get("product_distance", {}).get("level") == "distant" and not plan.get("adaptation_ledger"):
        warnings.append("distant-category replacement has no adaptation ledger; document every physically necessary product-action change")

    ordered_source = sorted(video_dna.get("shots", []), key=lambda shot: int(shot.get("source_start_ms", 0)))
    previous_end = 0
    for shot in ordered_source:
        shot_id = str(shot.get("id", ""))
        start = shot.get("source_start_ms")
        end = shot.get("source_end_ms")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
            errors.append(f"source shot {shot_id} has an invalid time range")
            continue
        if start < previous_end:
            errors.append(f"source shot {shot_id} overlaps the previous shot")
        elif start > previous_end:
            warnings.append(f"source Video DNA has an unanalysed gap before shot {shot_id}: {previous_end}-{start}ms")
        previous_end = end
    source_duration = video_dna.get("media", {}).get("duration_ms")
    if isinstance(source_duration, int) and ordered_source and previous_end < source_duration:
        warnings.append(f"source Video DNA does not cover the final {source_duration - previous_end}ms")

    timeline = plan.get("timeline", [])
    if not timeline:
        errors.append("timeline must not be empty")
    else:
        cursor = 0
        timeline_ids = set()
        for item in timeline:
            item_id = str(item.get("id", ""))
            if not item_id or item_id in timeline_ids:
                errors.append(f"timeline id is empty or duplicated: {item_id!r}")
            timeline_ids.add(item_id)
            start = item.get("target_start_ms")
            end = item.get("target_end_ms")
            if start != cursor:
                errors.append(f"timeline {item_id} starts at {start}, expected {cursor}")
            if not isinstance(end, int) or not isinstance(start, int) or end <= start:
                errors.append(f"timeline {item_id} has invalid target range")
                continue
            cursor = end
        if duration_ms is not None and cursor != duration_ms:
            errors.append(f"timeline ends at {cursor}ms, expected {duration_ms}ms")

    editing = plan.get("editing_contract", {})
    if editing.get("expected_shot_count") != len(timeline):
        errors.append("editing_contract.expected_shot_count must equal timeline length")
    if editing.get("expected_cut_count") != max(0, len(timeline) - 1):
        errors.append("editing_contract.expected_cut_count must equal timeline length minus one")
    expected_cut_times = [int(item.get("target_start_ms", 0)) for item in timeline[1:]]
    if editing.get("expected_cut_times_ms") != expected_cut_times:
        errors.append("editing_contract.expected_cut_times_ms must match timeline boundaries")
    known_timeline_ids = {str(item.get("id")) for item in timeline}
    for pair in editing.get("merge_forbidden", []):
        if not isinstance(pair, list) or len(pair) != 2 or not set(str(item) for item in pair).issubset(known_timeline_ids):
            errors.append("editing_contract.merge_forbidden contains an invalid timeline pair")

    source_shots = {str(shot.get("id")): shot for shot in video_dna.get("shots", [])}
    covered_shots = {str(source_id) for item in timeline for source_id in item.get("source_shot_ids", [])}
    unknown_shots = covered_shots - set(source_shots)
    if unknown_shots:
        errors.append("timeline references unknown source shots: " + ", ".join(sorted(unknown_shots)))
    missing_must_shots = sorted(
        shot_id for shot_id, shot in source_shots.items() if shot.get("must_keep") and shot_id not in covered_shots
    )
    if missing_must_shots:
        errors.append("must-keep shots are missing: " + ", ".join(missing_must_shots))

    coverage_rows = plan.get("coverage", [])
    coverage_by_id = {str(row.get("source_element_id")): row for row in coverage_rows}
    source_elements = {str(item.get("id")): item for item in video_dna.get("source_elements", [])}
    for element_id, element in source_elements.items():
        row = coverage_by_id.get(element_id)
        if row is None:
            errors.append(f"source element has no coverage row: {element_id}")
            continue
        status = row.get("status")
        if status not in ALLOWED_COVERAGE:
            errors.append(f"source element {element_id} has invalid coverage status")
        if element.get("must_keep") and status == "omitted_with_reason":
            errors.append(f"must-keep source element is omitted: {element_id}")
        target_ids = set(str(item) for item in row.get("target_timeline_ids", []))
        if element.get("must_keep") and not target_ids:
            errors.append(f"must-keep source element has no target mapping: {element_id}")
        unknown_targets = target_ids - {str(item.get("id")) for item in timeline}
        if unknown_targets:
            errors.append(f"coverage for {element_id} references unknown timeline ids")
    omitted = plan.get("compression", {}).get("omitted_source_shot_ids", [])
    if omitted:
        warnings.append(f"single-call compression records {len(omitted)} omitted lower-value source shots")
    if plan.get("compression", {}).get("requires_semantic_review"):
        warnings.append("semantic review is required because the source was compressed or timeline units were merged")
    return errors, warnings


def validate_bundle(
    product_profile: Dict[str, Any],
    video_dna: Dict[str, Any],
    plan: Dict[str, Any],
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    errors, warnings = validate_plan(video_dna, plan)
    contract = bundle.get("contract", {})
    if contract != plan.get("contract"):
        errors.append("compiled contract does not match remake plan")
    request = bundle.get("api_request")
    if not isinstance(request, dict):
        errors.append("api_request must be one JSON object")
        request = {}
    for key in FORBIDDEN_REQUEST_KEYS:
        if key in request:
            errors.append(f"unsupported or multi-stage request key is forbidden: {key}")
    duration = request.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 4 <= duration <= 15:
        errors.append("api_request.duration must be an integer from 4 through 15")
    if request.get("ratio") not in ALLOWED_RATIOS:
        errors.append("api_request.ratio is invalid")
    if request.get("resolution") not in ALLOWED_RESOLUTIONS:
        errors.append("api_request.resolution is invalid")
    model = str(request.get("model", ""))
    if "fast" in model.lower() and request.get("resolution") == "1080p":
        errors.append("Seedance 2.0 fast does not support 1080p")
    if not isinstance(request.get("generate_audio"), bool):
        errors.append("api_request.generate_audio must be boolean")

    content = request.get("content", [])
    if not isinstance(content, list):
        errors.append("api_request.content must be an array")
        content = []
    text_items = [item for item in content if isinstance(item, dict) and item.get("type") == "text"]
    images = [item for item in content if isinstance(item, dict) and item.get("type") == "image_url" and item.get("role") == "reference_image"]
    videos = [item for item in content if isinstance(item, dict) and (item.get("type") == "video_url" or item.get("role") == "reference_video")]
    audios = [item for item in content if isinstance(item, dict) and (item.get("type") == "audio_url" or item.get("role") == "reference_audio")]
    allowed_items = [
        item
        for item in content
        if isinstance(item, dict)
        and (
            item.get("type") == "text"
            or (item.get("type") == "image_url" and item.get("role") == "reference_image")
        )
    ]
    if len(text_items) != 1:
        errors.append("content must contain exactly one text prompt")
    if not 1 <= len(images) <= 9:
        errors.append("content must contain 1-9 product reference images")
    if videos:
        errors.append("content must not contain video items; the source video is for offline analysis only")
    if audios:
        errors.append("content must not contain audio items; audio is described in the standalone prompt")
    if len(allowed_items) != len(content):
        errors.append("content may contain only one text prompt and product reference images")
    prompt = str(bundle.get("prompt", ""))
    if text_items and text_items[0].get("text") != prompt:
        errors.append("text content does not equal compiled prompt")
    if "图片1" not in prompt:
        errors.append("prompt must explicitly bind 图片1")
    lowered_prompt = prompt.lower()
    if re.search(r"\bT\d{3}\b", prompt) or "执行于：" in prompt or "执行于:" in prompt:
        errors.append("prompt must not expose internal timeline IDs or dangling execution references")
    expected_shots = len(plan.get("timeline", []))
    expected_cuts = max(0, expected_shots - 1)
    if f"{expected_shots}个肉眼可区分的独立镜头" not in prompt or f"{expected_cuts}次清晰硬切" not in prompt:
        errors.append("prompt is missing the explicit shot-count and hard-cut contract")
    if len(prompt) > 8000:
        warnings.append(f"compiled prompt is {len(prompt)} characters; review repetition and keep execution-critical details prominent")
    for marker in FORBIDDEN_PROMPT_MARKERS:
        if marker.lower() in lowered_prompt:
            errors.append(f"prompt contains source-dependent wording: {marker}")
    for term in plan.get("prompt_exclusion_terms", []):
        if str(term).strip() and str(term).lower() in lowered_prompt:
            errors.append(f"prompt contains a source-only exclusion term: {term}")

    coverage_by_id = {str(row.get("source_element_id")): row for row in plan.get("coverage", [])}
    compacted_coverage = 0
    for element in video_dna.get("source_elements", []):
        if not element.get("must_keep"):
            continue
        row = coverage_by_id.get(str(element.get("id")), {})
        instruction = _target_direct_text(row.get("instruction", ""))
        if instruction and instruction not in prompt:
            compacted_coverage += 1
    if compacted_coverage:
        warnings.append(
            f"{compacted_coverage} must-keep coverage instructions were compacted into their mapped numbered shots; verify those shot descriptions during semantic review"
        )

    request_text = json.dumps(request, ensure_ascii=False)
    source_candidates = []
    source_asset = video_dna.get("source_asset", {})
    source = str(source_asset.get("source", "")).strip()
    if source:
        source_candidates.extend([source, source.replace("\\", "/").rsplit("/", 1)[-1]])
    source_asset_id = str(source_asset.get("asset_id", "")).strip()
    if source_asset_id:
        source_candidates.append(source_asset_id)
    for audio in video_dna.get("audio", {}).get("reference_assets", []):
        audio_source = str(audio.get("source", "")).strip()
        if audio_source:
            source_candidates.extend([audio_source, audio_source.replace("\\", "/").rsplit("/", 1)[-1]])
        audio_asset_id = str(audio.get("asset_id", "")).strip()
        if audio_asset_id:
            source_candidates.append(audio_asset_id)
    for candidate in {item for item in source_candidates if len(item) >= 3}:
        if candidate.lower() in lowered_prompt or candidate.lower() in request_text.lower():
            errors.append(f"source media identifier leaked into prompt or API request: {candidate}")

    manifest = bundle.get("upload_manifest", {})
    assets = manifest.get("assets", []) if isinstance(manifest, dict) else []
    manifest_values = {str(asset.get("api_placeholder")) for asset in assets if isinstance(asset, dict)}
    if not any(asset.get("role") == "reference_image" for asset in assets if isinstance(asset, dict)):
        errors.append("upload manifest is missing a product image")
    unexpected_manifest_assets = [
        asset
        for asset in assets
        if isinstance(asset, dict)
        and (asset.get("content_type") != "image_url" or asset.get("role") != "reference_image")
    ]
    if unexpected_manifest_assets:
        errors.append("upload manifest may contain only product reference images")
    if len(assets) != len(images):
        errors.append("upload manifest and request must contain the same number of product images")
    for item in images:
        url = _url_from_content(item)
        if not url:
            errors.append(f"{item.get('type')} is missing its URL")
        if _is_local_path(url):
            errors.append("local paths may appear only in upload-manifest.json, not in the API request")
        if url not in manifest_values:
            errors.append(f"request asset is not mapped in upload manifest: {url}")
    for asset in assets:
        if not str(asset.get("source", "")):
            errors.append(f"manifest asset {asset.get('asset_id')} has an empty source")
        if asset.get("requires_upload") and not str(asset.get("api_placeholder", "")).startswith("${"):
            errors.append(f"local asset {asset.get('asset_id')} must use a URL placeholder")

    report = {
        "schema_version": SCHEMA_VERSION,
        "ready": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "generation_call_count": int(contract.get("generation_call_count", 1)),
            "text_items": len(text_items),
            "reference_images": len(images),
            "reference_videos": len(videos),
            "reference_audios": len(audios),
            "timeline_units": len(plan.get("timeline", [])),
            "source_elements": len(video_dna.get("source_elements", [])),
            "covered_source_elements": len(plan.get("coverage", [])),
            "expected_shots": len(plan.get("timeline", [])),
            "expected_cuts": max(0, len(plan.get("timeline", [])) - 1),
            "recommended_generation_mode": ensure_editing_contract(plan)["generation_strategy"]["recommended_mode"],
        },
    }
    return report


def write_compiled_outputs(output_dir: str | os.PathLike[str], bundle: Dict[str, Any]) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "seedance-prompt.txt").write_text(bundle["prompt"], encoding="utf-8", newline="\n")
    write_json(destination / "upload-manifest.json", bundle["upload_manifest"])
    write_json(destination / "seedance-request.json", bundle["api_request"])
