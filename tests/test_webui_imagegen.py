from __future__ import annotations

import asyncio
import base64
from io import BytesIO
import unittest
from unittest.mock import patch

import httpx
from PIL import Image

from webui import imagegen
from webui.imagegen import ImageGenError, _extract_inline


def png_bytes() -> bytes:
    content = BytesIO()
    Image.new("RGBA", (4, 4), (20, 120, 220, 255)).save(content, format="PNG")
    return content.getvalue()


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        return None


class InlineImageResponseTests(unittest.TestCase):
    def test_supports_object_and_list_inline_urls(self) -> None:
        self.assertEqual(
            _extract_inline({"data": {"url": "https://example.test/image.png"}}),
            "https://example.test/image.png",
        )
        self.assertEqual(
            _extract_inline({"data": [{"url": "https://example.test/list.png"}]}),
            "https://example.test/list.png",
        )

    def test_supports_object_and_list_inline_base64(self) -> None:
        self.assertEqual(_extract_inline({"data": {"b64_json": "YWJj"}}), "YWJj")
        self.assertEqual(_extract_inline({"data": [{"b64_json": "ZGVm"}]}), "ZGVm")

    def test_rejects_unknown_inline_shapes(self) -> None:
        self.assertIsNone(_extract_inline({"data": {"unexpected": "value"}}))
        self.assertIsNone(_extract_inline({"data": "not-a-list"}))


class KindSpecificPromptTests(unittest.TestCase):
    def test_map_refinement_uses_an_environment_only_contract(self) -> None:
        instructions: list[str] = []

        async def gemini(instruction: str, **_kwargs: object) -> str:
            instructions.append(instruction)
            return '{"subject":"an empty forest shrine","checks":[]}'

        with patch.object(imagegen, "_gemini_text", side_effect=gemini):
            subject = asyncio.run(
                imagegen.refine_prompt(
                    "a healer NPC outside a shrine",
                    "watercolor",
                    asset_kind="map",
                )
            )

        self.assertEqual(subject, "an empty forest shrine")
        self.assertIn("只描述环境本身", instructions[0])
        self.assertIn("不要描述或添加人物、NPC", instructions[0])

    def test_map_review_forbids_transparent_or_character_content(self) -> None:
        instructions: list[str] = []

        async def gemini(instruction: str, **_kwargs: object) -> str:
            instructions.append(instruction)
            return '{"decision":"pass","risk":"low","rewritten_prompt":"scene","checks":[]}'

        with patch.object(imagegen, "_gemini_text", side_effect=gemini):
            asyncio.run(
                imagegen.review_prompt(
                    "scene",
                    "village",
                    "watercolor",
                    asset_kind="map",
                )
            )

        self.assertIn("单张、不透明、完整的纯环境场景", instructions[0])
        self.assertIn("禁止人物、NPC、玩家角色", instructions[0])
        self.assertIn("透明背景", instructions[0])


class ResultDownloadValidationTests(unittest.TestCase):
    def run_fetch(self, response: httpx.Response) -> bytes:
        async def fetch() -> bytes:
            transport = httpx.MockTransport(lambda _request: response)
            async with httpx.AsyncClient(transport=transport) as client:
                with patch.object(imagegen, "_validate_result_url", return_value=None):
                    return await imagegen._fetch_bytes(client, "https://cdn.example.test/image.png")
        return asyncio.run(fetch())

    def test_accepts_a_verified_image_response(self) -> None:
        result = self.run_fetch(httpx.Response(200, headers={"content-type": "image/png"}, content=png_bytes()))

        self.assertEqual(result, png_bytes())

    def test_rejects_non_image_mime_and_invalid_image_body(self) -> None:
        with self.assertRaisesRegex(ImageGenError, "MIME"):
            self.run_fetch(httpx.Response(200, headers={"content-type": "text/html"}, content=b"nope"))
        with self.assertRaisesRegex(ImageGenError, "有效"):
            self.run_fetch(httpx.Response(200, headers={"content-type": "image/png"}, content=b"not a png"))

    def test_rejects_oversized_declared_and_chunked_responses(self) -> None:
        with patch.object(imagegen, "MAX_RESULT_BYTES", 8):
            with self.assertRaisesRegex(ImageGenError, "超过"):
                self.run_fetch(
                    httpx.Response(
                        200,
                        headers={"content-type": "image/png", "content-length": "99"},
                        content=b"x",
                    )
                )
            with self.assertRaisesRegex(ImageGenError, "超过"):
                self.run_fetch(
                    httpx.Response(
                        200,
                        headers={"content-type": "image/png"},
                        stream=ChunkedStream([b"1234", b"56789"]),
                    )
                )

    def test_validates_data_uri_and_bare_base64_before_decode(self) -> None:
        encoded = base64.b64encode(png_bytes()).decode("ascii")

        self.assertEqual(asyncio.run(imagegen._fetch_bytes(None, f"data:image/png;base64,{encoded}")), png_bytes())
        self.assertEqual(asyncio.run(imagegen._fetch_bytes(None, encoded)), png_bytes())
        with self.assertRaisesRegex(ImageGenError, "base64"):
            asyncio.run(imagegen._fetch_bytes(None, "data:image/png;base64,not base64!?"))
        with patch.object(imagegen, "MAX_INLINE_RESULT_CHARS", 5):
            with self.assertRaisesRegex(ImageGenError, "超过"):
                asyncio.run(imagegen._fetch_bytes(None, encoded))

    def test_rejects_local_or_unencrypted_result_urls(self) -> None:
        with self.assertRaisesRegex(ImageGenError, "公网"):
            asyncio.run(imagegen._validate_result_url("https://127.0.0.1/image.png"))
        with self.assertRaisesRegex(ImageGenError, "受支持"):
            asyncio.run(imagegen._validate_result_url("http://example.com/image.png"))
