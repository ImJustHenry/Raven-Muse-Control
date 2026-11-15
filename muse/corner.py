"""Layout within Raven's drawable area, not a change to its physical optics."""
COMPACT_SIZE = (256, 112)
EXPANDED_SIZE = (432, 320)
CONTROL_SIZE = (128, 104)
CONTROL_GAP = 16
INSET = 16
CORNERS = {"center_right", "center", "bottom_right", "bottom_left", "top_right", "top_left"}
DEFAULT_CORNER = "center_right"  # User choice (2026-11-14): vertically centred, right side.


def anchored_rect(view_width, view_height, width, height, corner=DEFAULT_CORNER, inset=INSET):
    if corner not in CORNERS:
        raise ValueError("Unknown UI corner")
    if min(width, height) <= 0 or inset < 0:
        raise ValueError("Invalid panel dimensions")
    if width + 2 * inset > view_width or height + 2 * inset > view_height:
        raise ValueError("Panel does not fit the drawable area")
    if corner == "center":
        return (view_width - width) // 2, (view_height - height) // 2, width, height
    if corner == "center_right":
        return view_width - inset - width, (view_height - height) // 2, width, height
    x = view_width - inset - width if corner.endswith("right") else inset
    y = view_height - inset - height if corner.startswith("bottom") else inset
    return x, y, width, height
