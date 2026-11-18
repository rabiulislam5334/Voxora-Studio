from types import SimpleNamespace

from app.ui.scene_asset_binding_tab import format_binding_preview, format_continuity_report


def test_binding_preview_summary_shows_counts_and_conflicts():
    preview = SimpleNamespace(
        scene_id="scene-1",
        asset_bindings=(object(), object()),
        character_bindings=(object(),),
        target_fingerprint="f" * 64,
        diagnostics=(SimpleNamespace(
            severity="error", code="ASSET_ALREADY_BOUND",
            message="This asset is already bound.",
        ),),
    )
    result = format_binding_preview(preview)
    assert "Scene: scene-1" in result
    assert "Assets to bind: 2" in result
    assert "Characters to bind: 1" in result
    assert "[ERROR] ASSET_ALREADY_BOUND" in result


def test_binding_preview_explains_clean_preview_requires_review():
    preview = SimpleNamespace(
        scene_id="scene-2", asset_bindings=(), character_bindings=(),
        target_fingerprint="a" * 64, diagnostics=(),
    )
    assert "No binding conflicts detected" in format_binding_preview(preview)
    assert "review the selection" in format_binding_preview(preview)


def test_continuity_report_includes_diagnostics_reuse_and_character_groups():
    report = SimpleNamespace(
        diagnostics=(SimpleNamespace(
            severity="warning", code="CHARACTER_APPEARANCE_CHANGED",
            scene_ids=("scene-1", "scene-3"), message="Review appearance.",
        ),),
        asset_reuse_groups=(SimpleNamespace(
            identity="asset-1", asset_ids=("asset-1",), scene_ids=("scene-1", "scene-2"),
        ),),
        character_groups=(SimpleNamespace(
            character_id="captain", scene_ids=("scene-1", "scene-3"),
            appearance_fingerprints=("a" * 64, "b" * 64),
        ),),
    )
    result = format_continuity_report(report)
    assert "Continuity diagnostics: 1" in result
    assert "CHARACTER_APPEARANCE_CHANGED" in result
    assert "REUSE asset-1" in result
    assert "CHARACTER captain" in result
    assert "appearances=2" in result
