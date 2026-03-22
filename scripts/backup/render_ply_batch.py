#!/usr/bin/env python3
"""
PLY 文件批量渲染脚本 - 测试版本
基于法向竖直分量确定颜色，白色背景，Freestyle 轮廓线

使用方法:
    blender -b --python render_ply_batch.py -- --src <source_dir> --outputs <output_dir> --num 10
"""

import bpy
import mathutils
import math
import os
import sys
import argparse
import glob


def ensure_dir(path):
    """create path by first checking its existence"""
    if not os.path.exists(path):
        os.makedirs(path)


# ==================== 渲染核心函数 ====================

def setup_scene():
    """设置渲染场景"""
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

    # AO - 关闭
    scene.eevee.use_gtao = False

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


def load_and_normalize(filepath):
    """加载 PLY 并归一化到合适大小"""
    bpy.ops.import_mesh.ply(filepath=filepath)
    obj = bpy.context.selected_objects[0]

    # 材质：基于法向竖直分量 (Normal Z) 确定颜色
    mat = bpy.data.materials.new(name="NormalMat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    nodes.clear()

    geom_node = nodes.new(type='ShaderNodeNewGeometry')
    sep_node = nodes.new(type='ShaderNodeSeparateXYZ')
    map_node = nodes.new(type='ShaderNodeMapRange')
    bsdf_node = nodes.new(type='ShaderNodeBsdfDiffuse')
    output_node = nodes.new(type='ShaderNodeOutputMaterial')

    geom_node.location = (-600, 0)
    sep_node.location = (-400, 0)
    map_node.location = (-200, 0)
    bsdf_node.location = (0, 0)
    output_node.location = (200, 0)

    map_node.inputs['From Min'].default_value = -1.0
    map_node.inputs['From Max'].default_value = 1.0
    map_node.inputs['To Min'].default_value = 0.3
    map_node.inputs['To Max'].default_value = 0.8
    map_node.clamp = True

    links.new(geom_node.outputs['Normal'], sep_node.inputs['Vector'])
    links.new(sep_node.outputs['Z'], map_node.inputs['Value'])
    links.new(map_node.outputs['Result'], bsdf_node.inputs['Color'])
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    obj.data.materials.append(mat)

    # 居中
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')
    obj.location = (0, 0, 0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # 计算包围球半径并缩放
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
    bpy.context.scene.camera = cam_obj
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = 2.0
    return cam_obj


def render_8_views(cam_obj, output_dir, file_stem):
    """渲染 8 个固定视角"""
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

        output_path = os.path.join(output_dir, f"{file_stem}_{i:03d}.png")
        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)


# ==================== 主逻辑 ====================

def process_ply_file(ply_path, output_dir):
    """处理单个 PLY 文件"""
    file_stem = os.path.splitext(os.path.basename(ply_path))[0]
    out_subdir = os.path.join(output_dir, file_stem)
    ensure_dir(out_subdir)

    try:
        setup_scene()
        obj = load_and_normalize(ply_path)
        cam = setup_camera()
        render_8_views(cam, out_subdir, file_stem)
        print(f"  OK: {ply_path} -> {out_subdir}")
        return True
    except Exception as e:
        print(f"  ERROR: {ply_path} - {str(e)}")
        return False


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', type=str, required=True, help="source folder with PLY files")
    parser.add_argument('--idx', type=int, default=0, help="start index")
    parser.add_argument('--num', type=int, default=10, help="number of files to process")
    parser.add_argument('-o', '--outputs', type=str, default=None, help="output folder")
    args = parser.parse_args()

    # 解析附加参数（Blender 传入的）
    if "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1:]
    else:
        argv = []

    args = parser.parse_args(argv)

    src_dir = args.src
    out_dir = args.src + "_img" if args.outputs is None else args.outputs

    print(f"Source dir: {src_dir}")
    print(f"Output dir: {out_dir}")

    # 获取所有 PLY 文件
    ply_files = sorted(glob.glob(os.path.join(src_dir, "**", "*.ply"), recursive=True))
    print(f"Found {len(ply_files)} PLY files total")

    # 选取指定范围的文件
    if args.num != -1:
        ply_files = ply_files[args.idx:args.idx + args.num]

    print(f"Processing {len(ply_files)} files starting from idx {args.idx}")

    # 处理每个文件
    success_count = 0
    for i, ply_path in enumerate(ply_files):
        print(f"[{i+1}/{len(ply_files)}] {ply_path}")
        if process_ply_file(ply_path, out_dir):
            success_count += 1

    print(f"\nComplete: {success_count}/{len(ply_files)} successful")
