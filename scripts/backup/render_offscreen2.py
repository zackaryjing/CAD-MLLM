#!/usr/bin/env python3
"""
render_offscreen2.py

Headless STEP renderer for CAD-MLLM style multi-view images:
- grayscale
- no texture
- hidden-line / hard-edge style
- 8 fixed corner views

Default output is for testing:
  datasets/Omni-CAD/test-img
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, List

import numpy as np
from PIL import Image

pv = None
BRep_Tool = None
BRepMesh_IncrementalMesh = None
IFSelect_RetDone = None
STEPControl_Reader = None
TopAbs_FACE = None
TopAbs_REVERSED = None
TopExp_Explorer = None
TopLoc_Location = None
topods = None


def import_backends() -> None:
    global pv
    global BRep_Tool
    global BRepMesh_IncrementalMesh
    global IFSelect_RetDone
    global STEPControl_Reader
    global TopAbs_FACE
    global TopAbs_REVERSED
    global TopExp_Explorer
    global TopLoc_Location
    global topods

    try:
        import pyvista as _pv

        pv = _pv
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "pyvista import failed. Install in conda env: "
            "conda install -c conda-forge pyvista vtk"
        ) from exc

    try:
        from OCC.Core.BRep import BRep_Tool as _BRep_Tool
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh as _BRepMesh_IncrementalMesh
        from OCC.Core.IFSelect import IFSelect_RetDone as _IFSelect_RetDone
        from OCC.Core.STEPControl import STEPControl_Reader as _STEPControl_Reader
        from OCC.Core.TopAbs import TopAbs_FACE as _TopAbs_FACE
        from OCC.Core.TopAbs import TopAbs_REVERSED as _TopAbs_REVERSED
        from OCC.Core.TopExp import TopExp_Explorer as _TopExp_Explorer
        from OCC.Core.TopLoc import TopLoc_Location as _TopLoc_Location
        from OCC.Core.TopoDS import topods as _topods

        BRep_Tool = _BRep_Tool
        BRepMesh_IncrementalMesh = _BRepMesh_IncrementalMesh
        IFSelect_RetDone = _IFSelect_RetDone
        STEPControl_Reader = _STEPControl_Reader
        TopAbs_FACE = _TopAbs_FACE
        TopAbs_REVERSED = _TopAbs_REVERSED
        TopExp_Explorer = _TopExp_Explorer
        TopLoc_Location = _TopLoc_Location
        topods = _topods
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "pythonocc-core import failed. Install in conda env: "
            "conda install -c conda-forge pythonocc-core"
        ) from exc


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def maybe_start_xvfb() -> None:
    os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

    # If DISPLAY is unavailable on Linux, try Xvfb.
    if os.name == "nt":
        return
    if os.environ.get("DISPLAY"):
        return
    try:
        pv.start_xvfb(wait=0.1)
        print("[INFO] DISPLAY not found. Started Xvfb for offscreen rendering.")
    except Exception as exc:
        print(
            "[WARN] DISPLAY not found and Xvfb start failed. "
            "Will continue and rely on EGL/OSMesa-enabled VTK.",
            file=sys.stderr,
        )
        print(f"[WARN] Xvfb details: {exc}", file=sys.stderr)


def find_step_files(src_dir: Path) -> List[Path]:
    patterns = ("**/*.step", "**/*.stp", "**/*.STEP", "**/*.STP")
    files: List[Path] = []
    for pattern in patterns:
        files.extend(src_dir.glob(pattern))

    # Deduplicate in case the filesystem is case-insensitive.
    dedup = {}
    for path in files:
        dedup[str(path).lower()] = path
    return sorted(dedup.values(), key=lambda p: str(p))


def read_step_shape(step_file: Path):
    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_file))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"ReadFile failed with status={status}")

    transferred = reader.TransferRoots()
    if transferred == 0:
        raise RuntimeError("TransferRoots returned 0")

    shape = reader.Shape()
    if shape.IsNull():
        raise RuntimeError("Loaded shape is null")
    return shape


def shape_to_polydata(shape, linear_deflection: float, angular_deflection: float) -> pv.PolyData:
    # OCC meshing: smaller deflection -> finer tessellation.
    BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)

    points = []
    faces = []

    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        loc = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, loc)
        if triangulation is None:
            explorer.Next()
            continue

        trsf = loc.Transformation()
        node_offset = len(points)

        num_nodes = triangulation.NbNodes()
        for node_idx in range(1, num_nodes + 1):
            pnt = triangulation.Node(node_idx).Transformed(trsf)
            points.append((pnt.X(), pnt.Y(), pnt.Z()))

        reversed_face = face.Orientation() == TopAbs_REVERSED
        num_triangles = triangulation.NbTriangles()
        for tri_idx in range(1, num_triangles + 1):
            tri = triangulation.Triangle(tri_idx)
            n1, n2, n3 = tri.Get()
            if reversed_face:
                n2, n3 = n3, n2
            faces.extend((3, node_offset + n1 - 1, node_offset + n2 - 1, node_offset + n3 - 1))

        explorer.Next()

    if not points or not faces:
        raise RuntimeError("No triangulation extracted from STEP shape")

    poly = pv.PolyData(np.asarray(points, dtype=np.float64), np.asarray(faces, dtype=np.int64))
    if poly.n_cells == 0:
        raise RuntimeError("Generated mesh has zero cells")
    return poly


def normalize_mesh(mesh: pv.PolyData) -> pv.PolyData:
    out = mesh.copy(deep=True)
    pts = np.asarray(out.points, dtype=np.float64)
    mins = pts.min(axis=0)
    maxs = pts.max(axis=0)
    center = 0.5 * (mins + maxs)
    diag = float(np.linalg.norm(maxs - mins))
    if diag < 1e-12:
        raise RuntimeError("Degenerate geometry (diagonal is near zero)")

    scale = 2.0 / diag
    out.points = (pts - center) * scale
    return out


def corner_view_directions() -> List[np.ndarray]:
    base = np.array([1.0, 1.0, 1.0], dtype=np.float64)
    dirs = []
    for i in range(8):
        vec = base.copy()
        if i & 1:
            vec[0] *= -1.0
        if i & 2:
            vec[1] *= -1.0
        if i & 4:
            vec[2] *= -1.0
        vec /= np.linalg.norm(vec)
        dirs.append(vec)
    return dirs


def camera_basis(view_dir: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    world_up = np.array([0.0, 0.0, 1.0], dtype=np.float64)
    if abs(float(np.dot(world_up, view_dir))) > 0.98:
        world_up = np.array([0.0, 1.0, 0.0], dtype=np.float64)

    right = np.cross(world_up, view_dir)
    right /= np.linalg.norm(right) + 1e-12
    true_up = np.cross(view_dir, right)
    true_up /= np.linalg.norm(true_up) + 1e-12
    return right, true_up


def compute_parallel_scale(points: np.ndarray, right: np.ndarray, up: np.ndarray, margin: float = 1.08) -> float:
    x = points @ right
    y = points @ up
    half_extent = max(float(np.max(np.abs(x))), float(np.max(np.abs(y))), 1e-6)
    return half_extent * margin


def render_eight_views(
    mesh: pv.PolyData,
    out_prefix: Path,
    size: int,
    edge_angle: float,
    line_width: float,
    gray: float,
) -> None:
    ensure_dir(out_prefix.parent)
    gray = float(np.clip(gray, 0.0, 1.0))

    plotter = pv.Plotter(off_screen=True, window_size=(size, size))
    plotter.set_background("white")
    try:
        plotter.enable_anti_aliasing("ssaa")
    except Exception:
        try:
            plotter.enable_anti_aliasing()
        except Exception:
            pass

    # Monochrome surface (no texture).
    plotter.add_mesh(
        mesh,
        color=(gray, gray, gray),
        smooth_shading=False,
        lighting=True,
        ambient=0.25,
        diffuse=0.75,
        specular=0.0,
    )

    # Hard-edge lines from geometric features.
    edge_mesh = mesh.extract_feature_edges(
        boundary_edges=True,
        feature_edges=True,
        manifold_edges=False,
        non_manifold_edges=True,
        feature_angle=edge_angle,
    )
    if edge_mesh.n_cells > 0:
        plotter.add_mesh(edge_mesh, color="black", line_width=line_width, lighting=False)

    points = np.asarray(mesh.points, dtype=np.float64)
    view_dirs = corner_view_directions()
    cam_dist = 5.0

    for vidx, view_dir in enumerate(view_dirs):
        right, up = camera_basis(view_dir)
        parallel_scale = compute_parallel_scale(points, right, up, margin=1.08)

        plotter.camera.position = tuple((view_dir * cam_dist).tolist())
        plotter.camera.focal_point = (0.0, 0.0, 0.0)
        plotter.camera.up = tuple(up.tolist())
        plotter.camera.parallel_projection = True
        plotter.camera.parallel_scale = parallel_scale

        rgb = plotter.screenshot(return_img=True)
        img = Image.fromarray(rgb).convert("L")
        out_file = out_prefix.parent / f"{out_prefix.name}_view_{vidx:03d}.png"
        img.save(out_file)

    plotter.close()


def select_files(files: List[Path], idx: int, num: int) -> Iterable[Path]:
    if idx < 0:
        idx = 0
    if num == -1:
        return files[idx:]
    return files[idx : idx + max(num, 0)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Headless STEP -> 8-view grayscale renderer")
    parser.add_argument(
        "--src",
        type=str,
        default="datasets/Omni-CAD/json_step",
        help="source directory (recursive search for STEP files)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="datasets/Omni-CAD/test-img",
        help="output root directory",
    )
    parser.add_argument("--idx", type=int, default=0, help="start index in sorted STEP file list")
    parser.add_argument(
        "--num",
        type=int,
        default=6,
        help="number of files to render for test; -1 means all",
    )
    parser.add_argument("--size", type=int, default=224, help="output image size (square)")
    parser.add_argument(
        "--lin-defl",
        type=float,
        default=0.20,
        help="OCC linear deflection for triangulation (smaller = finer mesh)",
    )
    parser.add_argument(
        "--ang-defl",
        type=float,
        default=0.50,
        help="OCC angular deflection for triangulation (radians)",
    )
    parser.add_argument(
        "--edge-angle",
        type=float,
        default=35.0,
        help="feature-edge threshold angle in degrees",
    )
    parser.add_argument("--line-width", type=float, default=1.6, help="rendered edge line width")
    parser.add_argument(
        "--gray",
        type=float,
        default=0.78,
        help="surface gray level in [0,1], where 0 is black and 1 is white",
    )
    parser.add_argument(
        "--no-xvfb",
        action="store_true",
        help="do not try to start Xvfb when DISPLAY is missing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import_backends()

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    if not src.exists():
        print(f"[ERROR] src does not exist: {src}", file=sys.stderr)
        return 1
    ensure_dir(out)

    if not args.no_xvfb:
        maybe_start_xvfb()

    files = find_step_files(src)
    if not files:
        print(f"[ERROR] no STEP files found under: {src}", file=sys.stderr)
        return 1

    selected = list(select_files(files, args.idx, args.num))
    print(f"[INFO] total STEP files: {len(files)}")
    print(f"[INFO] selected for rendering: {len(selected)}")
    print(f"[INFO] output root: {out}")

    ok_count = 0
    for step_file in selected:
        rel_dir = step_file.parent.relative_to(src)
        out_dir = out / rel_dir
        ensure_dir(out_dir)
        out_prefix = out_dir / step_file.stem

        try:
            shape = read_step_shape(step_file)
            mesh = shape_to_polydata(shape, linear_deflection=args.lin_defl, angular_deflection=args.ang_defl)
            mesh = normalize_mesh(mesh)
            render_eight_views(
                mesh=mesh,
                out_prefix=out_prefix,
                size=args.size,
                edge_angle=args.edge_angle,
                line_width=args.line_width,
                gray=args.gray,
            )
            ok_count += 1
            print(f"[OK] {step_file}")
        except Exception as exc:
            print(f"[WARN] failed: {step_file}", file=sys.stderr)
            print(f"       reason: {exc}", file=sys.stderr)

    print(f"[DONE] successfully rendered {ok_count}/{len(selected)} STEP files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
