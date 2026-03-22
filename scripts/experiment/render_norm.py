#!/usr/bin/env python3
# Version: v6
# 变更：使用法向竖直分量 (Normal Z) + AO 确定颜色，不用光照
# 目的：法向朝上=亮，朝下=暗，明确区分不同朝向的面
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

    # AO - 关闭，避免干扰
    scene.eevee.use_gtao = False

    # 关闭所有光照，让法向材质决定颜色
    shading = scene.display.shading
    shading.color_type = 'MATERIAL'
    shading.light = 'FLAT'

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

    # 材质：基于法向竖直分量 (Normal Z) 确定颜色
    # 朝上 (Z=1) = 亮灰色，朝下 (Z=-1) = 深灰色，侧面 (Z=0) = 中灰色
    mat = bpy.data.materials.new(name="NormalMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # 清除默认节点
    nodes.clear()

    # 创建节点 - 使用 New Geometry 节点获取法向（Blender 3.6 兼容）
    geom_node = nodes.new(type='ShaderNodeNewGeometry')
    sep_node = nodes.new(type='ShaderNodeSeparateXYZ')
    map_node = nodes.new(type='ShaderNodeMapRange')
    bsdf_node = nodes.new(type='ShaderNodeBsdfDiffuse')
    output_node = nodes.new(type='ShaderNodeOutputMaterial')

    # 设置节点位置
    geom_node.location = (-600, 0)
    sep_node.location = (-400, 0)
    map_node.location = (-200, 0)
    bsdf_node.location = (0, 0)
    output_node.location = (200, 0)

    # 设置 Map Range 参数：将 Normal Z (-1 到 1) 映射到灰度 (0.3 到 0.8)
    # 朝下的面不会死黑，保持 0.3 的亮度
    map_node.inputs['From Min'].default_value = -1.0
    map_node.inputs['From Max'].default_value = 1.0
    map_node.inputs['To Min'].default_value = 0.3   # 朝下的面 = 深灰但不黑
    map_node.inputs['To Max'].default_value = 0.8   # 朝上的面 = 亮灰但不纯白
    map_node.clamp = True

    # 连接节点：Geometry(Normal) -> SeparateXYZ(Z) -> MapRange -> Diffuse BSDF -> Output
    links.new(geom_node.outputs['Normal'], sep_node.inputs['Vector'])
    links.new(sep_node.outputs['Z'], map_node.inputs['Value'])
    links.new(map_node.outputs['Result'], bsdf_node.inputs['Color'])
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

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
        render_8_views(camera, "output_v6")
        print("\n=== Rendering Complete ===")
    else:
        print(f"File not found: {filepath}")
