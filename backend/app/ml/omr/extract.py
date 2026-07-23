"""Crops individual bubble regions out of an already-aligned scanned page
image, using the same `pdf_template.json` coordinates that both PDF
rendering (Phase 4.2) and page alignment (Phase 5.1) consult. Because the
image has already been homography-corrected by `align.py`, every bubble's
pixel position is a fixed, deterministic function of the template and the
working DPI - no per-scan search is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.services.geometry import bubble_center_pt, pdf_point_to_pixel

# Extra margin (in PDF points) added around the bubble's stroke radius so a
# fill that bleeds slightly past the circle's edge, or a stray mark just
# outside it, isn't clipped out of the crop the classifier sees.
CROP_PADDING_PT = 4.0


@dataclass
class BubbleCrop:
    row_index: int  # 0-based question position on the page
    option_index: int  # 0-based option position (post-shuffle) within the row
    image: np.ndarray


def extract_bubble_crops(
    aligned_image: np.ndarray,
    template: dict,
    num_questions_on_page: int,
    num_options: int,
    dpi: int = 200,
) -> list[BubbleCrop]:
    """Crop every bubble on a page of `num_questions_on_page` questions x
    `num_options` options each, in (row, option) order."""
    scale = dpi / 72.0
    page_h = template["page_height_pt"]
    half_size_px = int(round((template["bubble_radius_pt"] + CROP_PADDING_PT) * scale))

    img_h, img_w = aligned_image.shape[:2]
    crops: list[BubbleCrop] = []
    for row_index in range(num_questions_on_page):
        for option_index in range(num_options):
            x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
            px, py = pdf_point_to_pixel(x_pt, y_pt, page_h, dpi)
            px, py = int(round(px)), int(round(py))

            x0, x1 = max(0, px - half_size_px), min(img_w, px + half_size_px)
            y0, y1 = max(0, py - half_size_px), min(img_h, py + half_size_px)
            crops.append(BubbleCrop(row_index, option_index, aligned_image[y0:y1, x0:x1]))

    return crops
