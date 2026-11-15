import pytest
from muse.corner import COMPACT_SIZE, EXPANDED_SIZE, anchored_rect


@pytest.mark.parametrize("corner,expected", [
    ("center_right", (368, 264, 256, 112)),
    ("center", (192, 264, 256, 112)),
    ("bottom_right", (368, 512, 256, 112)),
    ("bottom_left", (16, 512, 256, 112)),
    ("top_right", (368, 16, 256, 112)),
    ("top_left", (16, 16, 256, 112)),
])
def test_compact_anchor(corner, expected):
    assert anchored_rect(640, 640, *COMPACT_SIZE, corner=corner) == expected


def test_expanded_defaults_to_centre():
    assert anchored_rect(640, 640, *EXPANDED_SIZE) == (192, 160, 432, 320)
    assert anchored_rect(640, 640, *EXPANDED_SIZE, corner="center") == (104, 160, 432, 320)
    assert anchored_rect(640, 640, *EXPANDED_SIZE, corner="bottom_right") == (192, 304, 432, 320)


def test_compact_raster_area_not_field_of_view_claim():
    fraction = COMPACT_SIZE[0] * COMPACT_SIZE[1] / (720 * 720)
    assert .055 < fraction < .056


@pytest.mark.parametrize("kwargs", [{"corner":"middle"}, {"inset":-1}])
def test_bad_corner_configuration(kwargs):
    with pytest.raises(ValueError):
        anchored_rect(640, 640, *COMPACT_SIZE, **kwargs)


def test_panel_must_fit():
    with pytest.raises(ValueError):
        anchored_rect(200, 200, *EXPANDED_SIZE)
