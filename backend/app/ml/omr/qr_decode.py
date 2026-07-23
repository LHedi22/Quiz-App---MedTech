"""Extracts and decodes the per-version QR code from a scanned page image.

The QR box's position is fixed per `pdf_template.json` (see
`app/services/pdf_gen.py::_draw_qr`), so decoding just needs to crop that
region and hand it to the same `pyzbar`-backed decoder already used for the
standalone QR round-trip in `app/services/qr.py` (Phase 4.1) - OpenCV's own
`QRCodeDetector` was tried there and found unreliable on this machine, see
that module's docstring/PROGRESS.md.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.services.geometry import qr_box_pixel_rect
from app.services.qr import decode_qr


def decode_qr_from_page(page_image: np.ndarray, template: dict, dpi: int = 200) -> str | None:
    """Crop the page's fixed QR box and decode it. Returns None - never
    raises - if the QR code is unreadable, occluded, or the crop is out of
    bounds/empty."""
    x0, y0, x1, y1 = qr_box_pixel_rect(template, dpi)
    img_h, img_w = page_image.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(img_w, x1), min(img_h, y1)

    crop = page_image[y0:y1, x0:x1]
    if crop.size == 0:
        return None

    bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR) if crop.ndim == 3 else crop
    ok, encoded = cv2.imencode(".png", bgr)
    if not ok:
        return None

    return decode_qr(encoded.tobytes())
