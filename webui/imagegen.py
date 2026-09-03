"""tt-image-2 图像生成客户端。

替代原项目依赖的宿主 agent 内置 image_gen，其余环节（提示词构建、
切帧、对齐、导出）仍由 skills/ 下的原生脚本完成。
"""
from __future__ import annotations

import asyncio
import base64
import ipaddress
from io import BytesIO
import json
import logging
import mimetypes
import os
import re
import socket
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent.parent
LOGGER = logging.getLogger("sprite_forge.imagegen")


def _load_env() -> None:
    """极简 .env 解析，避免额外依赖。"""
    env_files = (ROOT / ".env", ROOT.parent / "gemini3.7.env", ROOT.parent / ".gptEnv")
    for env_file in env_files:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("[") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            
            # 处理 .gptEnv 格式的映射
            if k == "base_url":
                os.environ.setdefault("LK_BASE_URL", v)
            elif k == "key":
                os.environ.setdefault("LK_API_KEY", v)
            elif k == "model":
                os.environ.setdefault("IMAGE_MODEL", v)
            elif k == "API_KEY":
                os.environ.setdefault("LK_API_KEY", v)
            else:
                os.environ.setdefault(k, v)


_load_env()

BASE_URL = os.getenv("LK_BASE_URL", "https://api.lk888.ai").rstrip("/")
API_KEY = os.getenv("LK_API_KEY", "")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "tt-image-2")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gem-3.7-flash")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "4"))
POLL_TIMEOUT = float(os.getenv("POLL_TIMEOUT", "600"))
PROGRESS_STALL_TIMEOUT = float(os.getenv("IMAGE_PROGRESS_STALL_TIMEOUT", "240"))
REQUEST_TIMEOUT = float(os.getenv("IMAGE_REQUEST_TIMEOUT", "45"))
CONNECT_TIMEOUT = float(os.getenv("IMAGE_CONNECT_TIMEOUT", "15"))
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "120"))
MAX_RESULT_BYTES = int(os.getenv("IMAGE_RESULT_MAX_BYTES", str(30 * 1024 * 1024)))
MAX_RESULT_PIXELS = int(os.getenv("IMAGE_RESULT_MAX_PIXELS", "64000000"))
MAX_INLINE_RESULT_CHARS = ((MAX_RESULT_BYTES + 2) // 3) * 4
MAX_CREATE_RESPONSE_BYTES = int(
    os.getenv("IMAGE_CREATE_RESPONSE_MAX_BYTES", str(MAX_INLINE_RESULT_CHARS + 1024 * 1024))
)
MAX_STATUS_RESPONSE_BYTES = int(os.getenv("IMAGE_STATUS_RESPONSE_MAX_BYTES", str(1024 * 1024)))
MAX_RESULT_REDIRECTS = int(os.getenv("IMAGE_RESULT_MAX_REDIRECTS", "3"))
ALLOW_HTTP_RESULT_URL = os.getenv("IMAGE_RESULT_ALLOW_HTTP", "").strip().lower() in {"1", "true", "yes"}
RESULT_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}
RESULT_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"}

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


class ImageGenError(RuntimeError):
    pass


@dataclass
class PromptReview:
    decision: str
    risk: str
    prompt: str
    checks: list[dict]
    note: str = ""


def is_retryable_generation_error(error: Exception) -> bool:
    """Avoid retrying failures that a rewritten prompt cannot repair."""
    message = str(error).lower()
    permanent_markers = (
        "未配置",
        "401",
        "403",
        "unauthorized",
        "forbidden",
        "invalid api key",
        "权限",
    )
    return not any(marker in message for marker in permanent_markers)


