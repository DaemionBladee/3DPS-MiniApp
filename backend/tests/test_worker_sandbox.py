"""Real sandbox evidence, plus deterministic geometry/unsafe profile negative tests."""

import json
import os

import pytest
from worker.geometry import GeometryError, analyze

from app.analysis.profile_config import canonical_hash, configuration, validate_profile
from app.analysis.sandbox import SandboxFailure, command, container_arguments
from app.intake.validation import InvalidModel, inspect
from tests.analysis_fixtures import cube
from tests.model_fixtures import MODEL_XML, RELS, TYPES, three_mf

PROFILE = {
    "build_x_mm": 220,
    "build_y_mm": 220,
    "build_z_mm": 250,
    "nozzle_mm": 0.4,
    "filament_mm": 1.75,
    "density_g_cm3": 1.24,
    "layer_mm": 0.2,
    "speed_mm_s": 40,
    "travel_mm_s": 100,
    "temperature_c": 205,
    "bed_c": 60,
    "retract_mm": 1,
    "retract_mm_s": 30,
    "infill_percent": 15,
    "support_enabled": False,
}


@pytest.mark.parametrize("mode", ["base", "network", "filesystem", "memory", "disk", "pids"])
async def test_actual_sandbox_denies_credentials_network_writes_and_resource_overruns(mode):
    image = os.environ.get("M06_TEST_WORKER_IMAGE")
    if not image:
        pytest.skip("Requires real immutable worker image, never a mocked sandbox")
    output = await command(
        "run",
        "--rm",
        "--env=DATABASE_URL=synthetic-secret-canary",
        "--env=BOT_TOKEN=synthetic-bot-canary",
        *container_arguments(image),
        "--probe=" + mode,
        timeout=75,  # bounded cold-start allowance plus the probe runtime
    )
    data = json.loads(output)["probe"]
    assert data["forbidden_environment"] == [] and data["network_devices"] == ["lo"]
    assert data["uid"] == 10001 and data["root_readonly"] and data["seccomp"] == "2"
    assert data["memory_limit"] == 768 * 1024**2 and data["pid_limit"] == 32
    if mode == "pids":
        assert data["pids_denied"] and data["children_started"] < 32
    elif mode in {"memory", "disk", "network"}:
        assert data[mode + "_denied"]
        if mode == "disk":
            assert 96 * 1024**2 <= data["written_bytes"] <= 128 * 1024**2
    elif mode == "filesystem":
        assert data["root_write_denied"]


async def test_actual_kernel_cpu_limit_kills_worker():
    image = os.environ.get("M06_TEST_WORKER_IMAGE")
    if not image:
        pytest.skip("Requires real immutable worker image")
    with pytest.raises(SandboxFailure, match="worker_crashed"):
        await command("run", "--rm", *container_arguments(image), "--probe=cpu", timeout=75)


@pytest.mark.parametrize(
    "spec,error",
    [
        ({"unit_key": "mm", "unit_confirmed": False}, "unit_confirmation_required"),
        ({"unit_key": "cm", "unit_confirmed": True}, "declared_unit_mismatch"),
    ],
)
def test_3mf_units_need_explicit_consistent_confirmation(tmp_path, spec, error):
    path = tmp_path / "cube.3mf"
    path.write_bytes(cube("3mf"))
    with pytest.raises(GeometryError, match=error):
        analyze(path, "3mf", spec, PROFILE)


@pytest.mark.parametrize(
    "config",
    [
        PROFILE | {"post_process": "evil"},
        PROFILE | {"temperature_c": float("nan")},
        PROFILE | {"speed_mm_s": "$(evil)"},
        PROFILE | {"layer_mm": 1},
        PROFILE | {"density_g_cm3": True},
    ],
)
def test_profile_surface_rejects_hooks_nonfinite_or_unapproved_settings(config):
    with pytest.raises(ValueError, match="unsafe_profile"):
        validate_profile(config)


def test_profile_hash_is_canonical_and_all_hooks_are_empty():
    assert canonical_hash(PROFILE) == canonical_hash(dict(reversed(list(PROFILE.items()))))
    settings = configuration(PROFILE)
    assert "post_process = \n" in settings and "start_gcode = \n" in settings


@pytest.mark.parametrize(
    "parts",
    [
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML,
            "Metadata/Slic3r_PE.config": b"post_process=evil",
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS.replace(
                b'Target="/3D/3dmodel.model"',
                b'Target="https://evil.test/model" TargetMode="External"',
            ),
            "3D/3dmodel.model": MODEL_XML,
        },
        {
            "../escape": b"bad",
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML,
        },
    ],
)
def test_embedded_3mf_settings_external_resources_and_traversal_rejected(parts):
    import io

    data = three_mf(parts)
    with pytest.raises(InvalidModel):
        inspect(
            io.BytesIO(data),
            len(data),
            {"entries": 64, "expanded": 64 * 1024**2, "entry_bytes": 16 * 1024**2, "ratio": 100},
        )


def test_translated_mesh_volume_is_numerically_stable(tmp_path):
    from tests.analysis_fixtures import FACES, POINTS

    data = (
        "solid translated\n"
        + "".join(
            "facet normal 0 0 0\nouter loop\n"
            + "".join("vertex " + " ".join(str(v + 999000) for v in POINTS[i]) + "\n" for i in face)
            + "endloop\nendfacet\n"
            for face in FACES
        )
        + "endsolid translated\n"
    )
    path = tmp_path / "translated.stl"
    path.write_text(data)
    geometry, _, review = analyze(path, "stl", {"unit_key": "mm", "unit_confirmed": True}, PROFILE)
    assert geometry["volume_mm3"] == pytest.approx(8000)
    assert geometry["dimensions_mm"] == dict(x=20, y=20, z=20)
    assert not review
