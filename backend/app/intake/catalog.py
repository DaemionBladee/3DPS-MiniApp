from app.api.intake_schemas import CatalogOption, ItemSpecification, MaterialOption, PrintingOptions
from app.core.config import Settings
from app.core.errors import AuthError

COLORS = {
    "dev-pla": ["dev-white", "dev-black", "not-sure"],
    "dev-petg": ["dev-black", "not-sure"],
    "not-sure": ["not-sure"],
}


def validate_spec(specification: ItemSpecification, *, complete: bool = False) -> None:
    if specification.color_key is not None and specification.material_key is not None:
        if specification.color_key not in COLORS[specification.material_key]:
            raise AuthError(422, "invalid_material_color", "Choose a compatible development color.")
    if complete and (
        not specification.material_key
        or not specification.color_key
        or not specification.quality_key
        or not specification.unit_confirmed
    ):
        raise AuthError(
            422, "incomplete_item", "Complete the printing settings and confirm model units."
        )


def options(settings: Settings) -> PrintingOptions:
    return PrintingOptions(
        materials=[
            MaterialOption(key=key, label=label, color_keys=COLORS[key])
            for key, label in [
                ("dev-pla", "PLA (development)"),
                ("dev-petg", "PETG (development)"),
                ("not-sure", "Not sure — Owner review required"),
            ]
        ],
        colors=[
            CatalogOption(key=key, label=label)
            for key, label in [
                ("dev-white", "White (development)"),
                ("dev-black", "Black (development)"),
                ("not-sure", "Not sure — Owner review required"),
            ]
        ],
        qualities=[
            CatalogOption(key=key, label=label)
            for key, label in [
                ("dev-standard", "Standard (development)"),
                ("dev-fine", "Fine (development)"),
                ("not-sure", "Not sure — Owner review required"),
            ]
        ],
        units=[
            CatalogOption(key=key, label=label)
            for key, label in [
                ("mm", "Millimeters"),
                ("cm", "Centimeters"),
                ("inch", "Inches"),
                ("um", "Microns"),
                ("ft", "Feet"),
                ("m", "Meters"),
            ]
        ],
        max_file_bytes=settings.upload_max_bytes,
        max_request_files=settings.request_file_limit,
    )
