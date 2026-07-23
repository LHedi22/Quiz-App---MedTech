"""Shared PDF-point <-> pixel coordinate math for the bubble-sheet template.

Consulted both when rendering the printable PDF (app/services/pdf_gen.py)
and when locating that same geometry in a scanned raster image during OMR
processing (app/ml/omr/*). Keeping the formulas in one place guarantees the
two stay in lockstep - pdf_template.json is the single source of truth for
both.
"""

from __future__ import annotations


def bubble_center_pt(template: dict, row_index: int, option_index: int) -> tuple[float, float]:
    row_y = template["first_question_y_pt"] - row_index * template["row_height_pt"]
    x = template["option_start_x_pt"] + option_index * template["option_spacing_x_pt"]
    y = row_y + template["bubble_dy_pt"]
    return x, y


def fiducial_positions_pt(template: dict) -> dict[str, tuple[float, float]]:
    """Bottom-left corner (PDF points, origin bottom-left) of each of the 4
    fiducial squares."""
    fid = template["fiducials"]
    size = fid["size_pt"]
    margin = fid["margin_from_edge_pt"]
    page_w = template["page_width_pt"]
    page_h = template["page_height_pt"]
    return {
        "top_left": (margin, page_h - margin - size),
        "top_right": (page_w - margin - size, page_h - margin - size),
        "bottom_left": (margin, margin),
        "bottom_right": (page_w - margin - size, margin),
    }


def fiducial_centers_pt(template: dict) -> dict[str, tuple[float, float]]:
    size = template["fiducials"]["size_pt"]
    half = size / 2
    return {name: (x + half, y + half) for name, (x, y) in fiducial_positions_pt(template).items()}


def pdf_point_to_pixel(
    x_pt: float, y_pt: float, page_height_pt: float, dpi: int
) -> tuple[float, float]:
    """Convert a PDF point (origin bottom-left, y-up) to a raster pixel
    coordinate (origin top-left, y-down) at the given DPI."""
    scale = dpi / 72.0
    return x_pt * scale, (page_height_pt - y_pt) * scale


def qr_box_pixel_rect(template: dict, dpi: int) -> tuple[int, int, int, int]:
    """Pixel bounding box (x0, y0, x1, y1) of the QR code box, top-left origin."""
    box = template["qr_box"]
    page_h = template["page_height_pt"]
    x0, y1 = pdf_point_to_pixel(box["x_pt"], box["y_pt"], page_h, dpi)
    x1, y0 = pdf_point_to_pixel(
        box["x_pt"] + box["size_pt"], box["y_pt"] + box["size_pt"], page_h, dpi
    )
    return int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
