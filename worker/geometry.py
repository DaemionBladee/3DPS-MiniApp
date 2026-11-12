"""Deterministic bounded geometry normalization; no repair, network or user settings."""

import hashlib
import math
import struct
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, cast
from xml.etree import ElementTree as ET

UNIT_SCALE = {
    "mm": 1.0,
    "cm": 10.0,
    "inch": 25.4,
    "um": 0.001,
    "ft": 304.8,
    "m": 1000.0,
}
THREE_MF_UNITS = {
    "millimeter": "mm",
    "centimeter": "cm",
    "inch": "inch",
    "micron": "um",
    "foot": "ft",
    "meter": "m",
}
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MAX_FACES = 100_000
Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]


class GeometryError(ValueError):
    pass


def sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def cross(a: Point, b: Point) -> Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def dot(a: Point, b: Point) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def transform(point: Point, matrix: list[float]) -> Point:
    x, y, z = point
    return (
        x * matrix[0] + y * matrix[3] + z * matrix[6] + matrix[9],
        x * matrix[1] + y * matrix[4] + z * matrix[7] + matrix[10],
        x * matrix[2] + y * matrix[5] + z * matrix[8] + matrix[11],
    )


def load(path: Path, kind: str) -> tuple[list[Triangle], int, str | None, list[str]]:
    triangles: list[Triangle] = []
    warnings: list[str] = []
    declared: str | None = None
    objects = 1
    if kind == "stl":
        with path.open("rb") as handle:
            head = handle.read(84)
            count = struct.unpack("<I", head[80:84])[0] if len(head) == 84 else 0
            if count and path.stat().st_size == 84 + 50 * count:
                if count > MAX_FACES:
                    raise GeometryError("geometry_complexity_limit")
                for _ in range(count):
                    data = struct.unpack("<12fH", handle.read(50))
                    triangles.append(
                        cast(
                            Triangle,
                            (tuple(data[3:6]), tuple(data[6:9]), tuple(data[9:12])),
                        )
                    )
            else:
                stl_vertices: list[Point] = []
                handle.seek(0)
                for raw in handle:
                    words = raw.decode("utf-8").split()
                    if words[:1] == ["vertex"]:
                        stl_vertices.append(
                            cast(Point, tuple(float(v) for v in words[1:4]))
                        )
                        if len(stl_vertices) == 3:
                            triangles.append(cast(Triangle, tuple(stl_vertices)))
                            stl_vertices = []
                            if len(triangles) > MAX_FACES:
                                raise GeometryError("geometry_complexity_limit")
    elif kind == "obj":
        vertices: list[Point] = []
        object_number = 0
        used_objects = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("#", 1)[0].split()
            if not fields:
                continue
            if fields[0] == "o":
                object_number += 1
            elif fields[0] == "v":
                values = [float(v) for v in fields[1:]]
                if len(values) == 4 and values[3] != 1:
                    raise GeometryError("unsupported_homogeneous_coordinates")
                vertices.append(cast(Point, tuple(values[:3])))
                if len(vertices) > MAX_FACES * 3:
                    raise GeometryError("geometry_complexity_limit")
            elif fields[0] == "f":
                indices = [int(v.split("/", 1)[0]) for v in fields[1:]]
                face = [vertices[i - 1 if i > 0 else i] for i in indices]
                used_objects.add(object_number)
                if len(face) > 3:
                    normal = cross(sub(face[1], face[0]), sub(face[2], face[0]))
                    length = math.sqrt(dot(normal, normal))
                    if length == 0 or any(
                        abs(dot(normal, sub(v, face[0]))) > 1e-8 * length for v in face
                    ):
                        raise GeometryError("nonplanar_obj_polygon")
                    turns = [
                        dot(
                            cross(
                                sub(face[(i + 1) % len(face)], face[i]),
                                sub(
                                    face[(i + 2) % len(face)], face[(i + 1) % len(face)]
                                ),
                            ),
                            normal,
                        )
                        for i in range(len(face))
                    ]
                    if any(value < -1e-12 for value in turns):
                        raise GeometryError("nonconvex_obj_polygon")
                    warnings.append("convex_polygon_triangulation")
                triangles.extend(
                    (face[0], face[i], face[i + 1]) for i in range(1, len(face) - 1)
                )
                if len(triangles) > MAX_FACES:
                    raise GeometryError("geometry_complexity_limit")
        objects = len(used_objects)
    elif kind == "3mf":
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("3D/3dmodel.model"))
        declared = THREE_MF_UNITS[root.get("unit", "millimeter")]
        resources = root.find(f"{{{CORE}}}resources")
        assert resources is not None
        definitions = {int(obj.attrib["id"]): obj for obj in resources}
        objects = 0
        identity = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

        def visit(object_id: int, matrices: list[list[float]], depth: int = 0) -> None:
            nonlocal objects
            if depth > 32:
                raise GeometryError("geometry_complexity_limit")
            obj = definitions[object_id]
            mesh = obj.find(f"{{{CORE}}}mesh")
            if mesh is not None:
                objects += 1
                vertex_nodes = mesh.find(f"{{{CORE}}}vertices")
                face_nodes = mesh.find(f"{{{CORE}}}triangles")
                assert vertex_nodes is not None and face_nodes is not None
                vertices = []
                for node in vertex_nodes:
                    point = cast(
                        Point, tuple(float(node.attrib[k]) for k in ["x", "y", "z"])
                    )
                    for matrix in matrices:
                        point = transform(point, matrix)
                    vertices.append(point)
                for face in face_nodes:
                    triangles.append(
                        cast(
                            Triangle,
                            tuple(
                                vertices[int(face.attrib[k])]
                                for k in ["v1", "v2", "v3"]
                            ),
                        )
                    )
                    if len(triangles) > MAX_FACES:
                        raise GeometryError("geometry_complexity_limit")
            else:
                components = obj.find(f"{{{CORE}}}components")
                assert components is not None
                for component in components:
                    matrix = (
                        [float(v) for v in component.attrib["transform"].split()]
                        if component.get("transform")
                        else identity
                    )
                    visit(
                        int(component.attrib["objectid"]),
                        [matrix, *matrices],
                        depth + 1,
                    )

        build = root.find(f"{{{CORE}}}build")
        assert build is not None
        for item in build:
            if item.get("printable", "1").lower() not in {"1", "true"}:
                raise GeometryError("nonprintable_3mf_item")
            matrix = (
                [float(v) for v in item.attrib["transform"].split()]
                if item.get("transform")
                else identity
            )
            visit(int(item.attrib["objectid"]), [matrix])
    else:
        raise GeometryError("unsupported_model")
    if not triangles:
        raise GeometryError("empty_geometry")
    return triangles, objects, declared, sorted(set(warnings))


