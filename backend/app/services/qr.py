"""QR code generation and decoding for exam version identification.

Every printed version encodes its `versions.qr_id` as a QR code. Scanning
(Phase 6) decodes it back to that string to look up the version's shuffle
mapping, so generation and decoding must round-trip exactly.
"""

from __future__ import annotations

import io

import qrcode
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode
from qrcode.constants import ERROR_CORRECT_M

QR_BOX_SIZE = 10
QR_BORDER = 4


def generate_qr(version_qr_id: str) -> bytes:
    """Render `version_qr_id` as PNG-encoded QR code bytes."""
    qr = qrcode.QRCode(
        error_correction=ERROR_CORRECT_M,
        box_size=QR_BOX_SIZE,
        border=QR_BORDER,
    )
    qr.add_data(version_qr_id)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def decode_qr(image_bytes: bytes) -> str | None:
    """Decode a QR code from raw image bytes (PNG/JPEG/etc). None if unreadable."""
    image = Image.open(io.BytesIO(image_bytes))
    results = zbar_decode(image)
    if not results:
        return None
    return results[0].data.decode("utf-8")
