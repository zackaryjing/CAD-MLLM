#!/usr/bin/env python3
"""
轻量 worker wrapper —— 在 Blender 环境中运行（调用 render_ply_worker 中的函数）
环境变量:
  WORKER_FILE_LIST: 必需，文件列表（每行一个 ply 绝对/相对路径）
  WORKER_ID: 可选
  WORKER_SRC: 可选，源码根目录（用于输出路径计算）
  WORKER_OUTPUTS: 可选，输出目录
"""
import os
import sys

# 确保脚本目录在 sys.path，方便 import render_ply_worker
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 导入核心渲染逻辑（不修改该文件）
import render_ply_worker as core

def read_file_list(path):
    with open(path, 'r') as f:
        return [l.strip() for l in f if l.strip()]

def flush(msg=""):
    print(msg)
    sys.stdout.flush()

def main():
    file_list_path = os.environ.get('WORKER_FILE_LIST')
    worker_id = os.environ.get('WORKER_ID', '0')
    src_dir = os.environ.get('WORKER_SRC', core.__dict__.get('src_dir', "/"))
    output_dir = os.environ.get('WORKER_OUTPUTS', core.__dict__.get('output_dir', "/"))
    if not file_list_path:
        print("ERROR: WORKER_FILE_LIST not set")
        sys.exit(2)

    files = read_file_list(file_list_path)
    flush(f"[worker {worker_id}] start: {len(files)} files (src={src_dir}, out={output_dir})")

    success = 0
    skipped = 0
    failed = 0

    for idx, ply in enumerate(files, 1):
        if not os.path.exists(ply):
            flush(f"[worker {worker_id}] [{idx}/{len(files)}] SKIP missing: {ply}")
            skipped += 1
            continue

        # 使用 core.is_ply_completed 来判断（与现有逻辑一致）
        try:
            completed = core.is_ply_completed(ply, output_dir, src_dir)
        except Exception:
            # 如果导入或调用失败，保守处理为未完成，交给 process_ply_file 处理
            completed = False

        if completed:
            skipped += 1
            if skipped % 100 == 0:
                flush(f"[worker {worker_id}] [{idx}/{len(files)}] skip-count: {skipped}")
            continue

        flush(f"[worker {worker_id}] [{idx}/{len(files)}] processing: {os.path.basename(ply)}")

        try:
            # 调用核心处理函数（render_ply_worker.py 中的 process_ply_file）
            res, msg = core.process_ply_file(ply, output_dir, src_dir)
            if res == 'ok':
                success += 1
                flush(f"[worker {worker_id}]   OK ({success})")
            elif res == 'skip':
                skipped += 1
                flush(f"[worker {worker_id}]   SKIP ({msg})")
            else:
                failed += 1
                flush(f"[worker {worker_id}]   FAIL (retryable?) {msg[:200]}")
        except Exception as e:
            failed += 1
            flush(f"[worker {worker_id}]   EXCEPTION: {str(e)[:200]}")

    flush()
    flush(f"[worker {worker_id}] done. OK={success} SKIP={skipped} FAIL={failed}")

    # 返回非零以让调度器知晓有失败
    if failed > 0:
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
