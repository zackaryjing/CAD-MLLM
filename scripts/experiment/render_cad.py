import bpy
import math
import os

def setup_scene():
    # 1. 清理场景
    bpy.ops.wm.read_factory_settings(use_empty=True)
    
    scene = bpy.context.scene
    # 修正渲染引擎名称
    scene.render.engine = 'BLENDER_EEVEE' 
    scene.render.resolution_x = 224
    scene.render.resolution_y = 224
    scene.render.image_settings.color_mode = 'BW'  # 单通道灰度
    
    # 2. 强化 AO 设置 (在 Blender 4.2+ 中 AO 移动到了 Raytracing 面板)
    if hasattr(scene, "eevee"):
        # 开启光线追踪以获得高质量 AO
        scene.eevee.use_raytracing = True
        # 增加 AO 强度/距离感
        scene.eevee.shadow_dielectric_threshold = 0.5
        
    # 3. 开启轮廓线 (Freestyle)
    scene.render.use_freestyle = True
    layer = scene.view_layers[0]
    if not layer.freestyle_settings.linesets:
        layer.freestyle_settings.linesets.new("LineSet")
    
    lineset = layer.freestyle_settings.linesets[0]
    lineset.select_silhouette = True
    lineset.select_crease = True  # 开启折痕线，对 CAD 模型很重要
    lineset.linestyle.thickness = 1.2

    # 4. 世界环境：恒定柔光 (确保无死黑)
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg_node = world.node_tree.nodes.get("Background")
    bg_node.inputs[0].default_value = (1.0, 1.0, 1.0, 1) # 纯白环境光
    bg_node.inputs[1].default_value = 0.6 # 适中强度

def load_and_normalize(filepath):
    # 加载 PLY
    bpy.ops.wm.ply_import(filepath=filepath)
    
    # 获取导入的对象
    obj = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = obj
    
    # 材质设置：哑光深灰色 (利于观察 AO 阴影)
    mat = bpy.data.materials.new(name="Matte")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs['Roughness'].default_value = 1.0
    bsdf.inputs['Base Color'].default_value = (0.4, 0.4, 0.4, 1)
    obj.data.materials.append(mat)
    
    # 几何归一化
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)
    
    # 自动平滑（CAD模型渲染关键）
    if obj.type == 'MESH':
        bpy.ops.object.shade_smooth()
        obj.data.use_auto_smooth = True # 旧版
        # 新版 Blender 4.1+ 使用修改器或节点平滑，这里简单处理
    
    return obj

def render_8_views(obj):
    # 创建相机
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = 'ORTHO' # 使用正交相机，消除透视畸变，更符合 CAD 习惯
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj
    
    # 八个顶点位置 (象限 1-8)
    view_coords = [
        (1, 1, 1), (-1, 1, 1), (-1, -1, 1), (1, -1, 1),
        (1, 1, -1), (-1, 1, -1), (-1, -1, -1), (1, -1, -1)
    ]
    
    for i, coord in enumerate(view_coords):
        # 放置相机
        cam_obj.location = coord
        
        # 旋转相机指向原点
        direction = -cam_obj.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        cam_obj.rotation_euler = rot_quat.to_euler()
        
        # 核心：自动缩放以占据 80% 视野
        # 选中物体并让相机适配
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        # 调整正交比例 (Ortho Scale)
        bpy.ops.view3d.camera_to_view_selected()
        cam_data.ortho_scale *= 1.25 # 缩放系数：1/0.8 = 1.25，确保占据 80%
        
        # 渲染保存
        output_path = os.path.join(os.getcwd(), f"view_{i+1}.png")
        bpy.context.scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
        print(f"Saved: {output_path}")

if __name__ == "__main__":
    setup_scene()
    if os.path.exists("test.ply"):
        target_obj = load_and_normalize("test.ply")
        render_8_views(target_obj)
    else:
        print("Error: test.ply not found.")
