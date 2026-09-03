"""agent-sprite-forge 演示服务。

复用 skills/generate2dsprite 的提示词模板与后处理脚本，
出图环节由 tt-image-2 承担（原项目依赖宿主 agent 的内置 image_gen）。
"""
from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from io import BytesIO
import json
import logging
import mimetypes
import shutil
import sqlite3
import subprocess
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TypeVar

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

try:
    import imagegen
except ModuleNotFoundError:  # Allows tests to import webui.server from the repo root.
    from webui import imagegen

try:
    from catalog import (
        DEFAULT_STYLE_ID,
        FIXED_FRAME_COUNTS,
        NPC_ROLES,
        SIZE_OPTIONS,
        TARGET_MODES,
        frame_preset,
        public_options,
        requires_custom_grid,
        resolve_style,
    )
except ModuleNotFoundError:  # Allows tests to import webui.server from the repo root.
    from webui.catalog import (
        DEFAULT_STYLE_ID,
        FIXED_FRAME_COUNTS,
        NPC_ROLES,
        SIZE_OPTIONS,
        TARGET_MODES,
        frame_preset,
        public_options,
        requires_custom_grid,
        resolve_style,
    )

mimetypes.add_type("image/webp", ".webp")

LOGGER = logging.getLogger("sprite_forge.pipeline")

ROOT = Path(__file__).resolve().parent.parent
SPRITE = ROOT / "skills" / "generate2dsprite" / "scripts" / "generate2dsprite.py"
OUT = ROOT / "demo_out"
DB = ROOT / "sprite_forge.sqlite3"
PY = ROOT / ".venv" / "bin" / "python"
OUT.mkdir(exist_ok=True)
MAX_REFERENCE_FILES = 14
MAX_REFERENCE_BYTES = 40 * 1024 * 1024
MAX_REFERENCE_PIXELS = 32_000_000
MAX_ACTIVE_JOBS = 2
IMAGE_SUFFIXES = {".png", ".webp"}
IMAGE_EXTENSIONS = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
    "GIF": ".gif",
    "BMP": ".bmp",
    "TIFF": ".tiff",
}
IMAGE_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}

MAX_IMAGE_ATTEMPTS = 2
MAX_QC_ATTEMPTS = 2
MIN_SOURCE_CELL_SIZE = 192
DB_BUSY_TIMEOUT_MS = 12_000
DB_LOCK_RETRIES = 4
DB_RETRY_DELAY_SECONDS = 0.15
SIZE_DIMENSIONS = {
    size: tuple(int(value) for value in size.split("x"))
    for size in SIZE_OPTIONS
}

app = FastAPI(title="Agent Sprite Forge Demo")
_jobs: dict[str, asyncio.Queue] = {}
_active_jobs: set[str] = set()
# A job is admitted before any request-time I/O (notably reference uploads).
# The lock makes the availability check and reservation one atomic operation.
_job_slots = asyncio.BoundedSemaphore(MAX_ACTIVE_JOBS)
_job_submission_lock = asyncio.Lock()

_DBResult = TypeVar("_DBResult")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB, timeout=DB_BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout = {DB_BUSY_TIMEOUT_MS}")
    return conn


def _run_db(operation: Callable[[sqlite3.Connection], _DBResult]) -> _DBResult:
    """Run a short SQLite transaction with bounded lock recovery and close it."""
    for attempt in range(DB_LOCK_RETRIES):
        conn = _open_db()
        try:
            result = operation(conn)
            conn.commit()
            return result
        except sqlite3.OperationalError as exc:
            conn.rollback()
            locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if not locked or attempt == DB_LOCK_RETRIES - 1:
                raise
            time.sleep(DB_RETRY_DELAY_SECONDS * (attempt + 1))
        finally:
            conn.close()
    raise RuntimeError("SQLite operation exhausted retries")


