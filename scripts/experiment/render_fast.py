import bpy
import mathutils
import math
import os

def setup_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 224
    scene.render.resolution_y = 224
    
    shading = scene.display.shading
    shading.light = 'STUDIO'
    shading.color_type = 'MATERIAL'
    shading.show_cavity = True
    shading.cavity_type = 'BOTH'
    shading.cavity_ridge_factor = 2.0
    shading.cavity_valley_factor = 2.0
    shading.show_object_outline = True
    shading.show_shadows = True
    shading.shadow_intensity = 0.4

def load_and_normalize(filepath):
    bpy.ops.import_mesh.ply(filepath=filepath)
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)
    
    mat = bpy.data.materials.new(name="CAD_Mat")
    mat.diffuse_color = (0.5, 0.5, 0.5, 1.0)
    obj.data.materials.append(mat)
    
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj

def setup_camera():
    cam_data = bpy.data.cameras.new("CameraData")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    
    # 核心修正：确保类型切换成功
    cam_data.type = 'ORTHO'
    return cam_obj

def get_global_ortho_scale(obj):
    """
    计算一个全局统一的缩放值，确保物体在任何角度旋转都不会出界，
    且在最长轴视角下占据约 85% 的画面。
    """
    # 计算物体 8 个顶点的最大模长（包围球半径）
    bbox = [mathutils.Vector(v) for v in obj.bound_box]
    max_radius = max(v.length for v in bbox)
    
    # 正交相机的 orthographic_scale 对应视口高度
    # 2.0 * max_radius 是物体的最大直径
    # 除以 0.85 得到视口大小，确保 85% 占比
    return (max_radius * 2.0) / 0.85

def render_8_views(obj, cam_obj, output_prefix="test_output"):
    # 固定 8 个视角
    coords = [
        (-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)
    ]
    
    # 修正：通过 cam_obj.data 访问 orthographic_scale
    # 并使用全局统一缩放，保证 8 张图大小比例一致
    unified_scale = get_global_ortho_scale(obj)
    cam_obj.data.orthographic_scale = unified_scale
    
    dist = 10.0
    for i, coord in enumerate(coords):
        pos = mathutils.Vector(coord).normalized() * dist
        cam_obj.location = pos
        
        # LookAt 原点
        direction = -pos
        cam_obj.rotation_mode = 'QUATERNION'
        cam_obj.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
        
        scene = bpy.context.scene
        scene.render.image_settings.color_mode = 'BW'
        scene.render.filepath = os.path.abspath(f"{output_prefix}_{i}.png")
        
        bpy.ops.render.render(write_still=True)
        print(f"View {i} rendered with scale {unified_scale:.4f}")

if __name__ == "__main__":
    filepath = "test.ply"
    if os.path.exists(filepath):
        setup_scene()
        target_obj = load_and_normalize(filepath)
        camera = setup_camera()
        render_8_views(target_obj, camera, "test_output")
