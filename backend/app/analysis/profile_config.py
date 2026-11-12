"""Typed numeric profile surface; arbitrary slicer configuration is never accepted."""

import hashlib
import json
import math
from typing import Any

ENGINE_VERSION = "2.5.0+UNKNOWN"
DEBIAN_PACKAGE = "2.5.0+dfsg-4"
PROFILE_KEYS = {
    "build_x_mm",
    "build_y_mm",
    "build_z_mm",
    "nozzle_mm",
    "filament_mm",
    "density_g_cm3",
    "layer_mm",
    "speed_mm_s",
    "travel_mm_s",
    "temperature_c",
    "bed_c",
    "retract_mm",
    "retract_mm_s",
    "infill_percent",
    "support_enabled",
}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def validate_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROFILE_KEYS:
        raise ValueError("unsafe_profile")
    ranges = {
        "build_x_mm": (10, 1000),
        "build_y_mm": (10, 1000),
        "build_z_mm": (10, 1000),
        "nozzle_mm": (0.2, 1.0),
        "filament_mm": (1.5, 3),
        "density_g_cm3": (0.5, 2.5),
        "layer_mm": (0.05, 0.5),
        "speed_mm_s": (5, 100),
        "travel_mm_s": (20, 200),
        "temperature_c": (170, 280),
        "bed_c": (0, 110),
        "retract_mm": (0, 5),
        "retract_mm_s": (5, 60),
        "infill_percent": (0, 100),
    }
    for key, (low, high) in ranges.items():
        number = value[key]
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not math.isfinite(number)
            or not low <= number <= high
        ):
            raise ValueError("unsafe_profile")
    if (
        type(value["support_enabled"]) is not bool
        or value["layer_mm"] > value["nozzle_mm"] * 0.75
    ):
        raise ValueError("unsafe_profile")
    return value


def configuration(value: dict[str, Any]) -> str:
    p = validate_profile(value)
    settings = {
        "printer_technology": "FFF",
        "bed_shape": f"0x0,{p['build_x_mm']}x0,{p['build_x_mm']}x{p['build_y_mm']},0x{p['build_y_mm']}",
        "max_print_height": p["build_z_mm"],
        "nozzle_diameter": p["nozzle_mm"],
        "filament_diameter": p["filament_mm"],
        "filament_density": p["density_g_cm3"],
        "layer_height": p["layer_mm"],
        "first_layer_height": p["layer_mm"],
        "perimeters": 2,
        "top_solid_layers": 4,
        "bottom_solid_layers": 4,
        "fill_density": f"{p['infill_percent']}%",
        "fill_pattern": "rectilinear",
        "perimeter_speed": p["speed_mm_s"],
        "external_perimeter_speed": p["speed_mm_s"] * 0.75,
        "infill_speed": p["speed_mm_s"],
        "solid_infill_speed": p["speed_mm_s"],
        "travel_speed": p["travel_mm_s"],
        "first_layer_speed": 20,
        "temperature": p["temperature_c"],
        "first_layer_temperature": p["temperature_c"],
        "bed_temperature": p["bed_c"],
        "first_layer_bed_temperature": p["bed_c"],
        "retract_length": p["retract_mm"],
        "retract_speed": p["retract_mm_s"],
        "support_material": int(p["support_enabled"]),
        "support_material_auto": int(p["support_enabled"]),
        "gcode_flavor": "reprap",
        "threads": 1,
    }
    for name in [
        "start_gcode",
        "end_gcode",
        "layer_gcode",
        "before_layer_gcode",
        "toolchange_gcode",
        "filament_start_gcode",
        "filament_end_gcode",
        "post_process",
    ]:
        settings[name] = ""
    return (
        "\n".join(f"{key} = {value}" for key, value in sorted(settings.items())) + "\n"
    )
