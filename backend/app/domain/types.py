from typing import Literal

ServiceType = Literal["printing", "custom_design", "design_and_print"]
StageKind = Literal["design", "printing"]
RequestStatus = Literal["draft", "submitted", "analyzing", "manual_review", "cancelled"]
