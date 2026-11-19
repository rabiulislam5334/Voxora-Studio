import pytest

from app.universal.visual_generation import (
    VisualGenerationProviderCapabilities,
    VisualGenerationProviderDescriptor,
    VisualGenerationProviderRegistry,
    VisualGenerationRequest,
    VisualGenerationValidationError,
)


def make_request(**overrides):
    values = {
        "request_id": "request-01",
        "scene_id": "scene-01",
        "prompt": "A cinematic observatory beneath a star-filled sky",
        "width": 1280,
        "height": 720,
        "output_format": "png",
        "image_count": 2,
        "seed": 42,
        "style_tags": ("cinematic", "2.5d"),
        "reference_asset_ids": ("asset-reference-01",),
        "metadata": {"channel_profile": "quasivanta", "quality": "draft"},
    }
    values.update(overrides)
    return VisualGenerationRequest(**values)


def make_provider(provider_id="local-diffusion", **overrides):
    values = {
        "provider_id": provider_id,
        "display_name": "Local Diffusion",
        "version": "1",
        "capabilities": VisualGenerationProviderCapabilities(
            output_formats=("png", "jpeg"),
            max_width=2048,
            max_height=2048,
            max_images_per_request=4,
            supports_reference_images=True,
            supports_seed=True,
            requires_network=False,
            requires_api_key=False,
            estimated_memory_mb=4096,
        ),
        "model_ids": ("sd15", "sdxl"),
        "available": True,
        "unavailable_reason": "",
    }
    values.update(overrides)
    return VisualGenerationProviderDescriptor(**values)


def test_request_round_trip_preserves_content_and_fingerprint():
    request = make_request()
    restored = VisualGenerationRequest.from_dict(request.to_dict())

    assert restored == request
    assert restored.fingerprint == request.fingerprint
    assert restored.to_dict()["request_version"] == 1


def test_request_fingerprint_changes_when_generation_inputs_change():
    original = make_request()
    changed = make_request(prompt="A different scene")

    assert original.fingerprint != changed.fingerprint


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_id": ""},
        {"scene_id": "scene with spaces"},
        {"prompt": ""},
        {"prompt": "x" * 12001},
        {"width": 32},
        {"height": 8193},
        {"width": 8192, "height": 8192},
        {"output_format": "webp"},
        {"image_count": 5},
        {"seed": -1},
        {"seed": True},
        {"style_tags": ("cinematic", "cinematic")},
        {"reference_asset_ids": ("asset-1", "asset-1")},
        {"metadata": {"bad": object()}},
    ],
)
def test_invalid_requests_are_rejected(overrides):
    with pytest.raises(VisualGenerationValidationError):
        make_request(**overrides)


def test_request_deserialization_rejects_string_sequences():
    payload = make_request().to_dict()
    payload["style_tags"] = "not-a-list"

    with pytest.raises(VisualGenerationValidationError, match="sequence"):
        VisualGenerationRequest.from_dict(payload)


def test_request_rejects_unknown_schema_version():
    payload = make_request().to_dict()
    payload["request_version"] = 2

    with pytest.raises(VisualGenerationValidationError, match="unsupported"):
        VisualGenerationRequest.from_dict(payload)


def test_provider_capabilities_validate_resource_limits_and_flags():
    with pytest.raises(VisualGenerationValidationError):
        VisualGenerationProviderCapabilities(max_width=0)
    with pytest.raises(VisualGenerationValidationError):
        VisualGenerationProviderCapabilities(supports_seed="yes")
    with pytest.raises(VisualGenerationValidationError):
        VisualGenerationProviderCapabilities(output_formats=("webp",))


def test_provider_descriptor_rejects_string_model_sequence():
    with pytest.raises(VisualGenerationValidationError, match="sequence"):
        make_provider(model_ids="not-a-list")


def test_provider_compatibility_accepts_matching_request():
    provider = make_provider()

    assert provider.compatibility_issues(make_request()) == ()


def test_provider_compatibility_reports_every_unsupported_requirement():
    provider = make_provider(
        capabilities=VisualGenerationProviderCapabilities(
            output_formats=("jpeg",),
            max_width=1024,
            max_height=1024,
            max_images_per_request=1,
            supports_reference_images=False,
            supports_seed=False,
            requires_network=True,
            requires_api_key=True,
        ),
        model_ids=("other-model",),
    )

    issues = provider.compatibility_issues(make_request(model_id="sdxl"))

    assert len(issues) == 6
    assert any("Model" in issue for issue in issues)
    assert any("exceeds provider limit" in issue for issue in issues)
    assert any("Output format" in issue for issue in issues)
    assert any("exceeds provider limit 1" in issue for issue in issues)
    assert any("reference images" in issue for issue in issues)
    assert any("seeds" in issue for issue in issues)


def test_unavailable_provider_is_not_compatible():
    provider = make_provider(available=False, unavailable_reason="Model files are missing")

    assert provider.compatibility_issues(make_request())
    assert provider not in VisualGenerationProviderRegistry([provider]).list_providers()


def test_registry_lists_and_resolves_exact_compatible_providers():
    remote = make_provider("remote-provider", capabilities=VisualGenerationProviderCapabilities(
        output_formats=("png",),
        max_width=2048,
        max_height=2048,
        max_images_per_request=4,
        supports_reference_images=True,
        supports_seed=True,
    ))
    local = make_provider("local-provider")
    registry = VisualGenerationProviderRegistry([remote, local])

    assert [item.provider_id for item in registry.list_providers()] == [
        "local-provider", "remote-provider"
    ]
    assert [item.provider_id for item in registry.find_compatible(make_request())] == [
        "local-provider", "remote-provider"
    ]
    assert registry.resolve("local-provider", make_request()) == local


def test_registry_never_silently_falls_back_to_another_provider():
    registry = VisualGenerationProviderRegistry([make_provider()])

    with pytest.raises(KeyError, match="unknown visual generation provider"):
        registry.resolve("missing-provider", make_request())


def test_registry_rejects_duplicate_provider_ids_unless_replaced():
    original = make_provider()
    registry = VisualGenerationProviderRegistry([original])
    replacement = make_provider(display_name="Updated Local Diffusion")

    with pytest.raises(ValueError, match="already registered"):
        registry.register(replacement)

    registry.register(replacement, replace=True)
    assert registry.get("local-diffusion").display_name == "Updated Local Diffusion"


def test_registry_rejects_non_descriptor_values():
    with pytest.raises(TypeError):
        VisualGenerationProviderRegistry([object()])
