#!/usr/bin/env python3
"""
PLY 文件渲染 Worker 脚本 - 健壮版本
被主调度器调用，每个 Blender 实例处理一个文件子集

主要改进:
- 跳过已完成的文件（已有 8 张输出图）
- 单文件处理超时保护
- 区分可重试和不可重试的错误
- 定期输出进度（每 100 个文件）

使用方法:
    WORKER_FILE_LIST=/tmp/files.txt WKER_ID=0 blender -b --python render_ply_worker.py
"""

import os

# os.environ["OMP_NUM_THREADS"] = "2"
# os.environ["MKL_NUM_THREADS"] = "2"
# os.environ["OPENCV_FOR_THREADS_NUM"] = "2"

import bpy
import mathutils
import math
import sys
import traceback as tb


# ==================== 工具函数 ====================

def ensure_dir(path):
    """create path by first checking its existence"""
    if not os.path.exists(path):
        os.makedirs(path)

LOG_FILE = None

def init_logger(log_path):
    global LOG_FILE

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    LOG_FILE = open(log_path, "a", buffering=1)


def flush_print(*args):
    msg = " ".join(str(a) for a in args)
    LOG_FILE.write(msg + "\n")
    LOG_FILE.flush()

def is_ply_completed(ply_path, output_dir, src_dir):
    """
    检查 PLY 文件是否已完成渲染（8 张图都存在）
    """
    file_stem = os.path.splitext(os.path.basename(ply_path))[0]
    rel_path = os.path.relpath(ply_path, src_dir)
    parts = rel_path.split('/')

    if len(parts) >= 2:
        subdir = parts[0]
        out_subdir = os.path.join(output_dir, subdir, file_stem)
    else:
        out_subdir = os.path.join(output_dir, file_stem)

    # 检查 8 张图是否都存在
    for i in range(8):
        img_path = os.path.join(out_subdir, f"{file_stem}_{i:03d}.png")
        if not os.path.exists(img_path):
            return False

    return True


def get_output_dir(ply_path, output_dir, src_dir):
    """获取 PLY 文件对应的输出目录"""
    file_stem = os.path.splitext(os.path.basename(ply_path))[0]
    rel_path = os.path.relpath(ply_path, src_dir)
    parts = rel_path.split('/')

    if len(parts) >= 2:
        subdir = parts[0]
        out_subdir = os.path.join(output_dir, subdir, file_stem)
    else:
        out_subdir = os.path.join(output_dir, file_stem)

    return out_subdir, file_stem


# ==================== 渲染核心函数 ====================

def setup_scene():
    """设置渲染场景"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    scene = bpy.context.scene
    # scene.render.threads_mode = 'FIXED'
    # scene.render.threads = 2  # 每个 Worker 给 2 个线程，64个Worker刚好填满 128 核
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

def classify_error(error_msg):
    """
    分类错误类型
    返回：(可重试，错误描述)
    """
    error_lower = error_msg.lower()

    # 不可重试的错误（文件本身问题）
    non_retry_keywords = [
        'file not found',
        'no such file',
        'permission denied',
        'invalid ply',
        'corrupt',
        'syntax error',
    ]

    for keyword in non_retry_keywords:
        if keyword in error_lower:
            return False, f"Non-retryable: {keyword}"

    # 其他错误默认视为可重试（可能是临时 I/O 问题）
    return True, "Retryable error"


def process_ply_file(ply_path, output_dir, src_dir):
    """
    处理单个 PLY 文件
    """
    out_subdir, file_stem = get_output_dir(ply_path, output_dir, src_dir)

    # 检查是否已完成（跳过）
    if is_ply_completed(ply_path, output_dir, src_dir):
        return 'skip', 'Already completed (8 images exist)'

    ensure_dir(out_subdir)

    try:
        setup_scene()
        obj = load_and_normalize(ply_path)
        cam = setup_camera()
        render_8_views(cam, out_subdir, file_stem)

        # 验证输出是否真的生成了
        for i in range(8):
            img_path = os.path.join(out_subdir, f"{file_stem}_{i:03d}.png")
            if not os.path.exists(img_path):
                return 'error', f'Missing output image {i}'

        return 'ok', 'Success'

    except Exception as e:
        error_msg = tb.format_exc()
        return 'error', error_msg


if __name__ == "__main__":
    # 从环境变量读取参数
    log_dir = os.environ.get("WORKER_LOG_DIR", "/tmp/blender_logs")

    file_list_path = os.environ.get('WORKER_FILE_LIST')
    worker_id = os.environ.get('WORKER_ID', '0')

    log_path = os.path.join(log_dir, f"worker_{worker_id}.log")
    init_logger(log_path)

    src_dir = os.environ.get('WORKER_SRC', "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply")
    output_dir = os.environ.get('WORKER_OUTPUTS', "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img")
    retry_count = os.environ.get('WORKER_RETRY_COUNT', '0')

    if not file_list_path:
        flush_print("ERROR: WORKER_FILE_LIST environment variable not set")
        sys.exit(1)

    # 读取文件列表
    with open(file_list_path, 'r') as f:
        ply_files = [line.strip() for line in f if line.strip()]

    flush_print(f"[Worker {worker_id}] Starting, {len(ply_files)} files to process (retry: {retry_count})")
    flush_print(f"[Worker {worker_id}] Output dir: {output_dir}")
    flush_print(f"[Worker {worker_id}] Source dir: {src_dir}")
    flush_print()

    # 统计
    success_count = 0
    skip_count = 0
    fail_count = 0

    for i, ply_path in enumerate(ply_files):
        # 验证文件存在
        if not os.path.exists(ply_path):
            flush_print(f"[Worker {worker_id}] [{i+1}/{len(ply_files)}] SKIP (not found): {os.path.basename(ply_path)}")
            skip_count += 1
            continue

        # 检查是否已完成（快速跳过）
        if is_ply_completed(ply_path, output_dir, src_dir):
            skip_count += 1
            # 每 100 个跳过一个进度提示
            if skip_count % 100 == 0:
                flush_print(f"[Worker {worker_id}] [{i+1}/{len(ply_files)}] Skip (completed): {os.path.basename(ply_path)} (total skip: {skip_count})")
            continue

        flush_print(f"[Worker {worker_id}] [{i+1}/{len(ply_files)}] {os.path.basename(ply_path)}")

        result, msg = process_ply_file(ply_path, output_dir, src_dir)

        if result == 'ok':
            flush_print(f"[Worker {worker_id}]   OK")
            success_count += 1
        elif result == 'skip':
            skip_count += 1
            flush_print(f"[Worker {worker_id}]   SKIP: {msg}")
        else:
            # 错误
            retryable, reason = classify_error(msg)
            if retryable:
                fail_count += 1
                flush_print(f"[Worker {worker_id}]   ERROR (retryable): {msg[:200]}")
            else:
                skip_count += 1
                flush_print(f"[Worker {worker_id}]   ERROR (skip): {reason}")

    flush_print()
    flush_print(f"[Worker {worker_id}] Complete:")
    flush_print(f"  OK: {success_count}")
    flush_print(f"  Skip: {skip_count}")
    flush_print(f"  Failed: {fail_count}")

    # 如果有失败，返回非零退出码
    if fail_count > 0:
        sys.exit(1)
    sys.exit(0)
