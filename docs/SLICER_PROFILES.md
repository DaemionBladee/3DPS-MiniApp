# M06 virtual profiles and estimate provenance

The registry represents assumptions about a generic **virtual** FDM machine,
not owned hardware: 220 × 220 × 250 mm, 0.4 mm nozzle, 1.75 mm filament, 15%
rectilinear infill, two perimeters and four top/bottom layers. Initial approved
simulation profiles pair PLA/PETG with standard 0.20 mm/fine 0.12 mm layers.
PLA density 1.24 g/cm³, nozzle/bed 205/60 °C; PETG 1.27 g/cm³, 235/80 °C.
Speed 40 mm/s, external perimeter 30 mm/s, first layer 20 mm/s, travel 100 mm/s,
retraction 1 mm at 30 mm/s. Supports are disabled. These values are conservative
test assumptions, not verified commercial capability, stock or calibration.

Profile content is immutable even before use; only activation can change. SQL
checks require approved, simulation-only, uncalibrated records. Numeric settings
are allowlisted and range checked; no arbitrary slicer INI, command, shell,
macro, start/end G-code or post-processing hook is accepted. Unknown material or
quality has no fallback. Selecting another revision never overwrites historical
runs. The backend requires matching material and quality, verified configuration
checksum and an available immutable worker image/executable.

## Engine pin and reproducibility

- Base: `python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df`.
- Debian PrusaSlicer: exact `2.5.0+dfsg-4`; native CLI reports `2.5.0+UNKNOWN`.
- The real installed CLI was inspected and exercised: `--help`, `--repair`,
  `--export-stl`, `--load`, `--config-compatibility disable`, `--center`,
  `--export-gcode`, `--output`, `--loglevel`. No assumed headless flag is used.
- Apt transitive libraries are not snapshot-pinned. Therefore source rebuilding
  is not claimed byte-identical. Each approved profile binds the **built image
  SHA-256 and native executable SHA-256**, plus exact engine version. The image
  retains `debian-packages.txt` for its package inventory. New builds require
  explicit new approval/version; execution never substitutes a mutable tag.
- Full configuration JSON, configuration SHA-256, virtual model ID, profile
  key/version, original file ID/SHA, item, frozen specification SHA/revision,
  task/lease identity and analyzer version are retained with immutable runs.
- PrusaSlicer implicitly repairs geometry when slicing. The worker first exports
  an explicitly repaired STL and compares face count and an order-independent,
  winding-preserving geometry signature at 0.00001 mm precision. Changed geometry
  routes to manual review instead of silently adopting repair. Original checksum
  and dimensions always remain attached. Normalization translates to zero origin;
  it does not fit-scale or reorient parts.
- The native timestamp header makes raw G-code hashes vary with time. Retain raw
  hash and a canonical hash excluding only that header. Regression fixtures check
  repeated grams, seconds and canonical checksum for a fixed model/profile.

## Meaning and limits of results

A result is a **Simulation estimate — not a final quotation.** Grams and duration
come from validated real PrusaSlicer output for a single model. Quantity is shown
separately; no packed batch or commercial total is inferred. Support material
breakdown is unavailable and represented by null/false, never invented zero.
No artifacts are retained or exposed for physical operation.

Geometry supports STL triangles, bounded OBJ triangles/convex planar polygons,
and permitted Core 3MF meshes/components/build transforms and declared units.
STL/OBJ require customer unit confirmation; optional three target dimensions in
mm and tolerance (default 0.5 mm) can additionally detect scale mismatch. 3MF
units must agree with confirmation. Oversized complexity, ambiguous unsupported
geometry, open/non-manifold/degenerate/duplicate/winding-invalid meshes, impossible
scale, dimension mismatch and virtual build-volume incompatibility fail closed or
require review. Volume is null for unreliable topology. Self-intersection,
structural strength, overhang/support feasibility, thermal behavior, tolerance,
material inventory and measured machine throughput are **not certified**.
Warnings stay visible and the printing-stage request remains in manual review.

M07 may consume only current successful results matching every request/file/profile
provenance field. It must independently evaluate eligibility and costs; uncalibrated
simulation runs cannot authorize live quotations, checkout, payment or production.
Real printer calibration, security verification on the target host and explicit
release approvals remain prerequisites for any later live behavior.
