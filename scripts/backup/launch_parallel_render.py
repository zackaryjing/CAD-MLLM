#!/usr/bin/env python3
"""
PLY 文件并行渲染调度器 - 健壮版本
扫描所有 PLY 文件，启动多个 Blender 实例并行处理

主要改进:
- 跳过已完成的文件（已有 8 张输出图）
- 修复日志记录问题
- 支持 worker 失败重试
- 实时进度输出

使用方法:
    python launch_parallel_render.py --workers 32
"""

import os
import sys
import glob
import subprocess
import argparse
import tempfile
import shutil
import time
from pathlib import Path


def get_all_ply_files(src_dir):
    """扫描源目录下所有 PLY 文件"""
    ply_files = sorted(glob.glob(os.path.join(src_dir, "**", "*.ply"), recursive=True))
    print(f"Found {len(ply_files)} PLY files in {src_dir}")
    return ply_files


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


def filter_completed_files(ply_files, output_dir, src_dir):
    """过滤掉已完成的文件"""
    completed = 0
    remaining = []

    for ply_path in ply_files:
        if is_ply_completed(ply_path, output_dir, src_dir):
            completed += 1
        else:
            remaining.append(ply_path)

    print(f"Completed: {completed}, Remaining: {len(remaining)}")
    return remaining


def distribute_files(ply_files, num_workers):
    """将文件均匀分配给各个 worker"""
    workers = [[] for _ in range(num_workers)]
    for i, ply_path in enumerate(ply_files):
        workers[i % num_workers].append(ply_path)

    print(f"\nDistributing {len(ply_files)} files across {num_workers} workers:")
    for i, worker_files in enumerate(workers):
        if worker_files:
            print(f"  Worker {i}: {len(worker_files)} files")

    return workers


def create_file_list(files, temp_dir, worker_id):
    """为 worker 创建临时文件列表"""
    list_path = os.path.join(temp_dir, f"worker_{worker_id}_files.txt")
    with open(list_path, 'w') as f:
        for ply_path in files:
            f.write(ply_path + '\n')
    return list_path


def launch_worker(worker_id, file_list_path, src_dir, output_dir, log_dir, blender_path="blender", retry_count=0):
    """启动一个 worker Blender 实例"""
    log_path = os.path.join(log_dir, f"worker_{worker_id}.log")

    # 使用环境变量传递参数
    env = os.environ.copy()
    env['WORKER_FILE_LIST'] = file_list_path
    env['WORKER_ID'] = str(worker_id)
    env['WORKER_SRC'] = src_dir
    env['WORKER_OUTPUTS'] = output_dir
    env['WORKER_RETRY_COUNT'] = str(retry_count)

    cmd = [
        blender_path,
        "-b",
        "--python", "/root/projects/CAD-MLLM/scripts/render_ply_worker.py"
    ]

    print(f"Launching worker {worker_id} (retry: {retry_count})...")

    # 打开日志文件（行缓冲）
    log_file = open(log_path, 'w', buffering=1)
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env, bufsize=1)

    return proc, log_path, log_file


def wait_for_workers(processes, file_lists, log_files, max_retries=2):
    """
    等待所有 worker 完成，支持失败重试
    """
    failed_workers = []
    retry_info = {}  # worker_id -> (file_list_path, retry_count)

    # 初始化重试信息
    for worker_id, proc, log_path, log_file in processes:
        retry_info[worker_id] = (file_lists[worker_id], 0)

    while processes:
        # 检查每个进程的状态
        still_running = []
        for worker_id, proc, log_path, log_file in processes:
            ret = proc.poll()
            if ret is None:
                # 还在运行
                still_running.append((worker_id, proc, log_path, log_file))
            else:
                # 进程结束
                log_file.close()
                if ret == 0:
                    print(f"Worker {worker_id} completed successfully")
                else:
                    print(f"Worker {worker_id} FAILED (exit code: {ret})")
                    # 检查是否有剩余文件需要重试
                    file_list_path, retry_count = retry_info[worker_id]

                    # 检查文件列表中还有多少文件没处理
                    with open(file_list_path, 'r') as f:
                        remaining_files = [l.strip() for l in f if l.strip()]

                    if remaining_files and retry_count < max_retries:
                        # 还有文件且未达到最大重试次数，重启 worker
                        print(f"  -> Retrying worker {worker_id} with {len(remaining_files)} remaining files (attempt {retry_count + 1}/{max_retries})")

                        # 更新文件列表（只保留未处理的文件）
                        new_list_path = file_list_path + f".retry{retry_count + 1}"
                        with open(new_list_path, 'w') as f:
                            for ply_path in remaining_files:
                                f.write(ply_path + '\n')

                        # 重新启动 worker
                        new_proc, new_log_path, new_log_file = launch_worker(
                            worker_id=worker_id,
                            file_list_path=new_list_path,
                            src_dir=proc.env.get('WORKER_SRC', '/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply'),
                            output_dir=proc.env.get('WORKER_OUTPUTS', '/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img'),
                            log_dir=os.path.dirname(log_path),
                            blender_path=proc.cmdline[0],
                            retry_count=retry_count + 1
                        )
                        still_running.append((worker_id, new_proc, new_log_path, new_log_file))
                        retry_info[worker_id] = (new_list_path, retry_count + 1)
                    else:
                        if remaining_files:
                            print(f"  -> Max retries reached, {len(remaining_files)} files skipped")
                        failed_workers.append(worker_id)

        processes = still_running

        if processes:
            time.sleep(5)  # 每 5 秒检查一次

    return failed_workers


