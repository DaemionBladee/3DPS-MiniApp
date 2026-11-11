import io
import math
import struct
import zipfile

import pytest

from app.intake.validation import InvalidModel, inspect
from tests.model_fixtures import ASCII_STL, BINARY_STL, MODEL_XML, OBJ, RELS, TYPES, three_mf

LIMITS = {"entries": 64, "expanded": 64 * 1024**2, "entry_bytes": 16 * 1024**2, "ratio": 100}


@pytest.mark.parametrize(
    "data,kind",
    [
        (BINARY_STL, "stl"),
        (ASCII_STL, "stl"),
        (OBJ, "obj"),
        (three_mf(), "3mf"),
        (OBJ.replace(b"f 1 2 3", b"f -3 -2 -1"), "obj"),
        (b"solid binary".ljust(80, b" ") + BINARY_STL[80:], "stl"),
    ],
)
def test_valid_structure_without_claiming_geometry_analysis(data: bytes, kind: str) -> None:
    result = inspect(io.BytesIO(data), len(data), LIMITS)
    assert result["format"] == kind
    assert "volume" not in result and "cost" not in result


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"<html>not a model</html>",
        BINARY_STL[:-1],
        ASCII_STL.replace(b"endfacet", b""),
        ASCII_STL.replace(b"vertex 1 0 0", b"vertex nan 0 0"),
        ASCII_STL + b"print malicious",
        OBJ.replace(b"f 1 2 3", b"f 0 2 3"),
        OBJ.replace(b"f 1 2 3", b"f 1 2 999"),
        OBJ + b"mtllib materials.mtl\n",
        OBJ + b"usemtl remote\n",
        OBJ + b"call /etc/passwd\n",
        OBJ + b"csh curl example.invalid\n",
        OBJ + b"curv 1 2 3\n",
        b"v " + b"1" * 20000,
        BINARY_STL[:84] + struct.pack("<12fH", math.inf, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0),
    ],
)
def test_malformed_or_external_models_fail_closed(data: bytes) -> None:
    with pytest.raises((InvalidModel, ValueError, UnicodeError)):
        inspect(io.BytesIO(data), len(data), LIMITS)


@pytest.mark.parametrize(
    "path",
    ["../escape", "/absolute", "3D/../bad", "3D\\escape", "C:/escape", "3D//bad", "nested.zip"],
)
def test_3mf_paths_and_nested_payloads_rejected(path: str) -> None:
    data = three_mf({path: b"unsafe"})
    with pytest.raises(InvalidModel):
        inspect(io.BytesIO(data), len(data), LIMITS)


@pytest.mark.parametrize(
    "parts",
    [
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS.replace(b"/3D/3dmodel.model", b"https://external.invalid/model"),
            "3D/3dmodel.model": MODEL_XML,
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS.replace(b'Id="r1"', b'Id="r1" TargetMode="External"'),
            "3D/3dmodel.model": MODEL_XML,
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": b'<!DOCTYPE model [<!ENTITY attack "explosion">]>' + MODEL_XML,
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML.replace(b'v3="2"', b'v3="900"'),
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML.replace(b"<vertex x=", b"<triangle x="),
        },
        {
            "[Content_Types].xml": TYPES,
            "_rels/.rels": RELS,
            "3D/3dmodel.model": MODEL_XML,
            "Metadata/image.png": b"not-supported",
        },
    ],
)
def test_3mf_references_entities_and_invalid_meshes_rejected(parts: dict[str, bytes]) -> None:
    data = three_mf(parts)
    with pytest.raises((InvalidModel, ValueError)):
        inspect(io.BytesIO(data), len(data), LIMITS)


@pytest.mark.parametrize(
    "limits",
    [
        {**LIMITS, "entries": 2},
        {**LIMITS, "expanded": 100},
        {**LIMITS, "entry_bytes": 100},
        {**LIMITS, "ratio": 1},
    ],
)
def test_archive_limits_enforced(limits: dict[str, int]) -> None:
    data = three_mf()
    with pytest.raises(InvalidModel):
        inspect(io.BytesIO(data), len(data), limits)


def test_archive_symlinks_duplicates_and_crc_failures() -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entry = zipfile.ZipInfo("3D/3dmodel.model")
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        archive.writestr(entry, b"../../secret")
    with pytest.raises(InvalidModel):
        inspect(io.BytesIO(output.getvalue()), len(output.getvalue()), LIMITS)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("3D/3dmodel.model", MODEL_XML)
        archive.writestr("3d/3DMODEL.MODEL", MODEL_XML)
    with pytest.raises(InvalidModel):
        inspect(io.BytesIO(output.getvalue()), len(output.getvalue()), LIMITS)
    broken = three_mf()[:-10]
    with pytest.raises((InvalidModel, zipfile.BadZipFile)):
        inspect(io.BytesIO(broken), len(broken), LIMITS)
