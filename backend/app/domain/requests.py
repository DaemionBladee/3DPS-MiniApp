import hashlib
import json
from typing import Literal

from app.core.errors import AuthError
from app.domain.types import RequestStatus, ServiceType, StageKind


def initial_stage(kind: ServiceType) -> StageKind:
    return "printing" if kind == "printing" else "design"


def specification_hash(kind: ServiceType, stage: StageKind, notes: str) -> str:
    encoded = json.dumps(
        {"service_type": kind, "stage_kind": stage, "customer_notes": notes},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def transition(status: RequestStatus, target: Literal["submitted", "cancelled"]) -> RequestStatus:
    if status != "draft":
        raise AuthError(409, "invalid_transition", "This request is no longer a draft.")
    if target == "submitted":
        # Never claim file/scope validation exists before M04/M05.
        raise AuthError(
            409,
            "intake_not_available",
            "Submission requires file or scope validation from a later milestone.",
        )
    return "cancelled"
