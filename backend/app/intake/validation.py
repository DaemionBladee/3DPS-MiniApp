"""Conservative structural intake validators; never evaluate, render or slice data.

CLI runs in a credential-free resource-bounded subprocess. Geometry, scale,
watertightness, manufacturability and pricing are deliberately not analyzed.
"""

import asyncio
import json
import math
import os
import re
import resource
import stat
import struct
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, BinaryIO
from xml.etree import ElementTree as ET

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT = "http://schemas.openxmlformats.org/package/2006/content-types"
MODEL_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
MAX_LINE = 16384


class InvalidModel(ValueError):
    def __init__(self, code: str = "invalid_model", status: int = 422):
        self.code, self.status = code, status


def finite(value: str | float) -> float:
    if isinstance(value, str) and (
        len(value) > 64
        or not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value)
    ):
        raise InvalidModel()
    result = float(value)
    if not math.isfinite(result) or abs(result) > 1e9:
        raise InvalidModel()
    return result


def lines(handle: BinaryIO) -> Iterator[str]:
    handle.seek(0)
    for _ in range(2000000):
        raw = handle.readline(MAX_LINE + 1)
        if not raw:
            return
        if len(raw) > MAX_LINE or b"\x00" in raw:
            raise InvalidModel()
        line = raw.decode("utf-8", errors="strict").strip()
        if line:
            yield line
    raise InvalidModel("model_complexity_limit")


def validate_stl(handle: BinaryIO, size: int) -> dict[str, Any]:
    handle.seek(0)
    header = handle.read(84)
    if len(header) == 84:
        triangles = struct.unpack("<I", header[80:84])[0]
        if triangles and size == 84 + 50 * triangles:
            for _ in range(triangles):
                values = struct.unpack("<12fH", handle.read(50))
                for coordinate in values[:12]:
                    finite(coordinate)
            return {"format": "stl", "mime": "model/stl", "details": {}}
    iterator = iter(lines(handle))
    if next(iterator, "").split(maxsplit=1)[:1] != ["solid"]:
        raise InvalidModel()
    count = 0
    for line in iterator:
        if line.split(maxsplit=1)[:1] == ["endsolid"]:
            if not count or next(iterator, None) is not None:
                raise InvalidModel()
            return {"format": "stl", "mime": "model/stl", "details": {}}
        fields = line.split()
        if len(fields) != 5 or fields[:2] != ["facet", "normal"]:
            raise InvalidModel()
        for value in fields[2:]:
            finite(value)
        if next(iterator, "") != "outer loop":
            raise InvalidModel()
        for _ in range(3):
            vertex = next(iterator, "").split()
            if len(vertex) != 4 or vertex[0] != "vertex":
                raise InvalidModel()
            for value in vertex[1:]:
                finite(value)
        if next(iterator, "") != "endloop" or next(iterator, "") != "endfacet":
            raise InvalidModel()
        count += 1
    raise InvalidModel()


def validate_obj(handle: BinaryIO) -> dict[str, Any]:
    counts = [0, 0, 0]
    faces = 0
    for line in lines(handle):
        fields = line.split("#", 1)[0].split()
        if not fields:
            continue
        command, values = fields[0], fields[1:]
        if command in {"mtllib", "usemtl", "call", "csh"}:
            raise InvalidModel("external_model_reference", 415)
        if command in {"v", "vt", "vn"}:
            index = {"v": 0, "vt": 1, "vn": 2}[command]
            if len(values) not in (
                {3, 4} if command == "v" else {1, 2, 3} if command == "vt" else {3}
            ):
                raise InvalidModel()
            for coordinate in values:
                finite(coordinate)
            counts[index] += 1
        elif command == "f":
            if not 3 <= len(values) <= 1024:
                raise InvalidModel()
            for vertex in values:
                parts = vertex.split("/")
                if not 1 <= len(parts) <= 3 or not parts[0]:
                    raise InvalidModel()
                for position, part in enumerate(parts):
                    if not part and position == 1 and len(parts) == 3:
                        continue
                    if not part:
                        raise InvalidModel()
                    value = int(part)
                    if value == 0 or not -counts[position] <= value <= counts[position]:
                        raise InvalidModel()
            faces += 1
        elif command not in {"o", "g", "s"}:
            raise InvalidModel("unsupported_model_content", 415)
    if counts[0] < 3 or faces < 1:
        raise InvalidModel()
    return {"format": "obj", "mime": "model/obj", "details": {}}


def xml(data: bytes, namespace: str, name: str) -> ET.Element:
    if b"\x00" in data or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise InvalidModel("unsafe_archive_xml")
    text = data.decode("utf-8-sig", errors="strict")
    declaration = re.match(r'\s*<\?xml[^?]*encoding=[\'"]([^\'"]+)', text, re.I)
    if declaration and declaration[1].lower() not in {"utf-8", "utf8"}:
        raise InvalidModel("unsupported_model_content", 415)
    root = ET.fromstring(text)
    if root.tag != f"{{{namespace}}}{name}":
        raise InvalidModel()
    depth = [(root, 1)]
    count = 0
    while depth:
        node, level = depth.pop()
        count += 1
        if level > 32 or count > 500000:
            raise InvalidModel("archive_xml_limit")
        depth.extend((child, level + 1) for child in node)
    return root