def main():
    parser = argparse.ArgumentParser(
        description="Launch multiple Blender instances for parallel PLY rendering"
    )
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Number of parallel workers (default: 8)"
    )
    parser.add_argument(
        "--src", type=str,
        default="/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply",
        help="Source directory containing PLY files"
    )
    parser.add_argument(
        "--outputs", type=str,
        default="/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img",
        help="Output directory for rendered images"
    )
    parser.add_argument(
        "--blender", type=str, default="blender",
        help="Path to blender executable (default: 'blender')"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without actually launching workers"
    )
    parser.add_argument(
        "--log-dir", type=str, default="./logs",
        help="Directory for worker log files"
    )
    parser.add_argument(
        "--max-retries", type=int, default=2,
        help="Maximum retry attempts for failed workers (default: 2)"
    )

    args = parser.parse_args()

    # 创建输出目录
    os.makedirs(args.outputs, exist_ok=True)
    os.makedirs(args.log_dir, exist_ok=True)

    print(f"Source: {args.src}")
    print(f"Output: {args.outputs}")
    print(f"Workers: {args.workers}")
    print()

    # 扫描所有 PLY 文件
    print("Scanning PLY files...")
    all_ply_files = get_all_ply_files(args.src)

    if not all_ply_files:
        print("ERROR: No PLY files found!")
        sys.exit(1)

    # 过滤已完成的文件
    print("Filtering completed files...")
    ply_files = filter_completed_files(all_ply_files, args.outputs, args.src)

    if not ply_files:
        print("All files are already completed!")
        return

    # 分配文件给各个 worker
    workers_files = distribute_files(ply_files, args.workers)

    if args.dry_run:
        print("\n[DRY RUN] Would launch the following workers:")
        for i, worker_files in enumerate(workers_files):
            print(f"  Worker {i}: {len(worker_files)} files")
        return

    # 创建临时目录存放文件列表
    temp_dir = tempfile.mkdtemp(prefix="ply_render_")
    print(f"\nTemp dir for file lists: {temp_dir}")

    # 为每个 worker 创建文件列表并启动
    processes = []
    file_lists = {}
    log_files = {}

    for i, worker_files in enumerate(workers_files):
        if not worker_files:
            continue

        file_list_path = create_file_list(worker_files, temp_dir, i)
        file_lists[i] = file_list_path
        proc, log_path, log_file = launch_worker(
            worker_id=i,
            file_list_path=file_list_path,
            src_dir=args.src,
            output_dir=args.outputs,
            log_dir=args.log_dir,
            blender_path=args.blender
        )
        log_files[i] = log_file
        processes.append((i, proc, log_path, log_file))

    # 等待所有进程完成（支持重试）
    print(f"\nLaunched {len(processes)} workers. Waiting for completion...")
    print(f"Logs are being written to: {args.log_dir}/")
    print()

    failed_workers = wait_for_workers(processes, file_lists, log_files, args.max_retries)

    # 清理临时目录
    shutil.rmtree(temp_dir)

    # 总结
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total workers launched: {len(file_lists)}")
    print(f"Successful: {len(file_lists) - len(failed_workers)}")
    if failed_workers:
        print(f"Failed: {len(failed_workers)} - Workers: {failed_workers}")
        print("Check individual log files for details.")
    else:
        print("All workers completed successfully!")


if __name__ == "__main__":
    main()
