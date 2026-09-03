from __future__ import annotations

import asyncio
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from PIL import Image

from webui import server
from webui.imagegen import PromptReview
from webui.server import (
    _apply_asset_contract,
    _apply_art_direction,
    _effective_sprite_size,
    _reference_to_data_uri,
    _sprite_processing_args,
    _validate_sprite_request,
    _write_download_bundle,
    _write_map_bundle_metadata,
)


def png_bytes() -> bytes:
    content = BytesIO()
    Image.new("RGBA", (16, 16), (80, 140, 220, 255)).save(content, format="PNG")
    return content.getvalue()


class SpriteRequestValidationTests(unittest.TestCase):
    def test_allows_dense_asset_animation_grid(self) -> None:
        frame = _validate_sprite_request("asset", "cast", "", 32)

        self.assertEqual((frame["rows"], frame["cols"]), (4, 8))

    def test_rejects_unsupported_or_fixed_frame_counts(self) -> None:
        with self.assertRaisesRegex(ValueError, "帧数不受支持"):
            _validate_sprite_request("asset", "cast", "", 3)
        with self.assertRaisesRegex(ValueError, "固定为 16 帧"):
            _validate_sprite_request("player", "player_sheet", "", 12)

    def test_requires_an_npc_role(self) -> None:
        with self.assertRaisesRegex(ValueError, "NPC 类型"):
            _validate_sprite_request("npc", "npc_walk", "", 4)

    def test_rejects_an_npc_role_on_other_sprite_targets(self) -> None:
        with self.assertRaisesRegex(ValueError, "仅适用于 NPC"):
            _validate_sprite_request("creature", "idle", "guard", 4)

    def test_sprite_processing_always_enables_consistent_strict_qc(self) -> None:
        grounded = _sprite_processing_args("creature", "idle", 12)
        detached = _sprite_processing_args("asset", "impact", 12)
        humanoid = _sprite_processing_args("player", "player_walk", 8)

        self.assertEqual(grounded[:2], ["--align", "feet"])
        self.assertEqual(detached[:2], ["--align", "center"])
        self.assertIn("--shared-scale", grounded)
        self.assertIn("--strict-qc", grounded)
        self.assertIn("--shared-scale", detached)
        self.assertIn("--strict-qc", detached)
        self.assertIn("--max-body-scale-cv", humanoid)
        self.assertIn("0.08", humanoid)
        self.assertIn("--max-anchor-y-std", humanoid)
        self.assertIn("0.05", humanoid)

    def test_dense_grids_raise_source_resolution_and_output_cell_size(self) -> None:
        self.assertEqual(_effective_sprite_size("1024x1024", server.frame_preset(4)), "1024x1024")
        self.assertEqual(_effective_sprite_size("1024x1024", server.frame_preset(24)), "2048x2048")
        self.assertEqual(_effective_sprite_size("1024x1024", server.frame_preset(32)), "2048x2048")
        self.assertIn("--cell-size", _sprite_processing_args("asset", "cast", 24))
        self.assertIn("192", _sprite_processing_args("asset", "cast", 32))

    def test_reference_data_uri_validates_image_content(self) -> None:
        uri = _reference_to_data_uri(png_bytes())

        self.assertTrue(uri.startswith("data:image/png;base64,"))
        with self.assertRaises(server.HTTPException) as raised:
            _reference_to_data_uri(b"not an image")
        self.assertEqual(raised.exception.status_code, 400)

    def test_selected_art_direction_is_reapplied_after_a_rewrite(self) -> None:
        style = "watercolor fantasy illustration, translucent pigment texture"
        rewritten = "A transparent game sprite sheet with no labels."

        prompt = _apply_art_direction(rewritten, style)

        self.assertIn(style, prompt)
        self.assertTrue(prompt.endswith("Do not mix visual styles."))
        self.assertEqual(_apply_art_direction(prompt, style), prompt)

    def test_map_delivery_contract_excludes_all_character_elements(self) -> None:
        prompt = _apply_asset_contract("A village requested by an NPC", "map", "watercolor")

        self.assertIn("environment only", prompt)
        self.assertIn("Do not include people, NPCs, playable characters", prompt)
        self.assertIn("complete opaque baked scene", prompt)
        self.assertIn("watercolor", prompt)

    def test_map_request_rejects_sprite_selection_fields(self) -> None:
        with self.assertRaises(server.HTTPException) as raised:
            asyncio.run(
                server.api_generate(
                    kind="map",
                    target="npc",
                    mode="npc",
                    brief="quiet forest village",
                    style=server.DEFAULT_STYLE_ID,
                    style_note="",
                    size="1024x1024",
                    frame_count=1,
                    role="guard",
                    references=[],
                )
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("场景请求不能包含", raised.exception.detail)

    def test_job_slots_admit_only_the_configured_concurrent_limit(self) -> None:
        old_slots = server._job_slots
        old_lock = server._job_submission_lock
        server._job_slots = asyncio.BoundedSemaphore(server.MAX_ACTIVE_JOBS)
        server._job_submission_lock = asyncio.Lock()

        async def reserve_all() -> list[bool]:
            results = await asyncio.gather(
                *(server._reserve_job_slot() for _ in range(server.MAX_ACTIVE_JOBS + 1))
            )
            for accepted in results:
                if accepted:
                    server._release_job_slot()
            return results

        try:
            results = asyncio.run(reserve_all())
        finally:
            server._job_slots = old_slots
            server._job_submission_lock = old_lock

        self.assertEqual(results.count(True), server.MAX_ACTIVE_JOBS)
        self.assertEqual(results.count(False), 1)

    def test_api_reserves_capacity_before_concurrent_reference_uploads(self) -> None:
        old_slots = server._job_slots
        old_lock = server._job_submission_lock
        old_save_references = server._save_references
        old_create_record = server._create_record
        old_pipeline = server._pipeline
        old_jobs = server._jobs
        old_active_jobs = server._active_jobs
        server._job_slots = asyncio.BoundedSemaphore(server.MAX_ACTIVE_JOBS)
        server._job_submission_lock = asyncio.Lock()
        server._jobs = {}
        server._active_jobs = set()

        async def delayed_save_references(_job: str, _references: list[object]) -> list[str]:
            await asyncio.sleep(0)
            return []

        async def inert_pipeline(*_args: object) -> None:
            return None

        async def ignored_record(*_args: object, **_kwargs: object) -> None:
            return None

        async def submit() -> int:
            try:
                result = await server.api_generate(
                    kind="sprite",
                    target="creature",
                    mode="idle",
                    brief="bronze wolf guardian",
                    style=server.DEFAULT_STYLE_ID,
                    style_note="",
                    size="1024x1024",
                    frame_count=4,
                    role="",
                    references=[],
                )
                return 200 if "job" in result else 500
            except server.HTTPException as exc:
                return exc.status_code

        async def submit_all() -> list[int]:
            return await asyncio.gather(*(submit() for _ in range(3)))

        server._save_references = delayed_save_references
        server._create_record = ignored_record
        server._pipeline = inert_pipeline
        try:
            statuses = asyncio.run(submit_all())
        finally:
            for _ in range(sum(status == 200 for status in locals().get("statuses", []))):
                server._release_job_slot()
            server._job_slots = old_slots
            server._job_submission_lock = old_lock
            server._save_references = old_save_references
            server._create_record = old_create_record
            server._pipeline = old_pipeline
            server._jobs = old_jobs
            server._active_jobs = old_active_jobs

        self.assertEqual(statuses.count(200), server.MAX_ACTIVE_JOBS)
        self.assertEqual(statuses.count(429), 1)


class PersistedJobAndBundleTests(unittest.TestCase):
    def test_persisted_record_exposes_terminal_recovery_fields(self) -> None:
        original_db = server.DB
        with tempfile.TemporaryDirectory() as temporary:
            server.DB = Path(temporary) / "jobs.sqlite3"
            try:
                server._init_db()
                server._create_record_sync(
                    "completed-job", "sprite", "creature", "idle", "wolf", "像素",
                    "2048x2048", 32, "4x8", 0,
                )
                server._update_record_sync(
                    "completed-job",
                    status="completed",
                    prompt="final prompt",
                    raw_file="completed-job/raw-qc-2.png",
                    output_files=json.dumps(["completed-job/out/animation.webp"]),
                    bundle_file="completed-job/out/sprite-forge-assets.zip",
                )
                record = server._get_record_sync("completed-job")
            finally:
                server.DB = original_db

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["raw_url"], "/files/completed-job/raw-qc-2.png")
        self.assertEqual(record["bundle_url"], "/files/completed-job/out/sprite-forge-assets.zip")
        self.assertEqual(record["files"], ["/files/completed-job/out/animation.webp"])

    def test_job_endpoint_returns_persisted_snapshot_and_404_for_missing_job(self) -> None:
        original = server._get_record
        snapshot = {"id": "done-job", "status": "completed", "files": []}

        async def found(_job: str) -> dict:
            return snapshot

        async def missing(_job: str) -> None:
            return None

        try:
            server._get_record = found
            self.assertEqual(asyncio.run(server.api_job("done-job")), snapshot)
            server._get_record = missing
            with self.assertRaises(server.HTTPException) as raised:
                asyncio.run(server.api_job("gone-job"))
        finally:
            server._get_record = original
        self.assertEqual(raised.exception.status_code, 404)

    def test_sprite_bundle_has_qc_reproduction_files_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            names = [
                "idle-1.png", "raw-sheet.png", "raw-sheet-clean.png",
                "pipeline-meta.json", "prompt-used.txt",
            ]
            for name in names:
                (output / name).write_bytes(b"fixture")
            bundle = output / "sprite-forge-assets.zip"
            image_paths = sorted(path for path in output.iterdir() if path.suffix == ".png")
            _write_download_bundle(
                bundle,
                [
                    *image_paths,
                    output / "pipeline-meta.json",
                    output / "prompt-used.txt",
                    output / "raw-sheet.png",
                    output / "raw-sheet-clean.png",
                ],
            )
            with ZipFile(bundle) as archive:
                names = archive.namelist()

        self.assertEqual(len(names), len(set(names)))
        self.assertIn("pipeline-meta.json", names)
        self.assertIn("prompt-used.txt", names)

    def test_map_bundle_declares_a_non_editable_baked_scene_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            raw = work / "raw.png"
            raw.write_bytes(png_bytes())
            files = _write_map_bundle_metadata(
                work,
                raw,
                prompt="top-down game scene",
                brief="forest shrine",
                style="水彩奇幻",
                requested_size="1024x1024",
                source_dimensions=(16, 16),
            )
            manifest = json.loads((work / "map-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual({path.name for path in files}, {"raw.png", "map.prompt.txt", "map-manifest.json"})
        self.assertEqual(manifest["schema"], "agent-sprite-forge.map-bundle.v1")
        self.assertEqual(manifest["map_mode"], "baked_scene_mode")
        self.assertEqual(manifest["visual_model"], "baked_raster")
        self.assertEqual(manifest["runtime_object_model"], "none")
        self.assertEqual(manifest["collision_model"], "none")

    def test_qc_failure_recovers_prompt_and_regenerates_once(self) -> None:
        old_out = server.OUT
        old_jobs = server._jobs
        old_refine = server.imagegen.refine_prompt
        old_review = server.imagegen.review_prompt
        old_generate = server.imagegen.generate
        old_recover = server.imagegen.recover_prompt
        old_run = server._run
        old_update = server._update_record
        old_release = server._release_job_slot
        old_retire = server._retire_job
        generated_prompts: list[str] = []
        process_args: list[list[str]] = []

        async def refine(*_args: object, **_kwargs: object) -> str:
            return "bronze wolf guardian"

        async def review(prompt: str, *_args: object, **_kwargs: object) -> PromptReview:
            return PromptReview("pass", "low", prompt, [])

        async def generate(prompt: str, **_kwargs: object) -> bytes:
            generated_prompts.append(prompt)
            return png_bytes()

        async def recover(prompt: str, *_args: object, **_kwargs: object) -> PromptReview:
            return PromptReview("retry", "low", f"{prompt} repaired", [])

        async def update(*_args: object, **_kwargs: object) -> None:
            return None

        async def retire(*_args: object, **_kwargs: object) -> None:
            return None

        def run(args: list[str]) -> str:
            if args[1] == "build-prompt":
                path = Path(args[args.index("--write-json") + 1])
                path.write_text(json.dumps({"generated_prompt": "initial sprite prompt"}), encoding="utf-8")
                return ""
            if args[1] == "process":
                process_args.append(args)
                output = Path(args[args.index("--output-dir") + 1])
                if len(process_args) == 1:
                    raise RuntimeError("QC failed: source edge touch")
                for name in (
                    "idle-1.png", "raw-sheet.png", "raw-sheet-clean.png",
                    "sheet-transparent.png", "animation.webp",
                ):
                    (output / name).write_bytes(png_bytes())
                (output / "pipeline-meta.json").write_text(
                    json.dumps({"qc_summary": {"valid_frame_count": 4, "frame_count": 4}}),
                    encoding="utf-8",
                )
                (output / "prompt-used.txt").write_text("repaired prompt", encoding="utf-8")
                return ""
            raise AssertionError(args)

        with tempfile.TemporaryDirectory() as temporary:
            server.OUT = Path(temporary)
            server._jobs = {"qc-job": asyncio.Queue()}
            server.imagegen.refine_prompt = refine
            server.imagegen.review_prompt = review
            server.imagegen.generate = generate
            server.imagegen.recover_prompt = recover
            server._run = run
            server._update_record = update
            server._release_job_slot = lambda: None
            server._retire_job = retire
            try:
                asyncio.run(
                    server._pipeline(
                        "qc-job", "sprite", "creature", "idle", "wolf", "像素", "pixel art",
                        "1024x1024", "1024x1024", [], "", server.frame_preset(4),
                    )
                )
                events = []
                while not server._jobs["qc-job"].empty():
                    events.append(server._jobs["qc-job"].get_nowait())
                bundle = server.OUT / "qc-job" / "out" / "sprite-forge-assets.zip"
                with ZipFile(bundle) as archive:
                    bundle_names = archive.namelist()
            finally:
                server.OUT = old_out
                server._jobs = old_jobs
                server.imagegen.refine_prompt = old_refine
                server.imagegen.review_prompt = old_review
                server.imagegen.generate = old_generate
                server.imagegen.recover_prompt = old_recover
                server._run = old_run
                server._update_record = old_update
                server._release_job_slot = old_release
                server._retire_job = old_retire

        self.assertEqual(len(generated_prompts), 2)
        self.assertEqual(len(process_args), 2)
        self.assertIn("--prompt", process_args[-1])
        self.assertIn("repaired", process_args[-1][process_args[-1].index("--prompt") + 1])
        self.assertIn("pipeline-meta.json", bundle_names)
        self.assertIn("prompt-used.txt", bundle_names)
        self.assertIn("raw-qc-2.png", bundle_names)
        self.assertTrue(any(event and event["type"] == "done" for event in events))


if __name__ == "__main__":
    unittest.main()
