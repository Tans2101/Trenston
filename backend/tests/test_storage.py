"""Image compression on the R2 upload path."""
import io
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import storage  # noqa: E402


def _jpeg_bytes(size, *, quality=95):
    w, h = size
    img = Image.frombytes("RGB", size, os.urandom(w * h * 3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _png_bytes(size, *, transparent=True):
    w, h = size
    if transparent:
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle(
            [w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=(201, 169, 98, 255),
        )
    else:
        img = Image.new("RGB", size, (9, 9, 11))
        ImageDraw.Draw(img).rectangle(
            [w // 4, h // 4, 3 * w // 4, 3 * h // 4], fill=(201, 169, 98),
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_pdf_bytes_are_unchanged():
    pdf = b"%PDF-1.4 minimal test content"
    assert storage.maybe_compress_image(pdf, "application/pdf", "invoice.pdf") is pdf
    assert storage.maybe_compress_image(pdf, "application/pdf", "invoice.pdf") == pdf


def test_non_image_content_type_skipped():
    data = b"not-an-image"
    assert storage.maybe_compress_image(data, "text/plain", "notes.txt") is data


def test_large_jpeg_is_resized_and_smaller(caplog):
    original = _jpeg_bytes((4000, 3000), quality=95)
    assert len(original) > 5 * 1024 * 1024
    with caplog.at_level(logging.INFO, logger="helm"):
        compressed = storage.maybe_compress_image(original, "image/jpeg", "photo.jpg")
    assert compressed != original
    assert len(compressed) < len(original)
    with Image.open(io.BytesIO(compressed)) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= storage.MAX_IMAGE_EDGE
        assert img.size[0] == 2000
        assert img.size[1] == 1500
    assert "image compressed photo.jpg" in caplog.text
    assert str(len(original)) in caplog.text
    assert str(len(compressed)) in caplog.text


def test_png_keeps_transparency_and_format():
    original = _png_bytes((800, 600), transparent=True)
    compressed = storage.maybe_compress_image(original, "image/png", "logo.png")
    with Image.open(io.BytesIO(compressed)) as img:
        assert img.format == "PNG"
        img = img.convert("RGBA")
        assert img.getpixel((0, 0))[3] == 0
        assert img.getpixel((400, 300))[3] == 255
        gold = img.getpixel((400, 300))[:3]
        assert gold[0] > gold[2]  # still warm/gold, not washed out


def test_oversized_png_is_resized_without_becoming_jpeg():
    original = _png_bytes((2400, 1800), transparent=True)
    compressed = storage.maybe_compress_image(original, "image/png", "wide-logo.png")
    with Image.open(io.BytesIO(compressed)) as img:
        assert img.format == "PNG"
        assert max(img.size) <= storage.MAX_IMAGE_EDGE
        img = img.convert("RGBA")
        assert img.getpixel((0, 0))[3] == 0


def test_unreadable_image_is_stored_as_is(caplog):
    junk = b"\xff\xd8\xff this is not a jpeg"
    with caplog.at_level(logging.WARNING, logger="helm"):
        out = storage.maybe_compress_image(junk, "image/jpeg", "broken.jpg")
    assert out == junk
    assert "unreadable" in caplog.text


def test_upload_document_sends_compressed_jpeg_to_r2():
    original = _jpeg_bytes((3200, 2400), quality=95)
    captured = {}

    fake = MagicMock()
    fake.put_object.side_effect = lambda **kwargs: captured.update(kwargs)

    with patch.object(storage, "r2_configured", return_value=True), patch.object(
        storage, "_client", return_value=fake
    ):
        key = storage.upload_document("ws_test", original, "receipt.jpg", "image/jpeg")

    assert key.startswith("ws_test/")
    assert key.endswith("receipt.jpg")
    body = captured["Body"]
    assert len(body) < len(original)
    with Image.open(io.BytesIO(body)) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= storage.MAX_IMAGE_EDGE
    fake.put_object.assert_called_once()


def test_upload_document_does_not_touch_pdf_bytes():
    pdf = b"%PDF-1.4 unchanged"
    captured = {}
    fake = MagicMock()
    fake.put_object.side_effect = lambda **kwargs: captured.update(kwargs)

    with patch.object(storage, "r2_configured", return_value=True), patch.object(
        storage, "_client", return_value=fake
    ):
        storage.upload_document("ws_test", pdf, "invoice.pdf", "application/pdf")

    assert captured["Body"] == pdf
    assert captured["Body"] is pdf
    assert captured["CacheControl"] == "private, no-store"


def test_presigned_urls_expire_after_fifteen_minutes():
    fake = MagicMock()
    fake.generate_presigned_url.return_value = "https://example.test/private"
    with patch.object(storage, "_client", return_value=fake):
        assert storage.get_presigned_url("ws_test/invoice.pdf") == "https://example.test/private"
    assert fake.generate_presigned_url.call_args.kwargs["ExpiresIn"] == 900


def test_resolve_r2_endpoint_prefers_explicit():
    assert storage.resolve_r2_endpoint(
        "https://abc.r2.cloudflarestorage.com/",
        "ignored",
    ) == "https://abc.r2.cloudflarestorage.com"


def test_resolve_r2_endpoint_derives_from_account_id():
    assert storage.resolve_r2_endpoint(
        "",
        "0123456789abcdef0123456789abcdef",
    ) == "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"


def test_resolve_r2_endpoint_empty_without_inputs():
    assert storage.resolve_r2_endpoint("", "") == ""


def test_probe_r2_not_configured():
    with patch.object(storage, "r2_configured", return_value=False):
        assert storage.probe_r2() == {"configured": False, "ok": False}


def test_probe_r2_ok_when_head_bucket_succeeds():
    fake = MagicMock()
    with patch.object(storage, "r2_configured", return_value=True), patch.object(
        storage, "_client", return_value=fake
    ), patch.object(storage, "R2_BUCKET_NAME", "helm-documents"):
        result = storage.probe_r2()
    fake.head_bucket.assert_called_once_with(Bucket="helm-documents")
    assert result == {"configured": True, "ok": True, "bucket": "helm-documents"}


def test_probe_r2_reports_error_type():
    fake = MagicMock()
    fake.head_bucket.side_effect = RuntimeError("boom")
    with patch.object(storage, "r2_configured", return_value=True), patch.object(
        storage, "_client", return_value=fake
    ), patch.object(storage, "R2_BUCKET_NAME", "helm-documents"):
        result = storage.probe_r2()
    assert result["configured"] is True
    assert result["ok"] is False
    assert result["error"] == "RuntimeError"


def test_upload_rejects_pathlike_workspace_id():
    with patch.object(storage, "r2_configured", return_value=True), patch.object(
        storage, "_client", return_value=MagicMock()
    ):
        with pytest.raises(ValueError, match="workspace_id"):
            storage.upload_document("../evil", b"%PDF", "a.pdf", "application/pdf")


def test_object_key_helpers_reject_traversal():
    with pytest.raises(ValueError, match="storage key"):
        storage.get_presigned_url("../secret")
    with pytest.raises(ValueError, match="storage key"):
        storage.delete_document("/absolute/key")
