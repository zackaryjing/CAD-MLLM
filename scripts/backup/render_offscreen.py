#!/usr/bin/env python3
"""
render_offscreen.py
Headless renderer: STEP -> 8-view grayscale hidden-line (hard-edge) images.

Usage example:
  conda activate deepcad
  python render_offscreen.py --src datasets/Omni-CAD/json_step --out datasets/Omni-CAD/test-img --num 6 --size 224

Outputs saved as: <out>/<basename>_view_000.png ... _view_007.png
"""
import os
import sys
import glob
import argparse
from math import acos, pi
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw
from tqdm import tqdm

# --- Try to import pythonocc (may be installed as pythonocc-core) ---
try:
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopoDS import topods
    from OCC.Core.Poly import Poly_Triangle
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.gp import gp_Trsf
    from OCC.Core.gp import gp_Pnt
except Exception as e:
    print("ERROR: pythonocc-core import failed:", e, file=sys.stderr)
    print("Install with: conda install -c conda-forge pythonocc-core", file=sys.stderr)
    raise

# ---------- Utility: filesystem ----------
def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

# ---------- STEP -> triangle mesh extraction ----------
def step_to_triangles(step_path, mesh_deflection=0.5):
    """
    Read STEP file and return vertices (Nx3) and triangles (Mx3 indices).
    mesh_deflection: smaller -> finer mesh. Tune for accuracy/size.
    """
    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != 1:
        raise RuntimeError(f"STEP read failed for {step_path} (status {status})")
    reader.TransferRoots()
    shape = reader.Shape()

    # mesh the whole shape
    BRepMesh_IncrementalMesh(shape, mesh_deflection)

    # collect nodes and triangles
    vertices = []
    triangles = []
    # To avoid duplicate vertices, map gp_Pnt coords to index with small tolerance
    vert_map = dict()
    tol = 1e-9
    def add_vertex(p):
        key = (round(p.X(), 9), round(p.Y(), 9), round(p.Z(), 9))
        idx = vert_map.get(key)
        if idx is None:
            idx = len(vertices)
            vertices.append([p.X(), p.Y(), p.Z()])
            vert_map[key] = idx
        return idx

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    face_index = 0
    while exp.More():
        face = topods.Face(exp.Current())
        # get triangulation and location
        loc = TopLoc_Location()
        try:
            tri = BRep_Tool.Triangulation(face, loc)
        except Exception:
            tri = None
        if tri is not None:
            # apply location transform if any
            # tri.Nodes() is 1..NbNodes
            nb_nodes = tri.NbNodes()
            for ni in range(1, nb_nodes + 1):
                p = tri.Node(ni)
                # transform by 'loc' to global coords if location not identity
                try:
                    trsf = loc.Transformation()
                    p = p.Transformed(trsf)
                except Exception:
                    pass
                add_vertex(p)
            # triangles: tri.Triangles() is 1..NbTriangles
            nb_tris = tri.NbTriangles()
            for ti in range(1, nb_tris + 1):
                poly_tri = tri.Triangle(ti)
                # get vertex indices (1-based)
                try:
                    (i1, i2, i3) = poly_tri.Get()
                except Exception:
                    # fallback API
                    a = poly_tri.GetABC()
                    i1, i2, i3 = a[0], a[1], a[2]
                # map to global indices
                p1 = tri.Node(i1); p2 = tri.Node(i2); p3 = tri.Node(i3)
                try:
                    trsf = loc.Transformation()
                    p1, p2, p3 = p1.Transformed(trsf), p2.Transformed(trsf), p3.Transformed(trsf)
                except Exception:
                    pass
                idx1 = add_vertex(p1)
                idx2 = add_vertex(p2)
                idx3 = add_vertex(p3)
                triangles.append((idx1, idx2, idx3))
        exp.Next()
        face_index += 1

    if len(vertices) == 0 or len(triangles) == 0:
        raise RuntimeError(f"No triangulation found for {step_path}. Try smaller deflection (finer mesh).")

    V = np.array(vertices, dtype=np.float64)
    F = np.array(triangles, dtype=np.int64)
    return V, F

# ---------- Geometry helpers ----------
def normalize(v):
    n = np.linalg.norm(v)
    return v / (n + 1e-12)

