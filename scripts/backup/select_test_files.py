#!/usr/bin/env python3
"""
随机选取 10 个 PLY 文件进行测试渲染
输出到 json_img_random 目录，保持与 json_ply 相同的层级结构
"""

import os
import random
import glob
import subprocess

# 源目录
SRC_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply"
OUTPUT_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random"
SCRIPT_PATH = "/root/projects/CAD-MLLM/scripts/render_ply_single.py"

# 获取所有 PLY 文件
ply_files = sorted(glob.glob(os.path.join(SRC_DIR, "**", "*.ply"), recursive=True))
print(f"Total PLY files: {len(ply_files)}")

# 随机选取 10 个
random.seed(42)  # 固定随机种子，便于复现
selected = random.sample(ply_files, 10)

print(f"\nSelected 10 files for testing:")
for i, f in enumerate(selected):
    rel_path = os.path.relpath(f, SRC_DIR)
    print(f"  {i+1}. {rel_path}")

# 生成处理命令
print(f"\nOutput dir: {OUTPUT_DIR}")
print("\n=== Run these commands ===\n")

for i, ply_path in enumerate(selected):
    # 计算相对路径以保持目录结构
    rel_path = os.path.relpath(ply_path, SRC_DIR)
    # 例如：0074/00744804_00001.ply
    parts = rel_path.split('/')
    file_stem = os.path.splitext(parts[-1])[0]
    # 输出目录结构：json_img_random/0074/file_stem/
    # 输出文件：json_img_random/0074/file_stem/file_stem_000.png ~ _007.png
    out_subdir = os.path.join(OUTPUT_DIR, parts[0], file_stem)

    print(f"# {i+1}. {rel_path}")
    print(f"blender -b --python {SCRIPT_PATH} -- --ply {ply_path} --out {out_subdir}")
    print()