def analyze(
    path: Path, kind: str, spec: dict[str, Any], profile: dict[str, Any]
) -> tuple[dict[str, Any], list[Triangle], list[str]]:
    triangles, objects, declared, warnings = load(path, kind)
    unit = spec.get("unit_key")
    review = []
    if not spec.get("unit_confirmed") or unit not in UNIT_SCALE:
        raise GeometryError("unit_confirmation_required")
    if declared and declared != unit:
        raise GeometryError("declared_unit_mismatch")
    scale = UNIT_SCALE[unit]
    triangles = [
        cast(
            Triangle,
            tuple(tuple(float(c) * scale for c in vertex) for vertex in triangle),
        )
        for triangle in triangles
    ]
    if any(
        not math.isfinite(c) or abs(c) > 1e6
        for triangle in triangles
        for vertex in triangle
        for c in vertex
    ):
        raise GeometryError("impossible_scale")
    points = list({point for triangle in triangles for point in triangle})
    lows = [min(p[i] for p in points) for i in range(3)]
    highs = [max(p[i] for p in points) for i in range(3)]
    dims = [highs[i] - lows[i] for i in range(3)]
    if min(dims) <= 1e-6:
        review.append("zero_thickness")
    ids = {p: i for i, p in enumerate(points)}
    parents = list(range(len(points)))

    def find(i: int) -> int:
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    edges: Counter[tuple[int, int]] = Counter()
    directed: Counter[tuple[int, int]] = Counter()
    faces: set[tuple[int, ...]] = set()
    degenerate = duplicate = 0
    volume = 0.0
    for a, b, c in triangles:
        i, j, k = ids[a], ids[b], ids[c]
        norm = cross(sub(b, a), sub(c, a))
        if len({i, j, k}) < 3 or dot(norm, norm) < 1e-18:
            degenerate += 1
        key = tuple(sorted([i, j, k]))
        if key in faces:
            duplicate += 1
        faces.add(key)
        for u, v in [(i, j), (j, k), (k, i)]:
            edge = (min(u, v), max(u, v))
            edges[edge] += 1
            directed[edge] += 1 if u < v else -1
            parents[find(u)] = find(v)
        # Translate the volume integral near the mesh to avoid cancellation
        # for small parts positioned far from the original coordinate origin.
        origin = cast(Point, tuple(lows))
        volume += dot(sub(a, origin), cross(sub(b, origin), sub(c, origin))) / 6.0
    boundary = sum(count == 1 for count in edges.values())
    nonmanifold = sum(count > 2 for count in edges.values())
    winding = sum(edges[key] == 2 and sign != 0 for key, sign in directed.items())
    watertight = not (boundary or nonmanifold or degenerate or duplicate or winding)
    if boundary:
        review.append("open_mesh")
    if nonmanifold:
        review.append("nonmanifold_edges")
    if degenerate:
        review.append("degenerate_faces")
    if duplicate:
        review.append("duplicate_faces")
    if winding or volume <= 0:
        review.append("inconsistent_winding")
    compatible = all(
        dims[i] <= profile[key]
        for i, key in enumerate(["build_x_mm", "build_y_mm", "build_z_mm"])
    )
    if not compatible:
        review.append("build_volume_exceeded")
    targets = [spec.get(f"dimension_{axis}_mm") for axis in "xyz"]
    if any(value is not None for value in targets):
        tolerance = spec.get("dimension_tolerance_mm", 0.5)
        if any(
            target is None or abs(dims[i] - target) > tolerance
            for i, target in enumerate(targets)
        ):
            review.append("customer_dimension_mismatch")
    components = len({find(i) for i in range(len(points))})
    if components > 1:
        warnings.append("multiple_mesh_components")
    warnings.extend(
        [
            "uncalibrated_virtual_profile",
            "self_intersections_not_checked",
            "simulation_only",
        ]
    )
    result = {
        "format": kind,
        "unit_key": unit,
        "declared_unit": declared,
        "dimensions_mm": dict(zip("xyz", dims, strict=True)),
        "volume_mm3": volume if watertight and volume > 0 else None,
        "object_count": objects,
        "component_count": components,
        "triangle_count": len(triangles),
        "watertight": watertight,
        "boundary_edges": boundary,
        "nonmanifold_edges": nonmanifold,
        "degenerate_faces": degenerate,
        "duplicate_faces": duplicate,
        "winding_errors": winding,
        "build_volume_compatible": compatible,
        "warnings": sorted(set(warnings)),
        "review_reasons": sorted(set(review)),
    }
    # Translate only to a local zero origin for toolpath generation; never scale,
    # repair or change customer topology. Original dimensions/provenance retained.
    centered = [
        cast(Triangle, tuple(tuple(p[i] - lows[i] for i in range(3)) for p in face))
        for face in triangles
    ]
    return result, centered, review


def write_stl(path: Path, triangles: list[Triangle]) -> None:
    with path.open("w", encoding="ascii") as output:
        output.write("solid normalized\n")
        for face in triangles:
            output.write("facet normal 0 0 0\nouter loop\n")
            for point in face:
                output.write(
                    "vertex "
                    + " ".join(format(value, ".17g") for value in point)
                    + "\n"
                )
            output.write("endloop\nendfacet\n")
        output.write("endsolid normalized\n")


def geometric_signature(triangles: list[Triangle]) -> str:
    # Order-independent comparison at STL's native floating-point precision.
    faces = []
    for face in triangles:
        points = [tuple(round(value, 5) for value in point) for point in face]
        variants = [points[i:] + points[:i] for i in range(3)]
        faces.append(min(variants))
    return hashlib.sha256(repr(sorted(faces)).encode("ascii")).hexdigest()
