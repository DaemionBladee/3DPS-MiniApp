"""Server-controlled, append-only virtual profiles; no public configuration editor."""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.profile_config import ENGINE_VERSION, canonical_hash, validate_profile
from app.database.analysis_models import SlicerProfile, VirtualPrinterModel


def snapshot(profile: SlicerProfile) -> dict[str, Any]:
    return {
        "id": str(profile.id),
        "key": profile.key,
        "version": profile.version,
        "virtual_printer_model_id": str(profile.virtual_printer_model_id),
        "config_sha256": profile.config_sha256,
        "configuration": profile.configuration,
    }


def safe_profile(profile: SlicerProfile) -> None:
    if (
        not profile.active
        or profile.approval_status != "approved"
        or profile.calibrated
        or not profile.simulation_only
        or profile.engine_version != ENGINE_VERSION
        or canonical_hash(validate_profile(profile.configuration)) != profile.config_sha256
        or not re.fullmatch("sha256:[0-9a-f]{64}", profile.worker_image)
    ):
        raise ValueError("unsafe_profile")


async def seed_profiles(db: AsyncSession, image: str, executable: str, version: int) -> list[UUID]:
    """Explicit administrative CLI only. Approves conservative simulation settings."""
    if (
        not re.fullmatch("sha256:[0-9a-f]{64}", image)
        or not re.fullmatch("[0-9a-f]{64}", executable)
        or version < 1
    ):
        raise ValueError("Exact immutable image/executable and positive revision required")
    await db.execute(text("SELECT pg_advisory_xact_lock(6006001)"))
    existing = (
        await db.scalars(select(SlicerProfile).where(SlicerProfile.version == version))
    ).all()
    if existing:
        if len(existing) != 4 or any(
            p.worker_image != image or p.executable_sha256 != executable for p in existing
        ):
            raise ValueError("Profile revision already exists with different provenance")
        return [p.id for p in existing]
    model = VirtualPrinterModel(
        key="generic-fdm-220",
        version=version,
        label="Virtual FDM 220 — unverified hardware assumptions",
        capabilities={
            "build_mm": [220, 220, 250],
            "nozzle_mm": 0.4,
            "materials": ["PLA", "PETG"],
            "physical_machine": False,
        },
    )
    db.add(model)
    await db.flush()
    profiles = []
    for material, density, temperature, bed in [
        ("dev-pla", 1.24, 205, 60),
        ("dev-petg", 1.27, 235, 80),
    ]:
        for quality, layer in [("dev-standard", 0.2), ("dev-fine", 0.12)]:
            config = validate_profile(
                {
                    "build_x_mm": 220,
                    "build_y_mm": 220,
                    "build_z_mm": 250,
                    "nozzle_mm": 0.4,
                    "filament_mm": 1.75,
                    "density_g_cm3": density,
                    "layer_mm": layer,
                    "speed_mm_s": 40,
                    "travel_mm_s": 100,
                    "temperature_c": temperature,
                    "bed_c": bed,
                    "retract_mm": 1,
                    "retract_mm_s": 30,
                    "infill_percent": 15,
                    "support_enabled": False,
                }
            )
            p = SlicerProfile(
                virtual_printer_model_id=model.id,
                key=f"virtual-{material}-{quality}",
                version=version,
                material_key=material,
                quality_key=quality,
                configuration=config,
                config_sha256=canonical_hash(config),
                engine_version=ENGINE_VERSION,
                executable_sha256=executable,
                worker_image=image,
            )
            db.add(p)
            profiles.append(p)
    await db.flush()
    return [p.id for p in profiles]