def _local_safety_rewrite(text: str) -> str:
    """Keep common graphic trigger phrases out of the image request fallback."""
    replacements = (
        ("decaying zombie", "stylized fantasy undead guardian"),
        ("rotting zombie", "stylized fantasy undead guardian"),
        ("zombie", "stylized fantasy undead creature"),
        ("decaying", "weathered"),
        ("rotting", "weathered"),
        ("tattered ragged", "worn"),
        ("tattered", "worn"),
        ("ragged", "worn"),
        ("bloody", "red-accented"),
        ("blood", "red paint accent"),
        ("gore", "dramatic fantasy detail"),
        ("mutilated", "battle-worn"),
        ("exposed wound", "weathered marking"),
    )
    safe = text
    for source, replacement in replacements:
        safe = safe.replace(source, replacement).replace(source.title(), replacement)
    safe = safe.replace("stylized fantasy stylized fantasy", "stylized fantasy")
    return re.sub(
        r"\bstylized\s+undead\s+fantasy\s+stylized\s+fantasy\s+undead\s+creature\b",
        "stylized fantasy undead creature",
        safe,
        flags=re.IGNORECASE,
    )


def to_data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


async def generate(
    prompt: str,
    size: str,
    references: list[str] | None = None,
    quality: str = "auto",
    on_log=None,
    on_task_created=None,
) -> bytes:
    """创建异步任务、轮询直到终态、返回图片字节。"""
    if not API_KEY:
        raise ImageGenError("未配置 LK_API_KEY")

    def log(msg: str) -> None:
        if on_log:
            on_log(msg)

    started_at = time.monotonic()
    log(f"图像请求准备：model={IMAGE_MODEL} size={size} refs={len(references or [])}")

    params: dict = {"size": size, "quality": quality, "n": 1}
    if references:
        params["images"] = references[:14]
    body = {"model": IMAGE_MODEL, "prompt": prompt, "params": params}

    timeout = httpx.Timeout(
        connect=CONNECT_TIMEOUT,
        read=REQUEST_TIMEOUT,
        write=REQUEST_TIMEOUT,
        pool=CONNECT_TIMEOUT,
    )
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as http:
        try:
            async with http.stream(
                "POST",
                f"{BASE_URL}/v1/media/generate",
                headers=HEADERS,
                json=body,
                follow_redirects=True,
            ) as response:
                status_code = response.status_code
                response_body = await _read_limited_response(
                    response, MAX_CREATE_RESPONSE_BYTES, "创建任务响应"
                )
        except httpx.HTTPError as exc:
            LOGGER.warning("image generation request failed: %s", exc)
            raise ImageGenError(f"图像服务连接失败：{_short_error(exc)}") from exc
        LOGGER.info("image generation request returned HTTP %s", status_code)
        log(f"图像接口响应 HTTP {status_code}（耗时 {time.monotonic() - started_at:.1f}s）")
        if status_code >= 400:
            raise ImageGenError(f"创建任务失败 {status_code}: {_response_text(response_body)[:300]}")
        try:
            data = json.loads(response_body)
        except ValueError as exc:
            raise ImageGenError(f"创建任务返回了无效 JSON: {_response_text(response_body)[:200]}") from exc
        _raise_api_error(data, "创建任务")

        task_id = _extract_task_id(data)
        if task_id is None:
            # 少数情况直接同步返回图片
            inline = _extract_inline(data)
            if inline:
                log("已同步返回图片")
                return await _fetch_bytes(http, inline)
            raise ImageGenError(f"未取到 task_id: {str(data)[:300]}")
        if on_task_created:
            on_task_created(task_id)
        LOGGER.info("image generation task created: %s", task_id)
        log(f"任务已创建 task_id={task_id}，开始轮询（间隔 {POLL_INTERVAL:g}s，最长 {POLL_TIMEOUT:g}s）")

        deadline = time.monotonic() + POLL_TIMEOUT
        last_progress = None
        progress_changed_at = time.monotonic()
        poll_count = 0
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            poll_count += 1
            try:
                async with http.stream(
                    "GET",
                    f"{BASE_URL}/v1/media/status",
                    headers=HEADERS,
                    params={"task_id": task_id},
                    follow_redirects=True,
                ) as response:
                    status_code = response.status_code
                    response_body = await _read_limited_response(
                        response, MAX_STATUS_RESPONSE_BYTES, "查询任务响应"
                    )
            except httpx.HTTPError as exc:
                LOGGER.warning("status request failed for task %s: %s", task_id, exc)
                raise ImageGenError(f"查询图像任务连接失败：{_short_error(exc)}") from exc
            if status_code >= 400:
                raise ImageGenError(f"查询失败 {status_code}: {_response_text(response_body)[:200]}")
            try:
                st = json.loads(response_body)
            except ValueError as exc:
                raise ImageGenError(f"查询任务返回了无效 JSON: {_response_text(response_body)[:200]}") from exc
            _raise_api_error(st, "查询任务")
            if isinstance(st.get("data"), dict) and "is_final" not in st:
                st = st["data"]
            LOGGER.info(
                "image generation task %s status=%s final=%s",
                task_id,
                st.get("state"),
                st.get("is_final"),
            )
            # state 是唯一可靠判据，status 为中文展示字段
            if st.get("is_final") is True:
                if st.get("state") != "success":
                    detail = st.get("error") or st.get("state") or "未知原因"
                    log(f"上游任务终态：state={st.get('state')} error={detail}")
                    if any(word in str(detail).lower() for word in ("violence", "safety", "暴力", "防护", "血腥", "安全")):
                        raise ImageGenError(f"上游内容安全拦截：{detail}")
                    raise ImageGenError(f"生成失败：{detail}")
                url = st.get("result_url")
                if not url:
                    raise ImageGenError("任务成功但缺少 result_url")
                log(f"上游任务成功：progress={st.get('progress', '100')} cost={st.get('cost', 0)}，下载结果…")
                result = await _fetch_bytes(http, url)
                log(f"原图下载完成：{len(result):,} bytes，总耗时 {time.monotonic() - started_at:.1f}s")
                return result
            progress = str(st.get("progress") or st.get("state") or "")
            now = time.monotonic()
            if progress != last_progress:
                last_progress = progress
                progress_changed_at = now
            log(f"轮询 #{poll_count}：state={st.get('state')} progress={progress}（已耗时 {now - started_at:.1f}s）")
            if now > deadline:
                raise ImageGenError("轮询超时")
            if now - progress_changed_at > PROGRESS_STALL_TIMEOUT:
                log("进度停滞，正在进行一次终态复查…")
                try:
                    async with http.stream(
                        "GET",
                        f"{BASE_URL}/v1/media/status",
                        headers=HEADERS,
                        params={"task_id": task_id},
                        follow_redirects=True,
                    ) as response:
                        confirm_status = response.status_code
                        confirm_body = await _read_limited_response(
                            response, MAX_STATUS_RESPONSE_BYTES, "终态复查响应"
                        )
                    if confirm_status >= 400:
                        raise ImageGenError(
                            f"终态复查失败 {confirm_status}: {_response_text(confirm_body)[:200]}"
                        )
                    confirm = json.loads(confirm_body)
                    _raise_api_error(confirm, "终态复查")
                    if isinstance(confirm.get("data"), dict) and "is_final" not in confirm:
                        confirm = confirm["data"]
                    if confirm.get("is_final") is True and confirm.get("state") != "success":
                        detail = confirm.get("error") or confirm.get("state") or "未知原因"
                        log(f"终态复查结果：state={confirm.get('state')} error={detail}")
                        if any(word in str(detail).lower() for word in ("violence", "safety", "暴力", "防护", "血腥", "安全")):
                            raise ImageGenError(f"上游内容安全拦截：{detail}")
                        raise ImageGenError(f"生成失败：{detail}")
                except ImageGenError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    log(f"终态复查失败：{_short_error(exc)}")
                raise ImageGenError(
                    f"图像服务进度已停滞 {int(PROGRESS_STALL_TIMEOUT)} 秒（{progress or '未知'}）"
                )

