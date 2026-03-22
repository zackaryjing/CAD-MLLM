# render_blender36.py

import bpy
import os
import mathutils

# -----------------
# reset scene
# -----------------
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene

# -----------------
# create world
# -----------------
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True

bg = world.node_tree.nodes["Background"]
bg.inputs[0].default_value = (1,1,1,1)
bg.inputs[1].default_value = 1.0

# -----------------
# import mesh
# -----------------
path = os.path.join(os.getcwd(),"test.ply")
bpy.ops.import_mesh.ply(filepath=path)

obj = bpy.context.selected_objects[0]

# -----------------
# center object
# -----------------
bpy.context.view_layer.update()

bbox = [obj.matrix_world @ mathutils.Vector(v) for v in obj.bound_box]
center = sum(bbox, mathutils.Vector()) / 8
obj.location -= center

# -----------------
# scale object
# -----------------
dims = obj.dimensions
scale = 1.25 / max(dims)
obj.scale = (scale,scale,scale)

# -----------------
# material
# -----------------
mat = bpy.data.materials.new("mat")
mat.use_nodes = True

nodes = mat.node_tree.nodes
for n in nodes:
    nodes.remove(n)

out = nodes.new("ShaderNodeOutputMaterial")
diff = nodes.new("ShaderNodeBsdfDiffuse")

diff.inputs[0].default_value = (0.5,0.5,0.5,1)

mat.node_tree.links.new(diff.outputs[0],out.inputs[0])

obj.data.materials.append(mat)

# -----------------
# camera
# -----------------
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam",cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

def look_at(cam,target):
    direction = target - cam.location
    rot = direction.to_track_quat('-Z','Y')
    cam.rotation_euler = rot.to_euler()

# -----------------
# render settings
# -----------------
scene.render.engine = "BLENDER_EEVEE"

scene.render.resolution_x = 224
scene.render.resolution_y = 224

# AO
scene.eevee.use_gtao = True
scene.eevee.gtao_distance = 1.0

# Freestyle outline
scene.render.use_freestyle = True

view_layer = bpy.context.view_layer
view_layer.use_freestyle = True

# -----------------
# 8 views
# -----------------
views = [
(1,1,1),(1,1,-1),(1,-1,1),(1,-1,-1),
(-1,1,1),(-1,1,-1),(-1,-1,1),(-1,-1,-1)
]

for i,v in enumerate(views):

    cam.location = (v[0]*3,v[1]*3,v[2]*3)
    look_at(cam,mathutils.Vector((0,0,0)))

    scene.render.filepath = os.path.join(os.getcwd(),f"view_{i}.png")

    bpy.ops.render.render(write_still=True)
