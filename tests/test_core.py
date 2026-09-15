import copy
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from remake_core import (  # noqa: E402
    build_single_call_plan,
    choose_segment_ranges,
    compile_bundle,
    ensure_editing_contract,
    load_json,
    validate_bundle,
    write_compiled_outputs,
)
from validate_generated_video import compare_structure  # noqa: E402
from prepare_analysis_pack import (  # noqa: E402
    _cache_key,
    _manifest_outputs_exist,
    scene_extraction_failed,
)
from check_release_safety import audit as audit_release  # noqa: E402


class ProductVideoRemakeTests(unittest.TestCase):
    def setUp(self):
        self.product = load_json(FIXTURES / "product-profile.json")
        self.short_video = load_json(FIXTURES / "video-dna-short.json")
        self.long_video = load_json(FIXTURES / "video-dna-long.json")

    def test_short_source_compiles_one_request_with_product_images_only(self):
        plan = build_single_call_plan(self.short_video)
        bundle = compile_bundle(self.product, self.short_video, plan)
        report = validate_bundle(self.product, self.short_video, plan, bundle)
        self.assertTrue(report["ready"], report["errors"])
        self.assertEqual(1, bundle["contract"]["generation_call_count"])
        self.assertFalse(bundle["contract"]["segmented_generation"])
        content = bundle["api_request"]["content"]
        self.assertEqual(1, sum(item.get("type") == "text" for item in content))
        self.assertGreaterEqual(sum(item.get("role") == "reference_image" for item in content), 1)
        self.assertFalse(any(item.get("type") in {"video_url", "audio_url"} for item in content))
        self.assertNotIn("${REFERENCE_VIDEO_URL}", json.dumps(bundle["api_request"], ensure_ascii=False))
        self.assertIn("图片1", bundle["prompt"])
        self.assertNotIn("视频1", bundle["prompt"])
        self.assertNotIn("参考视频", bundle["prompt"])
        self.assertNotIn("原商品", bundle["prompt"])
        self.assertIn("同一女主从明显丰满变得明显苗条", bundle["prompt"])
        self.assertNotRegex(bundle["prompt"], r"\bT\d{3}\b")
        self.assertNotIn("执行于：", bundle["prompt"])
        self.assertIn("最高优先级剪辑合同", bundle["prompt"])
        self.assertIn(f"{len(plan['timeline'])}个肉眼可区分的独立镜头", bundle["prompt"])

    def test_plan_has_explicit_editing_contract_and_human_shot_labels(self):
        plan = build_single_call_plan(self.short_video)
        editing = plan["editing_contract"]
        self.assertEqual(len(plan["timeline"]), editing["expected_shot_count"])
        self.assertEqual(len(plan["timeline"]) - 1, editing["expected_cut_count"])
        self.assertEqual([item["target_start_ms"] for item in plan["timeline"][1:]], editing["expected_cut_times_ms"])
        self.assertTrue(all(item["must_be_distinct"] for item in plan["timeline"]))
        prompt = compile_bundle(self.product, self.short_video, plan)["prompt"]
        self.assertIn("镜头1（", prompt)

    def test_dense_timeline_recommends_and_splits_high_fidelity_mode(self):
        plan = build_single_call_plan(self.short_video, target_duration_s=12)
        template = plan["timeline"][0]
        dense = []
        for index in range(10):
            item = copy.deepcopy(template)
            item["id"] = f"T{index + 1:03d}"
            item["target_start_ms"] = index * 1200
            item["target_end_ms"] = (index + 1) * 1200
            dense.append(item)
        plan["timeline"] = dense
        plan = ensure_editing_contract(plan)
        self.assertEqual("high_fidelity_segmented", plan["generation_strategy"]["recommended_mode"])
        ranges = choose_segment_ranges(plan)
        self.assertEqual([(0, 5), (5, 10)], ranges)

    def test_postflight_detects_missing_cuts_and_wrong_ratio(self):
        plan = build_single_call_plan(self.short_video)
        report = compare_structure(
            plan,
            {"duration_ms": 8000, "width": 864, "height": 496, "frame_rate": "24/1"},
            [],
        )
        self.assertFalse(report["structural_ready"])
        self.assertIsNone(report["fidelity_ready"])
        self.assertTrue(report["semantic_review_required"])

    def test_long_source_is_compressed_to_one_15_second_timeline(self):
        plan = build_single_call_plan(self.long_video)
        self.assertEqual(15, plan["target"]["duration_s"])
        self.assertEqual(15000, plan["timeline"][-1]["target_end_ms"])
        self.assertEqual("single_call_semantic_compression", plan["compression"]["strategy"])
        self.assertIn("S003", plan["compression"]["omitted_source_shot_ids"])
        self.assertIn("S006", plan["compression"]["omitted_source_shot_ids"])
        covered = {source_id for item in plan["timeline"] for source_id in item["source_shot_ids"]}
        must_keep = {shot["id"] for shot in self.long_video["shots"] if shot.get("must_keep")}
        self.assertTrue(must_keep.issubset(covered))
        for row in plan["coverage"]:
            if row["source_element_id"] in {"E001", "E002", "E003", "E004", "E005"}:
                self.assertNotEqual("omitted_with_reason", row["status"])

    def test_audio_beats_are_mapped_into_target_timeline(self):
        plan = build_single_call_plan(self.short_video)
        anchors = [value for item in plan["timeline"] for value in item.get("target_beat_anchors_ms", [])]
        self.assertTrue(anchors)
        self.assertTrue(all(0 <= value <= 8000 for value in anchors))
        bundle = compile_bundle(self.product, self.short_video, plan)
        self.assertIn("目标踩点", bundle["prompt"])

    def test_source_shorter_than_four_seconds_expands_to_one_four_second_request(self):
        video = copy.deepcopy(self.short_video)
        video["media"]["duration_ms"] = 3000
        video["shots"][-1]["source_end_ms"] = 3000
        video["shots"][-1]["source_start_ms"] = 2500
        video["shots"][1]["source_end_ms"] = 2500
        video["shots"][1]["source_start_ms"] = 1000
        video["shots"][0]["source_end_ms"] = 1000
        plan = build_single_call_plan(video)
        self.assertEqual(4, plan["target"]["duration_s"])
        self.assertEqual(4000, plan["timeline"][-1]["target_end_ms"])

    def test_remote_source_video_is_offline_only(self):
        plan = build_single_call_plan(self.long_video)
        bundle = compile_bundle(self.product, self.long_video, plan)
        serialized = json.dumps(bundle, ensure_ascii=False)
        self.assertNotIn("https://assets.example.com/reference-long.mp4", serialized)
        self.assertFalse(any(item.get("role") == "reference_video" for item in bundle["api_request"]["content"]))
        self.assertFalse(any(item.get("role") == "reference_video" for item in bundle["upload_manifest"]["assets"]))

    def test_validation_rejects_video_or_audio_content(self):
        plan = build_single_call_plan(self.short_video)
        bundle = compile_bundle(self.product, self.short_video, plan)
        broken = copy.deepcopy(bundle)
        broken["api_request"]["content"].append(
            {"type": "video_url", "video_url": {"url": "https://assets.example.com/source.mp4"}, "role": "reference_video"}
        )
        report = validate_bundle(self.product, self.short_video, plan, broken)
        self.assertFalse(report["ready"])
        self.assertTrue(any("must not contain video" in error for error in report["errors"]))

    def test_validation_rejects_source_dependent_prompt_wording(self):
        plan = build_single_call_plan(self.short_video)
        bundle = compile_bundle(self.product, self.short_video, plan)
        broken = copy.deepcopy(bundle)
        broken["prompt"] += "请参考视频还原。"
        broken["api_request"]["content"][0]["text"] = broken["prompt"]
        report = validate_bundle(self.product, self.short_video, plan, broken)
        self.assertFalse(report["ready"])
        self.assertTrue(any("source-dependent wording" in error for error in report["errors"]))

    def test_validation_rejects_second_call_shape_and_unsupported_fields(self):
        plan = build_single_call_plan(self.short_video)
        bundle = compile_bundle(self.product, self.short_video, plan)
        broken = copy.deepcopy(bundle)
        broken["api_request"]["segments"] = [{"duration": 4}, {"duration": 4}]
        broken["api_request"]["frames"] = 193
        report = validate_bundle(self.product, self.short_video, plan, broken)
        self.assertFalse(report["ready"])
        self.assertTrue(any("forbidden" in error for error in report["errors"]))

    def test_fast_model_rejects_1080p(self):
        plan = build_single_call_plan(
            self.short_video,
            resolution="1080p",
            model="doubao-seedance-2-0-fast-test",
        )
        bundle = compile_bundle(self.product, self.short_video, plan)
        report = validate_bundle(self.product, self.short_video, plan, bundle)
        self.assertFalse(report["ready"])
        self.assertTrue(any("fast does not support 1080p" in error for error in report["errors"]))

    def test_compiled_files_contain_no_local_paths_in_request(self):
        plan = build_single_call_plan(self.short_video)
        bundle = compile_bundle(self.product, self.short_video, plan)
        with tempfile.TemporaryDirectory() as directory:
            write_compiled_outputs(directory, bundle)
            request_text = (Path(directory) / "seedance-request.json").read_text(encoding="utf-8")
            manifest_text = (Path(directory) / "upload-manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("fixtures/product.png", request_text)
            self.assertIn("fixtures/product.png", manifest_text)
            self.assertNotIn("reference.mp4", manifest_text)


class SchemaFilesTests(unittest.TestCase):
    def test_schema_files_are_valid_json(self):
        schema_dir = ROOT / "schemas"
        files = sorted(schema_dir.glob("*.schema.json"))
        self.assertGreaterEqual(len(files), 4)
        for path in files:
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", value["$schema"])
            self.assertIn("$id", value)

    def test_runtime_scripts_contain_no_generation_api_client(self):
        forbidden = ("requests.post", "httpx.post", "urlopen(", "ark.cn-beijing.volces.com/api/v3")
        for path in sorted(SCRIPTS.glob("*.py")):
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                self.assertNotIn(token.lower(), text, f"{path.name} contains an API-call implementation")

    def test_skill_links_resolve_and_old_provider_is_absent(self):
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        linked_paths = re.findall(r"\[[^\]]+\]\(([^)]+)\)", skill_text)
        self.assertTrue(linked_paths)
        for linked_path in linked_paths:
            if linked_path.startswith(("http://", "https://")):
                continue
            self.assertTrue((ROOT / linked_path).exists(), linked_path)
        lowered = skill_text.lower()
        self.assertNotIn("wan3", lowered)
        self.assertNotIn("dashscope", lowered)

    def test_no_cut_ffmpeg_message_is_treated_as_empty_result_not_failure(self):
        self.assertFalse(scene_extraction_failed(1, "No filtered frames for output stream", []))
        self.assertFalse(scene_extraction_failed(1, "Nothing was written into output file", []))
        self.assertTrue(scene_extraction_failed(1, "Invalid filter syntax", []))

    def test_analysis_cache_key_is_stable_and_parameter_sensitive(self):
        signature = {"resolved_path": "fixtures/reference.mp4", "size": 10, "mtime_ns": 20}
        settings = {"dense_fps": 6.0, "scene_threshold": 0.22}
        first = _cache_key(signature, settings)
        second = _cache_key(copy.deepcopy(signature), copy.deepcopy(settings))
        changed = _cache_key(signature, {"dense_fps": 8.0, "scene_threshold": 0.22})
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)

    def test_analysis_manifest_requires_all_cached_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dense = root / "dense.jpg"
            cut = root / "cut.jpg"
            sheet = root / "sheet.jpg"
            audio = root / "audio.wav"
            for path in (dense, cut, sheet, audio):
                path.write_bytes(b"evidence")
            manifest = {
                "dense_frames": [str(dense)],
                "cut_candidate_frames": [str(cut)],
                "overview_sheets": [{"path": str(sheet)}],
                "analysis_audio": str(audio),
            }
            self.assertTrue(_manifest_outputs_exist(manifest))
            sheet.unlink()
            self.assertFalse(_manifest_outputs_exist(manifest))

    def test_release_safety_audit_accepts_repository(self):
        self.assertEqual([], audit_release(ROOT))

    def test_release_safety_audit_detects_personal_path_and_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.txt").write_text(
                "source=" + "C:/" + "Users/alice/Desktop/client/reference.mp4",
                encoding="utf-8",
            )
            (root / "customer.mp4").write_bytes(b"not real media")
            findings = audit_release(root)
            self.assertTrue(any("Windows user directory" in item for item in findings))
            self.assertTrue(any("blocked file type" in item for item in findings))


if __name__ == "__main__":
    unittest.main()