async def _read_limited_response(
    response: httpx.Response,
    max_bytes: int,
    label: str,
) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ImageGenError(f"{label}超过 {max_bytes // (1024 * 1024)} MB 限制")
        except ValueError as exc:
            raise ImageGenError(f"{label}的 Content-Length 无效") from exc
    chunks = bytearray()
    async for chunk in response.aiter_bytes():
        chunks.extend(chunk)
        if len(chunks) > max_bytes:
            raise ImageGenError(f"{label}超过 {max_bytes // (1024 * 1024)} MB 限制")
    return bytes(chunks)


def _response_text(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def _short_error(exc: Exception) -> str:
    text = str(exc).strip()
    return text[:240] or type(exc).__name__


def _raise_api_error(data: object, operation: str) -> None:
    """The provider can return business errors with HTTP 200."""
    if not isinstance(data, dict):
        return
    code = data.get("code")
    if isinstance(code, int) and code >= 400:
        message = data.get("msg") or data.get("message") or data.get("error") or "未知错误"
        raise ImageGenError(f"{operation}失败 {code}: {str(message)[:250]}")


def _extract_task_id(data: dict):
    """task_id 可能在顶层，也可能嵌在 data 对象里。"""
    for scope in (data, data.get("data")):
        if not isinstance(scope, dict):
            continue
        tid = scope.get("task_id") or scope.get("id")
        if tid:
            return tid
        ids = scope.get("task_ids")
        if isinstance(ids, list) and ids:
            return ids[0]
    return None


def _extract_inline(data: dict) -> str | None:
    inline_data = data.get("data")
    if isinstance(inline_data, dict):
        entries = [inline_data]
    elif isinstance(inline_data, list):
        entries = inline_data
    else:
        entries = []
    for d in entries:
        if isinstance(d, str) and d:
            return d
        if isinstance(d, dict) and d.get("url"):
            return d["url"]
        if isinstance(d, dict) and d.get("b64_json"):
            return d["b64_json"]
    return None


def _validate_result_image(content: bytes, declared_mime: str | None = None) -> bytes:
    """Reject non-image or decompression-bomb results before pipeline writes them."""
    if not content:
        raise ImageGenError("图像结果为空")
    if len(content) > MAX_RESULT_BYTES:
        raise ImageGenError(f"图像结果超过 {MAX_RESULT_BYTES // (1024 * 1024)} MB 限制")
    if declared_mime and declared_mime.lower() not in RESULT_IMAGE_MIME_TYPES:
        raise ImageGenError(f"图像结果 MIME 类型不受支持：{declared_mime}")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                image_format = (image.format or "").upper()
                if image_format not in RESULT_IMAGE_FORMATS:
                    raise ImageGenError("图像结果格式不受支持")
                if image.width * image.height > MAX_RESULT_PIXELS:
                    raise ImageGenError(f"图像结果像素超过 {MAX_RESULT_PIXELS:,} 限制")
                image.verify()
    except ImageGenError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageGenError("图像结果不是有效的受支持图片") from exc
    return content


def _decode_inline_result(encoded: str, declared_mime: str | None = None) -> bytes:
    if len(encoded) > MAX_INLINE_RESULT_CHARS:
        raise ImageGenError(f"图像内联数据超过 {MAX_RESULT_BYTES // (1024 * 1024)} MB 限制")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ImageGenError("图像内联数据不是有效 base64") from exc
    return _validate_result_image(content, declared_mime)


async def _validate_result_url(url: str) -> None:
    parsed = urlsplit(url)
    allowed_schemes = {"https"}
    if ALLOW_HTTP_RESULT_URL:
        allowed_schemes.add("http")
    if parsed.scheme.lower() not in allowed_schemes or not parsed.hostname:
        raise ImageGenError("图像结果 URL 必须使用受支持的 HTTP(S) 地址")
    if parsed.username or parsed.password:
        raise ImageGenError("图像结果 URL 不能包含用户凭据")
    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ImageGenError("图像结果 URL 端口无效") from exc
    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
        addresses = {literal_ip}
    except ValueError:
        try:
            records = await asyncio.get_running_loop().getaddrinfo(
                parsed.hostname, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise ImageGenError("图像结果 URL 无法解析") from exc
        addresses = {ipaddress.ip_address(record[4][0]) for record in records}
    if not addresses or any(not address.is_global for address in addresses):
        raise ImageGenError("图像结果 URL 必须解析为公网地址")


async def _fetch_bytes(http: httpx.AsyncClient, url: str) -> bytes:
    """Fetch a bounded, verified image from a result URL, data URI, or base64."""
    if not isinstance(url, str) or not url:
        raise ImageGenError("图像结果 URL 无效")
    if url.startswith("data:"):
        try:
            header, encoded = url.split(",", 1)
            if not header.lower().endswith(";base64"):
                raise ValueError("data URI is not base64")
            declared_mime = header[5:].split(";", 1)[0].lower()
        except (ValueError, IndexError) as exc:
            raise ImageGenError("图像 data URI 无效") from exc
        return await asyncio.to_thread(_decode_inline_result, encoded, declared_mime)

    parsed = urlsplit(url)
    if not parsed.scheme:
        return await asyncio.to_thread(_decode_inline_result, url)
    current_url = url
    for redirect_count in range(MAX_RESULT_REDIRECTS + 1):
        await _validate_result_url(current_url)
        try:
            async with http.stream(
                "GET", current_url, timeout=300, follow_redirects=False
            ) as response:
                if 300 <= response.status_code < 400:
                    location = response.headers.get("location")
                    if not location:
                        raise ImageGenError("图像结果重定向缺少目标地址")
                    if redirect_count >= MAX_RESULT_REDIRECTS:
                        raise ImageGenError("图像结果重定向次数超过限制")
                    current_url = urljoin(str(response.url), location)
                    continue
                if response.status_code >= 400:
                    raise ImageGenError(f"下载失败 {response.status_code}")
                declared_mime = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if declared_mime not in RESULT_IMAGE_MIME_TYPES:
                    raise ImageGenError(f"图像结果 MIME 类型不受支持：{declared_mime or '未提供'}")
                content = await _read_limited_response(response, MAX_RESULT_BYTES, "图像结果")
        except ImageGenError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ImageGenError(f"下载图像结果失败：{_short_error(exc)}") from exc
        return await asyncio.to_thread(_validate_result_image, content, declared_mime)
    raise ImageGenError("图像结果重定向失败")


async def _gemini_text(instruction: str, *, temperature: float = 0.2) -> str | None:
    if not API_KEY:
        return None
    body = {
        "contents": [{"role": "user", "parts": [{"text": instruction}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 1200,
        },
    }
    url = f"{BASE_URL}/v1beta/models/{GEMINI_MODEL}:generateContent"
    timeout = httpx.Timeout(GEMINI_TIMEOUT, connect=CONNECT_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(url, headers=HEADERS, json=body)
        if response.status_code >= 400:
            LOGGER.warning("Gemini request failed HTTP %s: %s", response.status_code, response.text[:240])
            return None
        data = response.json()
        _raise_api_error(data, "Gemini 请求")
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, ImageGenError) as exc:
        LOGGER.warning("Gemini request could not be parsed: %s", _short_error(exc))
        return None


def _parse_json_object(text: str | None) -> dict | None:
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.startswith("json"):
            candidate = candidate[4:].lstrip()
    try:
        data = json.loads(candidate)
    except ValueError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(candidate[start:end + 1])
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _emit_checks(checks: object, on_log) -> None:
    if not on_log or not isinstance(checks, list):
        return
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = check.get("name") or check.get("check") or "未命名检查"
        status = str(check.get("status") or check.get("result") or "unknown").upper()
        detail = check.get("detail") or check.get("reason") or ""
        on_log(f"  [checklist] {name}: {status}{f' - {detail}' if detail else ''}")


async def refine_prompt(
    brief: str,
    style_hint: str,
    on_log=None,
    *,
    asset_kind: str = "sprite",
) -> str:
    """Use Gemini to create a description under a kind-specific contract."""
    if asset_kind == "map":
        editor_scope = "场景"
        description_rule = (
            "必须只描述环境本身（地形、建筑、道路、植被、环境物件、材质、光照、配色）。"
            "不要描述或添加人物、NPC、玩家角色、生物、怪物、肖像、角色装备或动作。"
            "如果原需求提到角色，只提取地点和氛围信息，彻底省略角色。"
            "不要写画幅、透明背景、动作帧、UI、文字或 pixel art。"
        )
        checklist = "地形、建筑、材质、光照、配色；排除角色和 NPC"
    elif asset_kind == "sprite":
        editor_scope = "角色/物件素材"
        description_rule = (
            "必须只描述主体外观（种族/职业、服装、武器、配色），"
            "不要写画幅、场景背景、动作帧或 pixel art。"
        )
        checklist = "主体、职业/种族、服装、武器、配色；过滤血腥和写实伤口"
    else:
        raise ValueError(f"unsupported asset kind: {asset_kind}")
    if on_log:
        on_log(f"Gemini 3.7 {editor_scope}润色清单：{checklist}")
    instruction = (
        f"你是 2D 游戏{editor_scope}提示词编辑器。请把需求转成一句简短的英文描述。\n"
        f"{description_rule}\n"
        "安全清单：禁止血液、尸块、裸露伤口、肢解、内脏、残酷暴力、写实恐怖；"
        "如果需求涉及僵尸/怪物，改成适合全年龄游戏的 stylized fantasy creature，身体完整、无血腥细节。\n"
        "返回严格 JSON，不要 Markdown："
        '{"subject":"一句英文描述","checks":['
        '{"name":"需求主体","status":"PASS|REVISE","detail":"..."},'
        '{"name":"全年龄安全","status":"PASS|REVISE","detail":"..."},'
        '{"name":"素材描述范围","status":"PASS|REVISE","detail":"..."}]}.\n\n'
        f"需求：{brief}\n风格倾向：{style_hint or '无'}"
    )
    data = _parse_json_object(await _gemini_text(instruction, temperature=0.35))
    if data:
        _emit_checks(data.get("checks"), on_log)
        subject = _local_safety_rewrite(str(data.get("subject") or brief).strip())
    else:
        subject = _local_safety_rewrite(brief)
        if on_log:
            on_log("  [checklist] 润色响应: FALLBACK - Gemini 响应不可解析，使用本地安全规则")
    if on_log:
        on_log(f"Gemini 3.7 润色结果：{subject}")
    return subject


async def review_prompt(
    prompt: str,
    brief: str,
    style_hint: str,
    on_log=None,
    *,
    asset_kind: str = "sprite",
) -> PromptReview:
    """Review and, when needed, rewrite the final prompt before image generation."""
    if asset_kind == "map":
        scope_name = "场景"
        delivery_check = "无角色的完整不透明场景"
        delivery_rule = (
            "交付物必须是单张、不透明、完整的纯环境场景。禁止人物、NPC、玩家角色、生物、怪物、"
            "肖像、角色精灵、角色装备、透明背景、独立素材图标、UI、标签或文字。"
            "如需改写，只保留环境、地点和美术风格，不得引入任何角色元素。"
        )
    elif asset_kind == "sprite":
        scope_name = "角色/物件素材"
        delivery_check = "透明背景"
        delivery_rule = (
            "如有风险，decision 必须为 revise，并将 rewritten_prompt 改写为全年龄、完整身体、"
            "stylized fantasy/game art 的安全表达；保留主体、装备和风格，不添加场景背景或文字。"
        )
    else:
        raise ValueError(f"unsupported asset kind: {asset_kind}")
    if on_log:
        on_log(f"Gemini 3.7 {scope_name}审核清单：安全内容、语义一致性、{delivery_check}、无文字")
    instruction = (
        f"你是图像生成前的{scope_name}安全与质量审核器。审核下面的提示词，返回严格 JSON，不要 Markdown：\n"
        '{"decision":"pass|revise","risk":"low|medium|high","rewritten_prompt":"...",'
        '"checks":[{"name":"安全内容","status":"PASS|REVISE","detail":"..."},'
        '{"name":"主体一致性","status":"PASS|REVISE","detail":"..."},'
        f'{{"name":"{delivery_check}","status":"PASS|REVISE","detail":"..."}},'
        '{"name":"无文字","status":"PASS|REVISE","detail":"..."}],"note":"..."}\n'
        "规则：禁止血液、尸块、裸露伤口、肢解、内脏、残酷暴力或写实恐怖。"
        f"{delivery_rule}"
        "如果没有风险，rewritten_prompt 原样返回。\n\n"
        f"原始需求：{brief}\n风格：{style_hint or '无'}\n最终提示词：{prompt}"
    )
    data = _parse_json_object(await _gemini_text(instruction, temperature=0.1))
    if not data:
        if on_log:
            on_log("素材审核：Gemini 返回不可解析，采用本地保守规则并保留原提示词")
        safe_prompt = _local_safety_rewrite(prompt)
        return PromptReview("revise" if safe_prompt != prompt else "pass", "unknown", safe_prompt, [{"name": "审核响应", "status": "FALLBACK", "detail": "Gemini 响应不可解析，使用本地安全规则"}], "")
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    _emit_checks(checks, on_log)
    decision = str(data.get("decision") or "revise").lower()
    risk = str(data.get("risk") or "unknown").lower()
    rewritten = _local_safety_rewrite(str(data.get("rewritten_prompt") or prompt).strip())
    if decision not in {"pass", "revise"}:
        decision = "revise"
    if decision == "revise" and not rewritten:
        rewritten = prompt
    note = str(data.get("note") or "")
    if on_log:
        on_log(f"素材审核结论：{decision.upper()} risk={risk}{f' - {note}' if note else ''}")
    return PromptReview(decision, risk, rewritten, checks, note)


async def recover_prompt(
    prompt: str,
    brief: str,
    style_hint: str,
    failure: str,
    on_log=None,
    *,
    asset_kind: str = "sprite",
) -> PromptReview:
    """Ask Gemini for one safer, simpler retry prompt after an upstream failure."""
    if asset_kind == "map":
        delivery_rule = (
            "保留环境、地点和美术风格；必须保留单张完整不透明场景、纯环境、"
            "无人物/NPC/角色/生物、无 UI 和无文字。"
        )
        delivery_label = "场景保留、无角色、完整不透明背景与无文字"
    elif asset_kind == "sprite":
        delivery_rule = "保留原需求的主体、装备和美术风格；必须保留 transparent background 和 no text。"
        delivery_label = "主体保留、透明背景与无文字"
    else:
        raise ValueError(f"unsupported asset kind: {asset_kind}")
    if on_log:
        on_log(f"Gemini 3.7 重试清单：失败归因、安全内容、{delivery_label}")
    instruction = (
        "你是 2D 游戏素材图像生成的故障恢复编辑器。上游图像服务失败后，"
        "请决定一次重新提交是否合理，并为可重试情况写出一个更稳妥的英文最终提示词。"
        "返回严格 JSON，不要 Markdown："
        '{"decision":"retry|stop","risk":"low|medium|high","rewritten_prompt":"...",'
        '"checks":[{"name":"失败归因","status":"PASS|REVISE","detail":"..."},'
        '{"name":"安全内容","status":"PASS|REVISE","detail":"..."},'
        '{"name":"主体保留","status":"PASS|REVISE","detail":"..."},'
        '{"name":"交付要求","status":"PASS|REVISE","detail":"..."}],"note":"..."}.\n'
        "规则：如果错误涉及内容安全、暴力、恐怖、血腥，必须使用全年龄、完整身体、"
        "stylized fantasy/game art 的温和表达，且不要复述被拦截的敏感词。"
        f"{delivery_rule}"
        "错误明显是认证、权限或缺少 API 配置时，decision 必须为 stop；其余上游失败可 retry。\n\n"
        f"原始需求：{brief}\n风格：{style_hint or '无'}\n"
        f"本次失败：{failure}\n当前最终提示词：{prompt}"
    )
    data = _parse_json_object(await _gemini_text(instruction, temperature=0.2))
    if not data:
        fallback = _local_safety_rewrite(prompt)
        if on_log:
            on_log("  [checklist] 重试响应: FALLBACK - Gemini 响应不可解析，使用本地安全提示词")
        return PromptReview(
            "retry",
            "unknown",
            fallback,
            [{"name": "重试响应", "status": "FALLBACK", "detail": "Gemini 响应不可解析，使用本地安全规则"}],
            "Gemini 未返回有效 JSON，使用本地安全规则后重试一次",
        )

    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    _emit_checks(checks, on_log)
    decision = str(data.get("decision") or "retry").lower()
    if decision not in {"retry", "stop"}:
        decision = "retry"
    risk = str(data.get("risk") or "unknown").lower()
    rewritten = _local_safety_rewrite(str(data.get("rewritten_prompt") or prompt).strip())
    note = str(data.get("note") or "")
    if on_log:
        on_log(f"重试审核结论：{decision.upper()} risk={risk}{f' - {note}' if note else ''}")
    return PromptReview(decision, risk, rewritten, checks, note)