def validate_3mf(handle: BinaryIO, limits: dict[str, int]) -> dict[str, Any]:
    allowed = {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
    with zipfile.ZipFile(handle) as archive:
        entries = archive.infolist()
        if len(entries) > limits["entries"]:
            raise InvalidModel("archive_entry_limit")
        expanded = 0
        names: set[str] = set()
        content: dict[str, bytes] = {}
        for info in entries:
            name = info.filename
            parts = name.rstrip("/").split("/")
            mode = stat.S_IFMT(info.external_attr >> 16)
            if (
                not name
                or name.startswith("/")
                or "\\" in name
                or ":" in name
                or any(part in {"", ".", ".."} for part in parts)
                or any(ord(character) < 32 for character in name)
                or mode not in {0, stat.S_IFREG, stat.S_IFDIR}
                or info.flag_bits & 1
            ):
                raise InvalidModel("unsafe_archive_path")
            folded = name.casefold()
            if folded in names:
                raise InvalidModel("duplicate_archive_entry")
            names.add(folded)
            if mode == stat.S_IFDIR and not info.is_dir():
                raise InvalidModel("unsafe_archive_path")
            if info.is_dir():
                if info.file_size != 0 or mode == stat.S_IFREG:
                    raise InvalidModel("unsafe_archive_path")
                if name not in {"3D/", "_rels/"}:
                    raise InvalidModel("unsupported_model_content", 415)
                continue
            if name not in allowed or info.compress_type not in {
                zipfile.ZIP_STORED,
                zipfile.ZIP_DEFLATED,
            }:
                raise InvalidModel("unsupported_model_content", 415)
            expanded += info.file_size
            if (
                expanded > limits["expanded"]
                or info.file_size > limits["entry_bytes"]
                or info.file_size / max(1, info.compress_size) > limits["ratio"]
            ):
                raise InvalidModel("archive_expansion_limit")
            with archive.open(info) as source:
                data = source.read(limits["entry_bytes"] + 1)
                if len(data) != info.file_size or len(data) > limits["entry_bytes"]:
                    raise InvalidModel("archive_expansion_limit")
                content[name] = data  # Only three bounded XML parts; no extraction.
        if set(content) != allowed:
            raise InvalidModel("incomplete_3mf")
    relationships = xml(content["_rels/.rels"], REL, "Relationships")
    if len(relationships) != 1 or relationships.attrib:
        raise InvalidModel("unsupported_model_content", 415)
    relation = relationships[0]
    if (
        set(relation.attrib) - {"Id", "Type", "Target", "TargetMode"}
        or not relation.get("Id")
        or relation.tag != f"{{{REL}}}Relationship"
        or relation.get("Type") != MODEL_REL
        or relation.get("Target") not in {"/3D/3dmodel.model", "3D/3dmodel.model"}
        or relation.get("TargetMode", "Internal") != "Internal"
    ):
        raise InvalidModel("external_model_reference", 415)
    types = xml(content["[Content_Types].xml"], CONTENT, "Types")
    covered: set[str] = set()
    for child in types:
        if child.tag == f"{{{CONTENT}}}Override":
            if (
                child.get("PartName") != "/3D/3dmodel.model"
                or child.get("ContentType")
                != "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
            ):
                raise InvalidModel()
            covered.add("model")
        elif child.tag == f"{{{CONTENT}}}Default":
            if (child.get("Extension"), child.get("ContentType")) not in {
                ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
                ("model", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"),
            }:
                raise InvalidModel("unsupported_model_content", 415)
            covered.add(str(child.get("Extension")))
        else:
            raise InvalidModel()
    if not {"model", "rels"} <= covered:
        raise InvalidModel("incomplete_3mf")
    model = xml(content["3D/3dmodel.model"], CORE, "model")
    units = model.get("unit", "millimeter")
    if units not in {"micron", "millimeter", "centimeter", "inch", "foot", "meter"} or model.get(
        "requiredextensions"
    ):
        raise InvalidModel("unsupported_model_content", 415)
    xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
    structure = {
        "model": ({"metadata", "resources", "build"}, {"unit", "requiredextensions", xml_lang}),
        "resources": ({"object"}, set()),
        "object": ({"metadata", "mesh", "components"}, {"id", "type", "name", "partnumber"}),
        "mesh": ({"vertices", "triangles"}, set()),
        "vertices": ({"vertex"}, set()),
        "vertex": (set(), {"x", "y", "z"}),
        "triangles": ({"triangle"}, set()),
        "triangle": (set(), {"v1", "v2", "v3"}),
        "components": ({"component"}, set()),
        "component": (set(), {"objectid", "transform"}),
        "build": ({"item"}, set()),
        "item": (set(), {"objectid", "transform", "printable"}),
        "metadata": (set(), {"name", xml_lang}),
    }
    for element in model.iter():
        tag = element.tag.removeprefix(f"{{{CORE}}}")
        if element.tag != f"{{{CORE}}}{tag}" or tag not in structure:
            raise InvalidModel("unsupported_model_content", 415)
        children, attributes = structure[tag]
        if set(element.attrib) - attributes or any(
            child.tag not in {f"{{{CORE}}}{name}" for name in children} for child in element
        ):
            raise InvalidModel("unsupported_model_content", 415)
        if tag in {"model", "mesh", "object"}:
            child_names = [child.tag for child in element if child.tag != f"{{{CORE}}}metadata"]
            if len(child_names) != len(set(child_names)):
                raise InvalidModel()
        if tag != "metadata" and element.text and element.text.strip():
            raise InvalidModel()
        if any(child.tail and child.tail.strip() for child in element):
            raise InvalidModel()
        if tag == "object" and element.get("type", "model") not in {
            "model",
            "support",
            "solidsupport",
            "surface",
            "other",
        }:
            raise InvalidModel("unsupported_model_content", 415)
        transform = element.get("transform")
        if transform:
            values = transform.split()
            if len(values) != 12:
                raise InvalidModel()
            for value in values:
                finite(value)
    resources = model.find(f"{{{CORE}}}resources")
    build = model.find(f"{{{CORE}}}build")
    if resources is None or build is None or not len(build):
        raise InvalidModel()
    objects: dict[int, set[int]] = {}
    for obj in resources:
        if obj.tag != f"{{{CORE}}}object":
            raise InvalidModel()
        identity = int(obj.get("id", "0"))
        if identity <= 0 or identity in objects:
            raise InvalidModel()
        mesh = obj.find(f"{{{CORE}}}mesh")
        components = obj.find(f"{{{CORE}}}components")
        if (mesh is None) == (components is None):
            raise InvalidModel()
        references: set[int] = set()
        if mesh is not None:
            vertices = mesh.find(f"{{{CORE}}}vertices")
            triangles = mesh.find(f"{{{CORE}}}triangles")
            if vertices is None or triangles is None or len(vertices) < 3 or not len(triangles):
                raise InvalidModel()
            for vertex in vertices:
                for dimension in ["x", "y", "z"]:
                    finite(vertex.attrib[dimension])
            for triangle in triangles:
                indices = [int(triangle.attrib[key]) for key in ["v1", "v2", "v3"]]
                if len(set(indices)) != 3 or min(indices) < 0 or max(indices) >= len(vertices):
                    raise InvalidModel()
        else:
            assert components is not None
            if not len(components):
                raise InvalidModel()
            references = {int(component.attrib["objectid"]) for component in components}
        objects[identity] = references
    if not objects or len(objects) > 1000:
        raise InvalidModel("model_complexity_limit")

    def visit(identity: int, ancestors: set[int]) -> None:
        if identity not in objects or identity in ancestors or len(ancestors) > 32:
            raise InvalidModel()
        for child in objects[identity]:
            visit(child, ancestors | {identity})

    for identity in objects:
        visit(identity, set())
    for item in build:
        if item.tag != f"{{{CORE}}}item" or int(item.attrib["objectid"]) not in objects:
            raise InvalidModel()
    return {"format": "3mf", "mime": "model/3mf", "details": {"declared_unit": units}}


def inspect(handle: BinaryIO, size: int, limits: dict[str, int]) -> dict[str, Any]:
    prefix = handle.read(84)
    handle.seek(0)
    if prefix.startswith(b"PK"):
        return validate_3mf(handle, limits)
    if prefix.lstrip().startswith(b"solid") or (
        len(prefix) == 84 and size == 84 + 50 * struct.unpack("<I", prefix[80:84])[0]
    ):
        return validate_stl(handle, size)
    return validate_obj(handle)


async def validate_file(
    path: Path, limits: dict[str, int], timeout: int, cpu: int
) -> dict[str, Any]:
    # Isolated Python mode and an allowlisted environment prevent credential/
    # Python startup inheritance. Only trusted stdlib code reads model bytes.
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-B",
        str(Path(__file__).resolve()),
        str(path),
        json.dumps(limits),
        str(cpu),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env={"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"},
        close_fds=True,
    )
    try:
        output, _ = await asyncio.wait_for(child.communicate(), timeout)
    except BaseException:
        if child.returncode is None:
            child.kill()
        await child.wait()
        raise
    if child.returncode != 0 or len(output) > 4096:
        raise InvalidModel("validation_resource_limit")
    result: dict[str, Any] = json.loads(output)
    if result.get("error"):
        raise InvalidModel(result["error"], result.get("status", 422))
    return result


def main() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    cpu = int(sys.argv[3])
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    try:
        descriptor = os.open(sys.argv[1], os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as handle:
            result = inspect(handle, os.fstat(handle.fileno()).st_size, json.loads(sys.argv[2]))
    except InvalidModel as error:
        result = {"error": error.code, "status": error.status}
    except (
        ValueError,
        KeyError,
        OSError,
        ET.ParseError,
        zipfile.BadZipFile,
        RuntimeError,
        MemoryError,
        struct.error,
    ):
        result = {"error": "invalid_model", "status": 422}
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
