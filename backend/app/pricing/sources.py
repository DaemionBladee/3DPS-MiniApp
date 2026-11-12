"""Build pricing inputs from current, server-authorized source records only."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.registry import safe_profile
from app.analysis.registry import snapshot as profile_snapshot
from app.api.pricing_schemas import DesignPricingBasis
from app.core.errors import AuthError
from app.database.analysis_models import SlicerProfile, SlicingRun
from app.database.business_models import ServiceRequest
from app.database.design_models import DesignProject, DesignScope
from app.database.intake_models import RequestItem
from app.database.pricing_models import PricingAvailabilityFixture
from app.pricing.policies import AvailabilityDefinition, checksum
from app.services.analysis import results
from app.services.specifications import item_specification

CALCULATION_VERSION = "m07-decimal-1"


async def latest_availability(db: AsyncSession) -> PricingAvailabilityFixture | None:
    return await db.scalar(
        select(PricingAvailabilityFixture).where(PricingAvailabilityFixture.active).limit(1)
    )


async def build_sources(
    db: AsyncSession, row: ServiceRequest, now: datetime, basis: DesignPricingBasis | None
) -> tuple[dict[str, Any], list[dict[str, Any]], AvailabilityDefinition | None]:
    source: dict[str, Any] = {
        "calculation_version": CALCULATION_VERSION,
        "request_id": str(row.id),
        "request_version": row.version,
        "request_revision": row.revision,
        "spec_sha256": row.canonical_spec_sha256,
        "stage_kind": row.stage_kind,
        "service_type": row.service_type,
        "evaluation_day_utc": now.date().isoformat(),
        "source_design_version_id": str(row.source_design_version_id)
        if row.source_design_version_id
        else None,
    }
    if row.stage_kind == "design":
        if basis is None:
            raise AuthError(
                422,
                "design_basis_required",
                "The Owner must supply scoped design hours and pricing assumptions.",
            )
        project = await db.scalar(
            select(DesignProject).where(DesignProject.request_id == row.id).with_for_update()
        )
        if project is None:
            raise AuthError(409, "design_scope_missing", "Create the design scope before pricing.")
        scope = await db.scalar(
            select(DesignScope)
            .where(DesignScope.design_project_id == project.id)
            .order_by(DesignScope.number.desc())
            .limit(1)
            .with_for_update()
        )
        if scope is None or scope.id != basis.scope_id:
            raise AuthError(
                409, "design_scope_stale", "Price only the current Owner-authored scope."
            )
        source.update(
            scope={
                "id": str(scope.id),
                "number": scope.number,
                "specification": scope.specification,
                "agreed_at": scope.agreed_at.isoformat() if scope.agreed_at else None,
                "agreed_by": str(scope.agreed_by) if scope.agreed_by else None,
            },
            design_basis=basis.model_dump(mode="json"),
            design_project_id=str(project.id),
            latest_design_version_id=str(project.latest_version_id)
            if project.latest_version_id
            else None,
            approved_design_version_id=str(project.approved_version_id)
            if project.approved_version_id
            else None,
        )
        return source, [], None
    if basis is not None:
        raise AuthError(
            422,
            "printing_basis_invalid",
            "Printing prices use verified slicing, not a design-hours input.",
        )
    current = {result.request_item_id: result for result in (await results(db, row)).items}
    items = (
        await db.scalars(
            select(RequestItem)
            .where(RequestItem.request_id == row.id, RequestItem.active)
            .order_by(RequestItem.id)
        )
    ).all()
    engine_items = []
    snapshots = []
    for item in items:
        result = current.get(item.id)
        specification = item_specification(item).model_dump(mode="json")
        profile = None
        run = await db.get(SlicingRun, result.id) if result else None
        provenance = False
        if result:
            profile = await db.scalar(
                select(SlicerProfile)
                .where(SlicerProfile.id == result.profile.id)
                .with_for_update(read=True)
            )
            if profile is not None:
                try:
                    safe_profile(profile)
                    provenance = (
                        result.profile_snapshot == profile_snapshot(profile)
                        and result.engine_version == profile.engine_version
                        and result.executable_sha256 == profile.executable_sha256
                        and result.worker_image == profile.worker_image
                        and result.profile.config_sha256 == profile.config_sha256
                        and profile.material_key == item.material_key
                        and profile.quality_key == item.quality_key
                    )
                except ValueError:
                    provenance = False
        metric = (
            result.estimate if result and result.outcome == "estimated" and provenance else None
        )
        geometry = result.geometry.model_dump(mode="json") if result else None
        dimensions_confirmed = bool(
            result
            and specification["unit_confirmed"]
            and all(
                specification[f"dimension_{axis}_mm"] is not None
                and abs(
                    result.geometry.dimensions_mm.model_dump()[axis]
                    - specification[f"dimension_{axis}_mm"]
                )
                <= specification["dimension_tolerance_mm"]
                for axis in "xyz"
            )
        )
        engine_item = {
            "item_id": str(item.id),
            **specification,
            "authoritative": bool(metric and provenance),
            "filament_g": str(metric.filament_g) if metric else None,
            "print_seconds": metric.print_seconds if metric else None,
            "profile_id": str(profile.id) if profile else None,
            "geometry": geometry,
            "dimensions_confirmed": dimensions_confirmed,
        }
        engine_items.append(engine_item)
        snapshots.append(
            {
                "item_id": str(item.id),
                "specification": specification,
                "run_id": str(result.id) if result else None,
                "analysis_task_id": str(result.task_id) if result else None,
                "analysis_id": str(run.model_analysis_id) if run else None,
                "uploaded_file_id": str(result.uploaded_file_id)
                if result
                else str(item.model_file_id)
                if item.model_file_id
                else None,
                "input_sha256": result.input_sha256 if result else None,
                "profile": profile_snapshot(profile) if profile else None,
                "engine_version": result.engine_version if result else None,
                "executable_sha256": result.executable_sha256 if result else None,
                "worker_image": result.worker_image if result else None,
                "geometry": geometry,
                "metrics": metric.model_dump(mode="json") if metric else None,
                "authoritative": bool(metric and provenance),
            }
        )
    fixture = await latest_availability(db)
    fixture_config = None
    if fixture is not None:
        source["availability"] = {
            "id": str(fixture.id),
            "version": fixture.version,
            "checksum": fixture.checksum,
            "expires_at": fixture.expires_at.isoformat(),
            "usable": fixture.expires_at > now
            and checksum(fixture.configuration) == fixture.checksum,
        }
        if source["availability"]["usable"]:
            try:
                fixture_config = AvailabilityDefinition.model_validate(fixture.configuration)
            except ValueError:
                source["availability"]["usable"] = False
    else:
        source["availability"] = None
    source["items"] = snapshots
    return source, engine_items, fixture_config