def _init_db() -> None:
    def initialize(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                job_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                target TEXT NOT NULL,
                mode TEXT NOT NULL,
                brief TEXT NOT NULL,
                style TEXT NOT NULL,
                size TEXT NOT NULL,
                frame_count INTEGER NOT NULL DEFAULT 1,
                frame_layout TEXT NOT NULL DEFAULT '',
                reference_count INTEGER NOT NULL DEFAULT 0,
            subject TEXT NOT NULL DEFAULT '',
            prompt TEXT NOT NULL DEFAULT '',
            external_task_id TEXT NOT NULL DEFAULT '',
            bundle_file TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '',
                raw_file TEXT NOT NULL DEFAULT '',
                output_files TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(assets)")}
        if "external_task_id" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN external_task_id TEXT NOT NULL DEFAULT ''")
        if "bundle_file" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN bundle_file TEXT NOT NULL DEFAULT ''")
        if "frame_count" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN frame_count INTEGER NOT NULL DEFAULT 1")
            conn.execute("UPDATE assets SET frame_count = 4 WHERE kind = 'sprite'")
        if "frame_layout" not in columns:
            conn.execute("ALTER TABLE assets ADD COLUMN frame_layout TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            UPDATE assets
            SET status = 'failed',
                error = CASE
                    WHEN error = '' THEN '服务重启中断了任务，请重新生成'
                    ELSE error
                END,
                updated_at = ?
            WHERE status IN ('queued', 'planning', 'generating', 'processing')
            """,
            (_now(),),
        )
    _run_db(initialize)


def _create_record_sync(
    job: str,
    kind: str,
    target: str,
    mode: str,
    brief: str,
    style: str,
    size: str,
    frame_count: int,
    frame_layout: str,
    reference_count: int,
) -> None:
    now = _now()
    def create(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO assets (
                job_id, created_at, updated_at, kind, target, mode,
                brief, style, size, frame_count, frame_layout, reference_count, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job, now, now, kind, target, mode, brief, style, size,
                frame_count, frame_layout, reference_count, "queued",
            ),
        )
    _run_db(create)


def _update_record_sync(job: str, **fields: str) -> None:
    allowed = {
        "subject", "prompt", "external_task_id", "bundle_file", "status", "error", "raw_file", "output_files"
    }
    values = {key: value for key, value in fields.items() if key in allowed}
    if not values:
        return
    values["updated_at"] = _now()
    assignment = ", ".join(f"{key} = ?" for key in values)
    def update(conn: sqlite3.Connection) -> None:
        conn.execute(
            f"UPDATE assets SET {assignment} WHERE job_id = ?",
            (*values.values(), job),
        )
    _run_db(update)


def _record_to_dict(row: sqlite3.Row) -> dict:
    output_files = json.loads(row["output_files"] or "[]")
    return {
        "id": row["job_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "kind": row["kind"],
        "target": row["target"],
        "mode": row["mode"],
        "brief": row["brief"],
        "style": row["style"],
        "size": row["size"],
        "frame_count": row["frame_count"],
        "frame_layout": row["frame_layout"],
        "reference_count": row["reference_count"],
        "subject": row["subject"],
        "prompt": row["prompt"],
        "external_task_id": row["external_task_id"],
        "bundle_url": f"/files/{row['bundle_file']}" if row["bundle_file"] else "",
        "status": row["status"],
        "error": row["error"],
        "raw_url": f"/files/{row['raw_file']}" if row["raw_file"] else "",
        "files": [f"/files/{path}" for path in output_files],
    }


def _get_record_sync(job: str) -> dict | None:
    def get(conn: sqlite3.Connection) -> dict | None:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM assets WHERE job_id = ?", (job,)).fetchone()
        return _record_to_dict(row) if row else None
    return _run_db(get)


def _history_sync(limit: int) -> list[dict]:
    def history(conn: sqlite3.Connection) -> list[dict]:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_record_to_dict(row) for row in rows]
    return _run_db(history)


async def _create_record(*args: object) -> None:
    await asyncio.to_thread(_create_record_sync, *args)


async def _update_record(job: str, **fields: str) -> None:
    await asyncio.to_thread(_update_record_sync, job, **fields)


async def _get_record(job: str) -> dict | None:
    return await asyncio.to_thread(_get_record_sync, job)


async def _history(limit: int) -> list[dict]:
    return await asyncio.to_thread(_history_sync, limit)


_init_db()


def _run(args: list[str]) -> str:
    p = subprocess.run(
        [str(PY), *args], capture_output=True, text=True, cwd=str(ROOT)
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-800:])
    return p.stdout.strip()


async def _reserve_job_slot() -> bool:
    """Atomically reserve capacity for a request that will start a pipeline."""
    async with _job_submission_lock:
        if _job_slots.locked():
            return False
        await _job_slots.acquire()
        return True


def _release_job_slot() -> None:
    _job_slots.release()


def _write_download_bundle(bundle_path: Path, files: list[Path]) -> None:
    """Create a portable bundle from known generated files only."""
    with zipfile.ZipFile(
        bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        seen: set[Path] = set()
        for path in files:
            resolved = path.resolve()
            if resolved not in seen and path.is_file():
                archive.write(path, arcname=path.name)
                seen.add(resolved)


def _reference_to_data_uri(content: bytes) -> str:
    """Validate an uploaded image and encode it without blocking the event loop."""
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > MAX_REFERENCE_PIXELS:
                raise HTTPException(status_code=413, detail="单张参考图像素不能超过 3200 万")
            image_format = (image.format or "").upper()
            image.verify()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="参考图不是有效图片") from exc
    if image_format not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="参考图格式不受支持")
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{IMAGE_MIME_TYPES[image_format]};base64,{encoded}"


def _write_canonical_png(path: Path, content: bytes) -> tuple[int, int]:
    """Persist a verified generated image with a filename/MIME that always agree."""
    with Image.open(BytesIO(content)) as image:
        image.load()
        width, height = image.size
        image.convert("RGBA").save(path, format="PNG")
    return width, height


def _read_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_qc_summary(path: Path) -> dict:
    return _read_json_file(path).get("qc_summary", {})


def _collect_image_outputs(output_dir: Path) -> list[Path]:
    return sorted(path for path in output_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)


def _reset_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _write_map_bundle_metadata(
    work: Path,
    raw_path: Path,
    *,
    prompt: str,
    brief: str,
    style: str,
    requested_size: str,
    source_dimensions: tuple[int, int],
) -> list[Path]:
    """Describe the honest, reproducible baked-raster contract for map mode."""
    prompt_path = work / "map.prompt.txt"
    manifest_path = work / "map-manifest.json"
    prompt_path.write_text(prompt, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "agent-sprite-forge.map-bundle.v1",
                "kind": "map",
                "map_mode": "baked_scene_mode",
                "visual_model": "baked_raster",
                "runtime_object_model": "none",
                "collision_model": "none",
                "source": raw_path.name,
                "source_dimensions": list(source_dimensions),
                "requested_size": requested_size,
                "brief": brief,
                "style": style,
                "prompt_file": prompt_path.name,
                "delivery_contract": (
                    "A fixed raster scene only. It does not provide editable tiles, "
                    "separate props, collision, zones, or engine-native map data."
                ),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return [raw_path, prompt_path, manifest_path]


async def _save_references(job: str, references: list[UploadFile]) -> list[str]:
    if len(references) > MAX_REFERENCE_FILES:
        raise HTTPException(status_code=400, detail=f"最多上传 {MAX_REFERENCE_FILES} 张参考图")

    refs: list[str] = []
    total_bytes = 0
    for index, upload in enumerate(references):
        if not upload.filename:
            continue
        content = await upload.read(MAX_REFERENCE_BYTES + 1)
        total_bytes += len(content)
        if not content or len(content) > MAX_REFERENCE_BYTES or total_bytes > MAX_REFERENCE_BYTES:
            raise HTTPException(status_code=413, detail="参考图总大小不能超过 40 MB")
        refs.append(await asyncio.to_thread(_reference_to_data_uri, content))
    return refs


async def _retire_job(job: str, delay: float = 300) -> None:
    await asyncio.sleep(delay)
    _jobs.pop(job, None)


def _log_background_task_result(task: asyncio.Task[object]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception:  # noqa: BLE001 - DB update failure must not become unobserved.
        LOGGER.exception("background task failed")


def _schedule_record_update(job: str, **fields: str) -> None:
    task = asyncio.create_task(_update_record(job, **fields))
    task.add_done_callback(_log_background_task_result)


def _effective_sprite_size(size: str, frame: dict[str, int | str]) -> str:
    """Choose the smallest supported source canvas with readable grid cells."""
    requested_width, requested_height = SIZE_DIMENSIONS[size]
    required_width = max(requested_width, int(frame["cols"]) * MIN_SOURCE_CELL_SIZE)
    required_height = max(requested_height, int(frame["rows"]) * MIN_SOURCE_CELL_SIZE)
    requested_aspect = requested_width / requested_height
    candidates = [
        (abs((width / height) - requested_aspect), width * height, candidate)
        for candidate, (width, height) in SIZE_DIMENSIONS.items()
        if width >= required_width and height >= required_height
    ]
    if not candidates:
        raise ValueError("所选帧数需要更大的画幅，但当前没有可用画幅")
    return min(candidates)[2]


def _validate_sprite_request(
    target: str,
    mode: str,
    role: str,
    frame_count: int,
) -> dict[str, int | str]:
    if target not in TARGET_MODES:
        raise ValueError("素材对象类别不受支持")
    if mode not in TARGET_MODES[target]:
        raise ValueError("该对象类别不支持所选动作模式")
    if target == "npc" and role not in NPC_ROLES:
        raise ValueError("请选择 NPC 类型")
    if target != "npc" and role:
        raise ValueError("NPC 类型仅适用于 NPC 对象类别")

    preset = frame_preset(frame_count)
    fixed_count = FIXED_FRAME_COUNTS.get(mode)
    if fixed_count is not None and frame_count != fixed_count:
        raise ValueError(f"{mode} 模式固定为 {fixed_count} 帧，不能修改")
    if fixed_count is None and frame_count == 1:
        raise ValueError("动画模式至少需要 4 帧")
    return preset


def _sprite_processing_args(target: str, mode: str, frame_count: int) -> list[str]:
    """Keep detached effects centered while grounded assets retain a feet anchor."""
    quality_args = ["--shared-scale", "--strict-qc"]
    # High-frame humanoid sheets are expected to preserve anatomy and a common
    # feet line. Effects and creatures can legitimately change silhouette more.
    if target in {"player", "npc"} and frame_count >= 6:
        quality_args.extend([
            "--max-body-scale-cv", "0.08",
            "--max-anchor-y-std", "0.05",
        ])
    if frame_count >= 24:
        quality_args.extend(["--cell-size", "192"])
    if target == "asset" and mode in {"projectile", "impact", "explode", "fx"}:
        return ["--align", "center", *quality_args]
    return ["--align", "feet", *quality_args]


def _apply_art_direction(prompt: str, style_hint: str) -> str:
    """Make the validated style the final instruction after any LLM rewrite."""
    directive = (
        f"ART DIRECTION (highest visual priority): {style_hint}. "
        "Apply this direction consistently to every frame and replace any generic default art-style wording above. Do not mix visual styles."
    )
    if directive in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{directive}"


def _apply_asset_contract(prompt: str, kind: str, style_hint: str) -> str:
    """Reapply delivery semantics after any model-authored rewrite."""
    prompt = _apply_art_direction(prompt, style_hint)
    if kind == "map":
        directive = (
            "MAP DELIVERY CONTRACT (highest semantic priority): environment only. "
            "Do not include people, NPCs, playable characters, creatures, monsters, "
            "portraits, character sprites, character equipment, or character shadows. "
            "Render one complete opaque baked scene with no transparent background, "
            "separate asset icons, UI, labels, or text."
        )
    elif kind == "sprite":
        directive = (
            "SPRITE DELIVERY CONTRACT (highest semantic priority): isolated game asset "
            "on a transparent background with no environment, scenery, UI, labels, or text."
        )
    else:
        raise ValueError(f"unsupported asset kind: {kind}")
    if directive in prompt:
        return prompt
    return f"{prompt.rstrip()}\n\n{directive}"


async def _pipeline(
    job: str,
    kind: str,
    target: str,
    mode: str,
    brief: str,
    style_label: str,
    style_hint: str,
    size: str,
    requested_size: str,
    refs: list[str],
    role: str,
    frame: dict[str, int | str],
) -> None:
    q = _jobs[job]

    def log(msg: str) -> None:
        LOGGER.info("job=%s %s", job, msg)
        q.put_nowait({"type": "log", "text": msg})

    try:
        work = OUT / job
        await asyncio.to_thread(work.mkdir, parents=True, exist_ok=True)

        description_type = "环境" if kind == "map" else "主体"
        log(f"阶段 1/5：正在用 Gemini 3.7 润色{description_type}描述…")
        subject = await imagegen.refine_prompt(
            brief, style_hint, on_log=log, asset_kind=kind
        )
        await _update_record(job, subject=subject, status="planning")
        log(f"阶段 1/5 完成：主体描述 = {subject}")

        if kind == "sprite":
            log("阶段 2/5：套用 Sprite skill 提示词模板…")
            meta_path = work / "prompt.json"
            await asyncio.to_thread(
                _run,
                [
                    str(SPRITE), "build-prompt", "--target", target,
                    "--mode", mode, "--prompt", subject,
                    *( ["--role", role] if role else [] ),
                    *(
                        ["--rows", str(frame["rows"]), "--cols", str(frame["cols"])]
                        if requires_custom_grid(mode, int(frame["count"]))
                        else []
                    ),
                    "--write-json", str(meta_path),
                ],
            )
            prompt = (await asyncio.to_thread(_read_json_file, meta_path))["generated_prompt"]
        else:
            prompt = (
                f"top-down 2D game scene, {subject}. "
                "Deliver one complete, non-editable baked raster environment with "
                "consistent lighting and palette. This is a single scene, not a tileset: "
                "do not draw tile boundaries, separate prop icons, UI, labels, or text."
            )
        prompt = _apply_asset_contract(prompt, kind, style_hint)
        log(f"阶段 2/5 完成：提示词长度 {len(prompt)} 字符")

        log("阶段 3/5：请 Gemini 3.7 审核最终提示词…")
        review = await imagegen.review_prompt(
            prompt, brief, style_hint, on_log=log, asset_kind=kind
        )
        if review.decision == "revise" and review.prompt != prompt:
            log("审核要求改写，使用安全版提示词重新提交")
            prompt = _apply_asset_contract(review.prompt, kind, style_hint)
        else:
            log("审核通过，保留当前提示词")
        await _update_record(job, prompt=prompt, status="generating")
        q.put_nowait({"type": "prompt", "text": prompt})

        async def generate_candidate() -> bytes:
            nonlocal prompt
            for attempt in range(1, MAX_IMAGE_ATTEMPTS + 1):
                log(
                    f"阶段 4/5：调用 {imagegen.IMAGE_MODEL} 生成原图"
                    f"（第 {attempt}/{MAX_IMAGE_ATTEMPTS} 次尝试）…"
                )
                try:
                    return await imagegen.generate(
                        prompt,
                        size=size,
                        references=refs,
                        on_log=log,
                        on_task_created=lambda task_id: _schedule_record_update(
                            job, external_task_id=str(task_id)
                        ),
                    )
                except imagegen.ImageGenError as exc:
                    can_retry = (
                        attempt < MAX_IMAGE_ATTEMPTS
                        and imagegen.is_retryable_generation_error(exc)
                    )
                    if not can_retry:
                        log(f"上游出图第 {attempt} 次失败，不再重试：{exc}")
                        raise
                    log(f"上游出图第 {attempt} 次失败：{exc}")
                    log("正在请 Gemini 3.7 根据失败原因重新生成安全提示词…")
                    recovery = await imagegen.recover_prompt(
                        prompt, brief, style_hint, str(exc), on_log=log,
                        asset_kind=kind,
                    )
                    if recovery.decision == "stop":
                        log(f"Gemini 判定不应重试：{recovery.note or '错误不可由提示词修复'}")
                        raise
                    if recovery.prompt != prompt:
                        prompt = _apply_asset_contract(recovery.prompt, kind, style_hint)
                        await _update_record(job, prompt=prompt)
                        q.put_nowait({"type": "prompt", "text": prompt})
                        log(f"重试提示词已更新：长度 {len(prompt)} 字符")
                    else:
                        log("重试提示词未变化，按原提示词进行一次上游重试")
            raise RuntimeError("图像生成未返回结果")

        raw_path: Path | None = None
        raw_dimensions: tuple[int, int] | None = None
        output_dir = work / "out"
        for qc_attempt in range(1, MAX_QC_ATTEMPTS + 1):
            raw = await generate_candidate()
            raw_path = work / ("raw.png" if kind == "map" else f"raw-qc-{qc_attempt}.png")
            raw_dimensions = await asyncio.to_thread(_write_canonical_png, raw_path, raw)
            raw_file = f"{job}/{raw_path.name}"
            await _update_record(job, raw_file=raw_file)
            q.put_nowait({"type": "raw", "url": f"/files/{raw_file}"})

            if kind != "sprite":
                break

            log(
                "阶段 5/5：切帧、对齐锚点、导出…"
                f"（QC 尝试 {qc_attempt}/{MAX_QC_ATTEMPTS}）"
            )
            await _update_record(job, status="processing")
            await asyncio.to_thread(_reset_output_dir, output_dir)
            process_args = [
                str(SPRITE), "process", "--input", str(raw_path),
                "--target", target, "--mode", mode,
                "--output-dir", str(output_dir),
                "--prompt", prompt,
                *_sprite_processing_args(target, mode, int(frame["count"])),
            ]
            if requires_custom_grid(mode, int(frame["count"])):
                process_args.extend([
                    "--rows", str(frame["rows"]),
                    "--cols", str(frame["cols"]),
                    "--label-prefix", mode,
                ])
            try:
                await asyncio.to_thread(_run, process_args)
                break
            except RuntimeError as exc:
                qc_failure = "QC failed:" in str(exc)
                if not qc_failure or qc_attempt >= MAX_QC_ATTEMPTS:
                    raise
                log(f"QC 未通过：{exc}")
                log("正在根据 QC 失败原因调整提示词并重新生成…")
                recovery = await imagegen.recover_prompt(
                    prompt, brief, style_hint, str(exc), on_log=log
                )
                if recovery.decision == "stop":
                    log(f"Gemini 判定不应重试：{recovery.note or 'QC 问题无法由提示词修复'}")
                    raise
                prompt = _apply_asset_contract(recovery.prompt, kind, style_hint)
                await _update_record(job, prompt=prompt, status="generating")
                q.put_nowait({"type": "prompt", "text": prompt})
                log(f"QC 重试提示词已更新：长度 {len(prompt)} 字符")

        if kind == "sprite":
            if raw_path is None:
                raise RuntimeError("精灵生成未产出原图")
            qc_path = output_dir / "pipeline-meta.json"
            try:
                qc_summary = await asyncio.to_thread(_read_qc_summary, qc_path)
                log(
                    "QC 通过："
                    f"有效帧 {qc_summary.get('valid_frame_count', 0)}/"
                    f"{qc_summary.get('frame_count', 0)}，"
                    f"缩放变异 {float(qc_summary.get('body_scale_cv', 0.0)):.3f}，"
                    f"锚点偏移 {float(qc_summary.get('anchor_y_std', 0.0)):.3f}"
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                LOGGER.warning("job=%s could not read QC metadata: %s", job, exc)
            output_paths = await asyncio.to_thread(_collect_image_outputs, output_dir)
            bundle_path = output_dir / "sprite-forge-assets.zip"
            reproducibility_paths = [
                raw_path,
                output_dir / "pipeline-meta.json",
                output_dir / "prompt-used.txt",
                output_dir / "raw-sheet.png",
                output_dir / "raw-sheet-clean.png",
            ]
            await asyncio.to_thread(
                _write_download_bundle, bundle_path, [*output_paths, *reproducibility_paths]
            )
            files = [p.name for p in output_paths]
            bundle_file = f"{job}/out/{bundle_path.name}"
            q.put_nowait({
                "type": "done",
                "kind": kind,
                "files": [f"/files/{job}/out/{n}" for n in files],
                "bundle": f"/files/{bundle_file}",
            })
            await _update_record(
                job,
                status="completed",
                output_files=json.dumps([f"{job}/out/{n}" for n in files]),
                bundle_file=bundle_file,
            )
        else:
            if raw_path is None:
                raise RuntimeError("地图生成未产出原图")
            bundle_path = work / "sprite-forge-assets.zip"
            map_files = await asyncio.to_thread(
                _write_map_bundle_metadata,
                work,
                raw_path,
                prompt=prompt,
                brief=brief,
                style=style_label,
                requested_size=requested_size,
                source_dimensions=raw_dimensions or (0, 0),
            )
            await asyncio.to_thread(_write_download_bundle, bundle_path, map_files)
            bundle_file = f"{job}/{bundle_path.name}"
            q.put_nowait({
                "type": "done",
                "kind": kind,
                "files": [f"/files/{job}/raw.png"],
                "bundle": f"/files/{bundle_file}",
            })
            await _update_record(
                job,
                status="completed",
                output_files=json.dumps([f"{job}/raw.png"]),
                bundle_file=bundle_file,
            )
        log("全部阶段完成：素材已保存")
    except Exception as e:  # noqa: BLE001 - 演示服务需把错误回传前端
        log(f"流程终止：{type(e).__name__}: {e}")
        try:
            await _update_record(job, status="failed", error=str(e))
        except Exception:  # noqa: BLE001 - the client must still receive a terminal event.
            LOGGER.exception("job=%s could not persist failure state", job)
        q.put_nowait({"type": "error", "text": str(e)})
    finally:
        _active_jobs.discard(job)
        _release_job_slot()
        q.put_nowait(None)
        asyncio.create_task(_retire_job(job))


@app.post("/api/generate")
async def api_generate(
    kind: str = Form("sprite"),
    target: str | None = Form(None),
    mode: str | None = Form(None),
    brief: str = Form(...),
    style: str = Form(DEFAULT_STYLE_ID),
    style_note: str = Form(""),
    size: str = Form("1024x1024"),
    frame_count: int | None = Form(None),
    role: str | None = Form(None),
    references: list[UploadFile] = File(default=[]),
):
    kind = kind.strip().lower()
    target = (target or "").strip().lower()
    mode = (mode or "").strip().lower()
    role = (role or "").strip().lower()
    brief = brief.strip()
    style_note = style_note.strip()
    if kind not in {"sprite", "map"}:
        raise HTTPException(status_code=400, detail="素材类型不受支持")
    if not brief:
        raise HTTPException(status_code=400, detail="请填写需求描述")
    if len(brief) > 800:
        raise HTTPException(status_code=400, detail="需求描述不能超过 800 个字符")
    if len(style_note) > 300:
        raise HTTPException(status_code=400, detail="画风补充不能超过 300 个字符")
    if size not in SIZE_OPTIONS:
        raise HTTPException(status_code=400, detail="画幅不受支持")
    try:
        style_label, style_hint = resolve_style(style, style_note)
        if kind == "sprite":
            if not target or not mode or frame_count is None:
                raise ValueError("角色素材必须选择对象类别、动作模式和动画帧数")
            frame = _validate_sprite_request(target, mode, role, frame_count)
            effective_size = _effective_sprite_size(size, frame)
        else:
            if target or mode or role or frame_count is not None:
                raise ValueError("场景请求不能包含对象类别、动作模式、NPC 类型或动画帧数")
            target, mode, role = "map", "map", ""
            frame = frame_preset(1)
            effective_size = size
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not await _reserve_job_slot():
        raise HTTPException(
            status_code=429,
            detail="当前生成任务较多，请等待现有任务完成后再提交",
        )
    job = f"{int(time.time())}-{uuid.uuid4().hex[:6]}"
    try:
        refs = await _save_references(job, references)
        await _create_record(
            job, kind, target, mode, brief, style_label, effective_size,
            int(frame["count"]), f"{frame['rows']}x{frame['cols']}", len(refs),
        )
        _jobs[job] = asyncio.Queue()
        _active_jobs.add(job)
        asyncio.create_task(
            _pipeline(
                job, kind, target, mode, brief, style_label, style_hint,
                effective_size, size, refs, role, frame,
            )
        )
    except BaseException:
        _active_jobs.discard(job)
        _jobs.pop(job, None)
        _release_job_slot()
        raise
    return {"job": job, "requested_size": size, "size": effective_size}


@app.get("/api/stream/{job}")
async def api_stream(job: str):
    q = _jobs.get(job)
    if q is None:
        raise HTTPException(status_code=404, detail="任务不存在或实时事件已过期")

    async def gen():
        while True:
            item = await q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/jobs/{job}")
async def api_job(job: str):
    record = await _get_record(job)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return record


@app.get("/api/modes")
async def api_modes():
    return TARGET_MODES


@app.get("/api/options")
async def api_options():
    return public_options()


@app.get("/api/history")
async def api_history(limit: int = 24):
    return {"items": await _history(max(1, min(limit, 100)))}


app.mount("/files", StaticFiles(directory=str(OUT)), name="files")


@app.get("/")
async def index():
    return FileResponse(Path(__file__).resolve().parent / "static" / "index.html")


app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
    name="static",
)
