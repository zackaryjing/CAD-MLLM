import bpy
import mathutils # 修正：独立导入
import math
import os

def setup_scene():
    # 1. 彻底清理场景
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 224
    scene.render.resolution_y = 224
    
    # 设置色彩管理为标准灰度
    scene.display_settings.display_device = 'sRGB'
    scene.view_settings.view_transform = 'Standard'
    
    # 2. 开启 AO (Ambient Occlusion) - Blender 3.6 EEVEE API
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 1.0
    scene.eevee.gtao_factor = 2.0  # 增强AO强度，使拐角更黑
    
    # 3. 开启 Freestyle 轮廓线渲染
    scene.render.use_freestyle = True
    # 获取或创建 ViewLayer 里的 Freestyle 设置
    view_layer = bpy.context.view_layer
    lineset = view_layer.freestyle_settings.linesets.new("CAD_Lines")
    lineset.select_silhouette = True  # 轮廓
    lineset.select_crease = True     # 折痕（棱线）
    lineset.select_border = True     # 边界
    
    # 调整折痕角度，捕捉更多几何棱线 (建议 130° 左右)
    view_layer.freestyle_settings.crease_angle = math.radians(134)
    
    # 设置线宽
    bpy.data.linestyles["LineStyle"].thickness = 1.2

    # 4. 设置纯白环境光
    if not scene.world:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg_node = scene.world.node_tree.nodes.get('Background')
    if bg_node:
        bg_node.inputs[0].default_value = (0.7, 0.7, 0.7, 1.0) # 中度灰环境
        bg_node.inputs[1].default_value = 1.0

def load_and_normalize(filepath):
    # 导入 PLY
    bpy.ops.import_mesh.ply(filepath=filepath)
    obj = bpy.context.selected_objects[0]
    
    # 设置材质：哑光灰
    mat = bpy.data.materials.new(name="MatteGray")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.6, 0.6, 0.6, 1.0)
        bsdf.inputs['Roughness'].default_value = 1.0 # 消除反光
        bsdf.inputs['Specular'].default_value = 0.0
    obj.data.materials.append(mat)

    # 归一化：居中并缩放
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)
    
    # 自动缩放至占据约 80% 视野
    max_dim = max(obj.dimensions)
    if max_dim > 0:
        # 在 50mm 镜头下，坐标范围约 2.0 时占比合适
        scale_val = 2.0 / max_dim
        obj.scale = (scale_val, scale_val, scale_val)
    
    # 应用变换
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj

def setup_camera():
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    cam_data.lens = 50 # 50mm 标准镜头
    return cam_obj

def render_8_views(cam_obj, output_prefix="test_output"):
    # 严格按照全空间 8 个顶点排序
    # 顺序：(-,-,-), (+,-,-), (-,+,-), (+,+,-), (-,-,+), (+,-,+), (-,+,+), (+,+,+)
    coords = [
        (-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)
    ]
    
    dist = 5.0 # 相机距离
    
    for i, coord in enumerate(coords):
        # 计算位置
        pos = mathutils.Vector(coord).normalized() * dist
        cam_obj.location = pos
        
        # 修正：使用 mathutils.Vector 的 to_track_quat
        direction = mathutils.Vector((0, 0, 0)) - pos
        cam_obj.rotation_mode = 'QUATERNION'
        cam_obj.rotation_quaternion = direction.to_track_quat('-Z', 'Y')
        
        # 指定输出路径
        scene = bpy.context.scene
        scene.render.image_settings.color_mode = 'BW' # 强制输出单通道灰度
        scene.render.filepath = os.path.abspath(f"{output_prefix}_{i}.png")
        
        # 执行渲染
        bpy.ops.render.render(write_still=True)
        print(f"Rendered View {i} at {coord}")

if __name__ == "__main__":
    filepath = "test.ply"
    if os.path.exists(filepath):
        setup_scene()
        load_and_normalize(filepath)
        camera = setup_camera()
        render_8_views(camera, "test_output")
    else:
        print(f"File not found: {filepath}")
