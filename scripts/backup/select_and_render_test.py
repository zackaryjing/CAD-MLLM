#!/usr/bin/env python3
"""
随机选取 10 个 PLY 文件进行测试渲染
输出到 json_img_random 目录
"""

import os
import random
import glob
import subprocess

# 源目录
SRC_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply"
OUTPUT_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random"
SCRIPT_PATH = "/root/projects/CAD-MLLM/scripts/render_ply_batch.py"

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

# 将选中的文件路径保存为列表
list_path = "/tmp/test_ply_files.txt"
with open(list_path, 'w') as f:
    for p in selected:
        f.write(p + '\n')

print(f"\nSaved file list to: {list_path}")

# 创建输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Output dir: {OUTPUT_DIR}")

# 生成处理脚本
process_script = "/tmp/run_test_render.sh"
with open(process_script, 'w') as f:
    f.write("#!/bin/bash\n")
    f.write(f"OUTPUT_DIR={OUTPUT_DIR}\n")
    f.write(f"SRC_DIR={SRC_DIR}\n")
    f.write("\n")
    f.write("# 逐个处理文件\n")
    for i, ply_path in enumerate(selected):
        # 计算相对路径以保持目录结构
        rel_path = os.path.relpath(ply_path, SRC_DIR)
        # 例如：0000/0000/00000007_00001.ply
        parts = rel_path.split('/')
        file_stem = os.path.splitext(parts[-1])[0]
        # 输出目录结构：json_img_random/0000/0000/file_stem/
        out_subdir = os.path.join(OUTPUT_DIR, parts[0], parts[1], file_stem)

        f.write(f"echo '[{i+1}/10] Processing {ply_path}'\n")
        f.write(f"blender -b --python {SCRIPT_PATH} -- --src {SRC_DIR} --outputs {out_subdir} --num 1 << EOF_PLY\n")
        f.write(f"{ply_path}\n")
        f.write(f"EOF_PLY\n")
        f.write("\n")

print(f"\nGenerated process script: {process_script}")
print("Run it with: bash " + process_script)
