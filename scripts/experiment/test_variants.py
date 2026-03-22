#!/usr/bin/env python3
"""
测试三种阴影/光照方案
生成 8 视角渲染图用于对比
"""

import bpy
import mathutils
import math
import os
import sys

# ========== 配置选项 ==========
# 修改这里来切换方案：'base', 'ao', 'sun', 'ao_sun'
TEST_MODE = 'ao_sun'
OUTPUT_PREFIX = 'variant_ao_sun'
# =============================


def cleanup_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    # 清理旧数据
    for mesh in bpy.data.meshes: bpy.data.meshes.remove(mesh)
    for mat in bpy.data.materials: bpy.data.materials.remove(mat)
    for light in bpy.data.lights: bpy.data.lights.remove(light)


def setup_scene_common():
    """通用场景设置"""
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

    # 关闭不必要的效果
    scene.eevee.use_bloom = False
    scene.eevee.use_ssr = False
    scene.eevee.use_motion_blur = False

    # 白色世界背景
    if not scene.world:
        scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    bg_node = scene.world.node_tree.nodes.get('Background')
    if bg_node:
        bg_node.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
        bg_node.inputs['Strength'].default_value = 1.0

    # Freestyle 轮廓线
    scene.render.use_freestyle = True
    vl = bpy.context.view_layer
    vl.freestyle_settings.crease_angle = math.radians(120)
    ls = vl.freestyle_settings.linesets[0]
    ls.select_silhouette = True
    ls.select_crease = True
    ls.select_border = False
    linestyle = bpy.data.linestyles.get('LineStyle')
    if linestyle:
        linestyle.thickness = 1.0
        linestyle.color = (0, 0, 0)


def setup_lights(mode):
    """根据模式设置光照"""
    scene = bpy.context.scene

    # AO 设置
    if mode in ('ao', 'ao_sun'):
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 2.0
        scene.eevee.gtao_factor = 1.5
    else:
        scene.eevee.use_gtao = False

    # 太阳灯设置
    if mode in ('sun', 'ao_sun'):
        bpy.ops.object.light_add(type='SUN')
        sun = bpy.context.active_object
        sun.location = (3, -3, 3)
        sun.data.energy = 2.5
        sun.data.color = (1.0, 0.98, 0.95)
        # 启用阴影
        sun.data.use_shadow = True


def load_and_normalize(filepath):
    """加载并归一化物体"""
    bpy.ops.import_mesh.ply(filepath=filepath)
    obj = bpy.context.selected_objects[0]

    # 材质
    mat = bpy.data.materials.new(name="RenderMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (0.65, 0.65, 0.65, 1.0)
        bsdf.inputs['Roughness'].default_value = 1.0
        bsdf.inputs['Specular'].default_value = 0.0
    obj.data.materials.append(mat)

    # 居中
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 缩放
    bbox = obj.bound_box
    max_radius = max(mathutils.Vector(v).length for v in bbox)
    target_radius = 0.95
    scale_factor = target_radius / max_radius
    obj.scale = (scale_factor, scale_factor, scale_factor)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    return obj


def setup_camera():
    """创建正交相机"""
    cam_data = bpy.data.cameras.new("Camera")
    cam_obj = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene = bpy.context.scene
    scene.camera = cam_obj
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 2.0
    return cam_obj


def render_8_views(cam_obj, output_prefix):
    """渲染 8 个视角"""
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

        scene.render.filepath = os.path.abspath(f"{output_prefix}_{i}.png")
        bpy.ops.render.render(write_still=True)
        print(f"  Rendered {output_prefix}_{i}.png")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ply_path = os.path.join(script_dir, "test.ply")

    if not os.path.exists(ply_path):
        print(f"Error: {ply_path} not found")
        sys.exit(1)

    print(f"=== Testing mode: {TEST_MODE} ===")

    cleanup_scene()
    setup_scene_common()
    setup_lights(TEST_MODE)
    obj = load_and_normalize(ply_path)
    cam = setup_camera()
    render_8_views(cam, os.path.join(script_dir, OUTPUT_PREFIX))

    print(f"\n=== Complete: {OUTPUT_PREFIX}_0.png to {OUTPUT_PREFIX}_7.png ===")


if __name__ == "__main__":
    main()
