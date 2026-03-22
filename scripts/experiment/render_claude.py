#!/usr/bin/env python3
# Version: v5
# 变更：材质改为中灰色 (0.5)，光照更水平 (3,-3,1.5)，移除补光
# 目的：增强顶部与背景区分，增大侧面与底面对比
"""
CAD 渲染脚本 - 基于 render_mini.py 优化
优化点:
- 物体占比从 ~50% 提升到 85%+
- 白色背景
- 保持 Freestyle 轮廓线
- 高效渲染 (EEVEE + 简单光照)
"""

import bpy
import mathutils
import math
import os


def setup_scene():
    """设置渲染场景"""
    # 清理场景
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 224
    scene.render.resolution_y = 224
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'BW'

    # 色彩管理
    scene.display_settings.display_device = 'sRGB'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    # 关闭不必要的效果以提高速度
    scene.eevee.use_bloom = False
    scene.eevee.use_ssr = False
    scene.eevee.use_motion_blur = False

    # 设置白色世界背景
    if not scene.world:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg_node = scene.world.node_tree.nodes.get('Background')
    if bg_node:
        bg_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)  # 纯白
        bg_node.inputs['Strength'].default_value = 1.0

    # AO (环境光遮蔽) - 增强缝隙和拐角的阴影
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 3.0
    scene.eevee.gtao_factor = 1.5

    # 主方向光 - 从较水平的方向照射，让侧面更亮，底面更暗
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.active_object
    sun.location = (3, -3, 1.5)  # 更水平的角度
    sun.data.energy = 3.5
    sun.data.color = (1.0, 1.0, 1.0)
    sun.data.use_shadow = False

    # Freestyle 轮廓线
    scene.render.use_freestyle = True
    view_layer = bpy.context.view_layer
    fs_settings = view_layer.freestyle_settings
    fs_settings.crease_angle = math.radians(120)

    lineset = fs_settings.linesets[0]
    lineset.select_silhouette = True
    lineset.select_crease = True
    lineset.select_border = False

    linestyle = bpy.data.linestyles.get('LineStyle')
    if linestyle:
        linestyle.thickness = 1.0
        linestyle.color = (0, 0, 0)


def load_and_normalize(filepath):
    """加载 PLY 并归一化到合适大小"""
    bpy.ops.import_mesh.ply(filepath=filepath)
    obj = bpy.context.selected_objects[0]

    # 材质：中等灰色（不是纯白），让顶部与白色背景区分开
    mat = bpy.data.materials.new(name="MatteGray")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.5, 0.5, 0.5, 1.0)  # 中灰色
        bsdf.inputs['Roughness'].default_value = 1.0
        bsdf.inputs['Specular'].default_value = 0.0
    obj.data.materials.append(mat)

    # 居中
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)

    # 获取原始尺寸
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 计算包围球半径（物体 8 个顶点到原点的最大距离）
    bbox = obj.bound_box
    max_radius = max(mathutils.Vector(v).length for v in bbox)

    # 目标半径设置：
    # ortho_scale=2.0 对应视口高度 2.0
    # target_radius=0.95 时，物体直径 1.9，占 95% 视口
    # 从角落视角 (1,1,1) 看，投影缩小到约 95% * 0.866 ≈ 82%
    target_radius = 0.95
    scale_factor = target_radius / max_radius
    obj.scale = (scale_factor, scale_factor, scale_factor)

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    print(f"Original max_radius: {max_radius:.4f}")
    print(f"Scale factor: {scale_factor:.4f}")
    print(f"Final dimensions: {obj.dimensions}")

    return obj


def setup_camera():
    """创建正交相机"""
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    bpy.context.scene.camera = cam_obj

    # 正交相机
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 2.0  # 视口高度

    return cam_obj


def render_8_views(cam_obj, output_prefix="output"):
    """渲染 8 个固定视角"""
    # 8 个视角：立方体顶点
    coords = [
        (-1, -1, -1), (1, -1, -1), (-1, 1, -1), (1, 1, -1),
        (-1, -1, 1), (1, -1, 1), (-1, 1, 1), (1, 1, 1)
    ]

    scene = bpy.context.scene
    dist = 5.0

    for i, coord in enumerate(coords):
        pos = mathutils.Vector(coord).normalized() * dist
        cam_obj.location = pos

        direction = mathutils.Vector((0, 0, 0)) - pos
        cam_obj.rotation_mode = 'QUATERNION'
        cam_obj.rotation_quaternion = direction.to_track_quat('-Z', 'Y')

        scene.render.image_settings.color_mode = 'BW'
        scene.render.filepath = os.path.abspath(f"{output_prefix}_{i}.png")

        bpy.ops.render.render(write_still=True)
        print(f"Rendered View {i} at {coord}")


if __name__ == "__main__":
    filepath = "test.ply"
    if os.path.exists(filepath):
        setup_scene()
        obj = load_and_normalize(filepath)
        camera = setup_camera()
        render_8_views(camera, "output_v5")
        print("\n=== Rendering Complete ===")
    else:
        print(f"File not found: {filepath}")
