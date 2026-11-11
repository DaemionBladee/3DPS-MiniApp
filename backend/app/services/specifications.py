"""Canonical print specifications and revision invalidation, independent of routes."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.intake_schemas import ItemSpecification
from app.database.business_models import ServiceRequest
from app.database.intake_models import ProcessingTask, RequestItem, UploadedFile
from app.domain.requests import specification_hash


def item_specification(item: RequestItem) -> ItemSpecification:
    return ItemSpecification.model_validate(
        {key: getattr(item, key) for key in ItemSpecification.model_fields}
    )


async def canonical_spec(database: AsyncSession, row: ServiceRequest) -> dict[str, Any]:
    items = (
        await database.scalars(
            select(RequestItem)
            .where(RequestItem.request_id == row.id, RequestItem.active)
            .order_by(RequestItem.id)
        )
    ).all()
    values: list[dict[str, Any]] = []
    for item in items:
        file = await database.get(UploadedFile, item.model_file_id) if item.model_file_id else None
        values.append(
            {
                "item_id": str(item.id),
                "specification": item_specification(item).model_dump(),
                "file": {
                    "id": str(file.id),
                    "sha256": file.sha256,
                    "format": file.format,
                    "size_bytes": file.size_bytes,
                }
                if file
                else None,
            }
        )
    return {
        "schema_version": 2,
        "service_type": row.service_type,
        "stage_kind": row.stage_kind,
        "customer_notes": row.customer_notes,
        "fulfillment_method": row.fulfillment_method,
        "fulfillment_notes": row.fulfillment_notes,
        "items": values,
    }


def canonical_hash(specification: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            specification, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


async def refresh_spec(
    database: AsyncSession, row: ServiceRequest, *, advance: bool = True
) -> None:
    if advance:
        row.revision += 1
        row.version += 1
    row.updated_at = datetime.now(UTC)
    if row.stage_kind == "printing":
        row.spec_schema_version = 2
        await database.flush()
        await database.execute(
            update(RequestItem)
            .where(RequestItem.request_id == row.id, RequestItem.active)
            .values(request_revision=row.revision)
        )
        row.canonical_spec_sha256 = canonical_hash(await canonical_spec(database, row))
    else:
        row.canonical_spec_sha256 = specification_hash(
            row.service_type, row.stage_kind, row.customer_notes
        )
    await database.execute(
        update(ProcessingTask)
        .where(
            ProcessingTask.request_id == row.id,
            ProcessingTask.state == "pending",
            ProcessingTask.request_revision != row.revision,
        )
        .values(state="superseded")
    )