def compute_face_normals(V, F):
    tris = V[F]  # (M,3,3)
    v0 = tris[:,1] - tris[:,0]
    v1 = tris[:,2] - tris[:,0]
    normals = np.cross(v0, v1)
    norms = np.linalg.norm(normals, axis=1)
    nonzero = norms > 0
    normals[nonzero] /= norms[nonzero][:,None]
    normals[~nonzero] = np.array([0.0,0.0,1.0])
    return normals

# ---------- Simple rasterizer (orthographic) ----------
def render_views(V, F, out_base, size=224, views=None, light_dir=None, edge_angle_deg=30):
    """
    Render multiple orthographic views.
    views: list of view direction vectors (camera pointing direction)
    light_dir: lighting direction for diffuse shading (same space)
    """
    ensure_dir(os.path.dirname(out_base) or ".")

    # center & scale model to fit into [-1,1]^3
    centroid = V.mean(axis=0)
    Vc = V - centroid
    max_extent = np.max(np.linalg.norm(Vc, axis=1))
    if max_extent == 0:
        max_extent = 1.0
    Vn = Vc / (max_extent * 1.05)  # small padding

    if views is None:
        # 8 sign combinations of (1,1,1)
        views = []
        base = np.array([1.0, 1.0, 1.0])
        for i in range(8):
            v = base.copy()
            if (i & 1) != 0:
                v[0] *= -1
            if (i & 2) != 0:
                v[1] *= -1
            if (i & 4) != 0:
                v[2] *= -1
            views.append(normalize(v))

    if light_dir is None:
        light_dir = normalize(np.array([1.0, 1.0, 2.0]))

    # Precompute face normals & triangle centers
    face_normals = compute_face_normals(Vn, F)
    face_centers = Vn[F].mean(axis=1)

    # Build adjacency for edge detection: map undirected edge -> list of face indices
    edge_faces = defaultdict(list)
    for fi, tri in enumerate(F):
        for a,b in ((tri[0],tri[1]), (tri[1],tri[2]), (tri[2],tri[0])):
            key = (min(a,b), max(a,b))
            edge_faces[key].append(fi)

    # For each view, render
    H = W = size
    for vidx, view_dir in enumerate(views):
        # choose an 'up' vector robustly
        up = np.array([0.0, 0.0, 1.0])
        if abs(np.dot(up, view_dir)) > 0.9:
            up = np.array([0.0, 1.0, 0.0])
        # compute right = up x view, then true_up = view x right
        right = normalize(np.cross(up, view_dir))
        true_up = normalize(np.cross(view_dir, right))

        # Build camera space basis: origin at (0,0,0), axes: right (x), true_up (y), -view_dir (z into screen)
        R = np.vstack([right, true_up, -view_dir]).T  # 3x3, world -> camera

        # Transform vertices into camera coords
        Vcam = (R.T @ Vn.T).T  # (N,3) where z is depth (positive into camera)
        # orthographic projection: drop z, map x,y to image coords
        # image coords: u = (x*0.5 + 0.5) * (W-1), v = (1 - (y*0.5 + 0.5)) * (H-1)
        xs = Vcam[:,0]
        ys = Vcam[:,1]
        us = (xs * 0.5 + 0.5) * (W - 1)
        vs = (1.0 - (ys * 0.5 + 0.5)) * (H - 1)
        verts2d = np.vstack([us, vs, Vcam[:,2]]).T  # (N,3): (u,v,z)

        # z-buffer init
        zbuf = np.full((H, W), np.inf, dtype=np.float64)
        img = np.full((H, W), 255, dtype=np.uint8)  # white background

        # shading params
        ambient = 0.2
        diffuse_k = 0.8

        # rasterize triangles one by one (simple bounding-box barycentric raster)
        for fi, tri in enumerate(F):
            idx0, idx1, idx2 = tri
            p0 = verts2d[idx0]; p1 = verts2d[idx1]; p2 = verts2d[idx2]
            # 2D coordinates and depths
            x0,y0,z0 = p0
            x1,y1,z1 = p1
            x2,y2,z2 = p2
            # bbox
            minx = int(max(min(x0,x1,x2)//1, 0))
            maxx = int(min(np.ceil(max(x0,x1,x2)), W-1))
            miny = int(max(min(y0,y1,y2)//1, 0))
            maxy = int(min(np.ceil(max(y0,y1,y2)), H-1))
            if maxx < 0 or maxy < 0 or minx >= W or miny >= H:
                continue

            # compute triangle area in 2D
            denom = ( (y1 - y2)*(x0 - x2) + (x2 - x1)*(y0 - y2) )
            if abs(denom) < 1e-8:
                continue
            # shading intensity
            n = face_normals[fi]
            intensity = ambient + diffuse_k * max(0.0, np.dot(n, normalize(light_dir)))
            intensity = np.clip(intensity, 0.0, 1.0)
            gray = int(255 * (1.0 - intensity))  # object darker when intensity higher

            for yy in range(miny, maxy+1):
                for xx in range(minx, maxx+1):
                    # barycentric
                    w0 = ((y1 - y2)*(xx - x2) + (x2 - x1)*(yy - y2)) / (denom + 1e-20)
                    w1 = ((y2 - y0)*(xx - x2) + (x0 - x2)*(yy - y2)) / (denom + 1e-20)
                    w2 = 1 - w0 - w1
                    if (w0 >= -1e-6) and (w1 >= -1e-6) and (w2 >= -1e-6):
                        depth = w0*z0 + w1*z1 + w2*z2
                        if depth < zbuf[yy, xx]:
                            zbuf[yy, xx] = depth
                            img[yy, xx] = gray

        # After filled render, draw hard edges where adjacent faces have dihedral angle > threshold
        edge_img = Image.fromarray(img, mode='L')
        draw = ImageDraw.Draw(edge_img)
        angle_thresh = (edge_angle_deg / 180.0) * pi

        # precompute face normals per face in camera space? we already have world normals; dihedral depends on face normals in world coords
        for (a,b), faces in edge_faces.items():
            # if boundary edge (only one adjacent face) -> always draw
            draw_edge = False
            if len(faces) == 1:
                draw_edge = True
            elif len(faces) == 2:
                n1 = face_normals[faces[0]]
                n2 = face_normals[faces[1]]
                # angle between normals
                cosang = np.dot(n1, n2)
                cosang = np.clip(cosang, -1.0, 1.0)
                ang = acos(cosang)
                if ang > angle_thresh:
                    draw_edge = True
            else:
                # more than 2 faces (rare) -> draw conservatively
                draw_edge = True

            if draw_edge:
                pA = verts2d[a]; pB = verts2d[b]
                xA, yA = pA[0], pA[1]
                xB, yB = pB[0], pB[1]
                # Draw thin black line. Use integer coordinates
                draw.line([(xA, yA), (xB, yB)], fill=0, width=1)

        # Save image
        out_path = f"{out_base}_view_{vidx:03d}.png"
        edge_img.save(out_path)

# ---------- Main: CLI ----------
def find_step_files(src_dir):
    patterns = ["**/*.step", "**/*.STEP", "**/*.stp", "**/*.STP"]
    files = []
    for p in patterns:
        files.extend(glob.glob(os.path.join(src_dir, p), recursive=True))
    files = sorted(files)
    return files

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', required=True, help="source folder containing .step files (recursive)")
    parser.add_argument('--out', required=False, default="datasets/Omni-CAD/test-img", help="output folder for images")
    parser.add_argument('--idx', type=int, default=0, help="start index (for selection)")
    parser.add_argument('--num', type=int, default=6, help="number of shapes to render (-1 => all)")
    parser.add_argument('--size', type=int, default=224, help="image size (square)")
    parser.add_argument('--deflection', type=float, default=0.5, help="mesh deflection for BRepMesh (smaller -> finer)")
    args = parser.parse_args()

    ensure_dir(args.out)

    all_steps = find_step_files(args.src)
    if len(all_steps) == 0:
        print("No STEP files found under", args.src)
        return

    if args.num != -1:
        selected = all_steps[args.idx: args.idx + args.num]
    else:
        selected = all_steps[args.idx:]

    print(f"Found {len(all_steps)} .step files, rendering {len(selected)} into {args.out} ...")

    for path in tqdm(selected):
        try:
            V, F = step_to_triangles(path, mesh_deflection=args.deflection)
        except Exception as e:
            print(f"Skipping {path}: {e}", file=sys.stderr)
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        out_base = os.path.join(args.out, base)
        try:
            render_views(V, F, out_base, size=args.size)
        except Exception as e:
            print(f"Render failed for {path}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
