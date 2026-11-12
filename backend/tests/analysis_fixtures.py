"""Synthetic closed cube generated in memory, never a customer model."""

import struct

from tests.model_fixtures import RELS, TYPES, three_mf

POINTS = [
    (0, 0, 0),
    (20, 0, 0),
    (20, 20, 0),
    (0, 20, 0),
    (0, 0, 20),
    (20, 0, 20),
    (20, 20, 20),
    (0, 20, 20),
]
FACES = [
    (0, 2, 1),
    (0, 3, 2),
    (4, 5, 6),
    (4, 6, 7),
    (0, 1, 5),
    (0, 5, 4),
    (1, 2, 6),
    (1, 6, 5),
    (2, 3, 7),
    (2, 7, 6),
    (3, 0, 4),
    (3, 4, 7),
]


def cube(kind="stl", faces=None):
    faces = FACES if faces is None else faces
    if kind == "stl":
        return (
            b"Synthetic M06 cube".ljust(80, b" ")
            + struct.pack("<I", len(faces))
            + b"".join(
                struct.pack("<12fH", 0, 0, 0, *[v for i in face for v in POINTS[i]], 0)
                for face in faces
            )
        )
    if kind == "obj":
        return (
            "\n".join("v " + " ".join(map(str, p)) for p in POINTS)
            + "\n"
            + "\n".join("f " + " ".join(str(i + 1) for i in face) for face in faces)
            + "\n"
        ).encode()
    xml = (
        '<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter"><resources><object id="1" type="model"><mesh><vertices>'
        + "".join(f'<vertex x="{p[0]}" y="{p[1]}" z="{p[2]}"/>' for p in POINTS)
        + "</vertices><triangles>"
        + "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
        + '</triangles></mesh></object></resources><build><item objectid="1"/></build></model>'
    ).encode()
    return three_mf({"[Content_Types].xml": TYPES, "_rels/.rels": RELS, "3D/3dmodel.model": xml})
