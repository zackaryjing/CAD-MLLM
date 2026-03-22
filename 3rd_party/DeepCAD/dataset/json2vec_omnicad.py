#!/usr/bin/env python3
"""
从 Omni-CAD JSON 文件生成 .h5 向量文件
基于 DeepCAD 的 json2vec.py 修改

用法:
    cd /root/projects/CAD-MLLM/3rd_party/DeepCAD/dataset
    source /root/miniconda3/bin/activate deepcad38

    # 正常运行（跳过已存在的文件）
    python json2vec_omnicad.py

    # 清空已存在的文件，重新生成所有
    python json2vec_omnicad.py --force

    # 指定并行 worker 数量
    python json2vec_omnicad.py --n_jobs 30
"""

import os
import json
import numpy as np
import h5py
from joblib import Parallel, delayed
import sys
import argparse

sys.path.append("..")
from cadlib.extrude import CADSequence
from cadlib.macro import *


# ========== 配置路径 ==========
OMNI_JSON_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json"
SAVE_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/cad_vec"
# =============================


def process_one(json_path):
    """处理单个 JSON 文件"""
    # 计算相对路径和保存路径
    rel_path = os.path.relpath(json_path, OMNI_JSON_DIR)
    save_path = os.path.join(SAVE_DIR, os.path.splitext(rel_path)[0] + ".h5")

    # 如果已存在，跳过
    if os.path.exists(save_path):
        return "skip", json_path

    try:
        with open(json_path, "r") as fp:
            data = json.load(fp)

        cad_seq = CADSequence.from_dict(data)
        cad_seq.normalize()
        cad_seq.numericalize()
        cad_vec = cad_seq.to_vector(MAX_N_EXT, MAX_N_LOOPS, MAX_N_CURVES, MAX_TOTAL_LEN, pad=False)

        if cad_vec is None:
            return "vec_none", json_path

        if MAX_TOTAL_LEN < cad_vec.shape[0]:
            return "too_long", json_path

        # 创建目录
        truck_dir = os.path.dirname(save_path)
        if not os.path.exists(truck_dir):
            os.makedirs(truck_dir)

        # 保存 h5
        with h5py.File(save_path, 'w') as fp:
            fp.create_dataset("vec", data=cad_vec, dtype=np.int32)

        return "success", json_path

    except Exception as e:
        return f"error: {e}", json_path


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="从 Omni-CAD JSON 生成 .h5 向量文件")
    parser.add_argument("--force", action="store_true",
                        help="删除已存在的 h5 文件，重新生成所有")
    parser.add_argument("--n_jobs", type=int, default=96,
                        help="并行 worker 数量 (默认：60)")
    args = parser.parse_args()

    N_JOBS = args.n_jobs

    print(f"源目录：{OMNI_JSON_DIR}")
    print(f"保存目录：{SAVE_DIR}")
    print(f"并行 worker 数量：{N_JOBS}")
    print(f"当前限制：MAX_TOTAL_LEN={MAX_TOTAL_LEN}, MAX_N_EXT={MAX_N_EXT}")

    # 创建输出目录
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

    # 如果 --force，删除所有已存在的 h5 文件
    if args.force:
        print("\n[!] --force 已启用，正在删除已存在的 h5 文件...")
        import glob
        h5_files = glob.glob(os.path.join(SAVE_DIR, "**/*.h5"), recursive=True)
        if h5_files:
            print(f"    找到 {len(h5_files)} 个 h5 文件")
            for f in h5_files:
                os.remove(f)
            print(f"    已删除 {len(h5_files)} 个文件")
        else:
            print("    没有找到已存在的 h5 文件")
        print()

    # 收集所有 JSON 文件
    json_paths = []
    for root, dirs, files in os.walk(OMNI_JSON_DIR):
        for f in files:
            if f.endswith('.json'):
                json_paths.append(os.path.join(root, f))

    json_paths = sorted(json_paths)
    print(f"共 {len(json_paths)} 个文件待处理")

    # 并行处理
    results = Parallel(n_jobs=N_JOBS, verbose=2, backend="loky")(
        delayed(process_one)(json_path)
        for json_path in json_paths
    )

    # 统计结果
    from collections import Counter
    stats = Counter(r[0] for r in results)
    print("\n=== 处理结果 ===")
    for status, count in sorted(stats.items()):
        print(f"  {status}: {count}")

    # 打印错误详情
    errors = [(r[0], r[1]) for r in results if r[0].startswith("error")]
    if errors:
        print("\n=== 错误详情 ===")
        for status, path in errors[:20]:
            print(f"  {path}: {status}")
        if len(errors) > 20:
            print(f"  ... 还有 {len(errors) - 20} 个错误")
