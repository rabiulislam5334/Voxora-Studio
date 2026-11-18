from app.ui.composition_editor_tab import canvas_rect, move_transform
from app.universal.composition import VisualTransform


def test_canvas_rect_maps_normalized_bounds_to_pixels():
    rect = canvas_rect(VisualTransform(x=0.1, y=0.2, width=0.4, height=0.5), 1000, 500)
    assert rect == (100, 100, 500, 350)


def test_move_transform_clamps_element_inside_canvas():
    moved = move_transform(
        VisualTransform(x=0.2, y=0.3, width=0.5, height=0.4),
        dx=0.8,
        dy=-0.8,
    )
    assert moved.x == 0.5
    assert moved.y == 0.0
    assert moved.width == 0.5
    assert moved.height == 0.4


def test_move_transform_preserves_non_position_transform_fields():
    original = VisualTransform(
        x=0.1, y=0.1, width=0.3, height=0.4,
        anchor_x=0.2, anchor_y=0.7, rotation_degrees=30, opacity=0.6,
    )
    moved = move_transform(original, 0.1, 0.1)
    assert moved.anchor_x == 0.2
    assert moved.anchor_y == 0.7
    assert moved.rotation_degrees == 30
    assert moved.opacity == 0.6
