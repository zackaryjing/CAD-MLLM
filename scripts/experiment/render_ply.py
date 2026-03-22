import open3d as o3d
import numpy as np
from PIL import Image

SIZE = 224

def normalize(mesh):
    bbox = mesh.get_axis_aligned_bounding_box()
    center = bbox.get_center()
    scale = 1.0 / np.max(bbox.get_extent())
    mesh.translate(-center)
    mesh.scale(scale * 1.6, center=[0,0,0])  # 约80%画面
    return mesh

def edge_lines(mesh):
    edges = set()
    tris = np.asarray(mesh.triangles)
    for t in tris:
        edges.add(tuple(sorted((t[0],t[1]))))
        edges.add(tuple(sorted((t[1],t[2]))))
        edges.add(tuple(sorted((t[0],t[2]))))
    edges = np.array(list(edges))
    line = o3d.geometry.LineSet()
    line.points = mesh.vertices
    line.lines = o3d.utility.Vector2iVector(edges)
    return line

def render_views(mesh):

    renderer = o3d.visualization.rendering.OffscreenRenderer(SIZE, SIZE)

    mat = o3d.visualization.rendering.MaterialRecord()
    mat.shader = "defaultLit"
    mat.base_color = (0.7,0.7,0.7,1)

    renderer.scene.add_geometry("mesh", mesh, mat)

    line = edge_lines(mesh)

    lmat = o3d.visualization.rendering.MaterialRecord()
    lmat.shader = "unlitLine"
    lmat.line_width = 1

    renderer.scene.add_geometry("edge", line, lmat)

    renderer.scene.scene.enable_sun_light(False)
    renderer.scene.scene.enable_indirect_light(True)

    cams = [
        (1,1,1),(1,1,-1),(1,-1,1),(1,-1,-1),
        (-1,1,1),(-1,1,-1),(-1,-1,1),(-1,-1,-1)
    ]

    images = []

    for c in cams:

        eye = np.array(c)*2.5
        center = np.array([0,0,0])
        up = [0,0,1]

        renderer.scene.camera.look_at(center, eye, up)

        img = renderer.render_to_image()
        img = np.asarray(img)

        gray = np.mean(img[:,:,:3],axis=2).astype(np.uint8)

        images.append(gray)

    return images


def stitch(imgs):

    rows = []
    for i in range(0,8,4):
        rows.append(np.concatenate(imgs[i:i+4],axis=1))
    return np.concatenate(rows,axis=0)


mesh = o3d.io.read_triangle_mesh("test.ply")
mesh.compute_vertex_normals()

mesh = normalize(mesh)

imgs = render_views(mesh)

final = stitch(imgs)

Image.fromarray(final).save("ply_views.png")
