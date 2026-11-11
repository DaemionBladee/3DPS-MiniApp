"""Small synthetic geometry; no user/customer model files in the repository."""

import io
import struct
import zipfile

BINARY_STL = b"Synthetic M04 fixture".ljust(80, b" ") + struct.pack(
    "<I12fH", 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0
)
ASCII_STL = b"solid triangle\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid triangle\n"
OBJ = b"# synthetic triangle\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
MODEL_XML = b"""<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter"><resources><object id="1" type="model"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources><build><item objectid="1"/></build></model>"""
RELS = b"""<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" Target="/3D/3dmodel.model"/></Relationships>"""
TYPES = b"""<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/3D/3dmodel.model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>"""


def three_mf(parts: dict[str, bytes] | None = None) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in (
            parts
            or {"[Content_Types].xml": TYPES, "_rels/.rels": RELS, "3D/3dmodel.model": MODEL_XML}
        ).items():
            archive.writestr(name, data)
    return output.getvalue()


COMPLETE_SPEC = {
    "description": "Test model",
    "quantity": 2,
    "material_key": "dev-pla",
    "color_key": "dev-white",
    "quality_key": "dev-standard",
    "unit_key": "mm",
    "unit_confirmed": True,
    "special_requirements": "",
}
