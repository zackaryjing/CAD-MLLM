#!/usr/bin/env python3
"""
PLY 文件渲染调度器
功能:
 - 扫描 src 下所有 .ply
 - 跳过已完成（8 张图都存在）
 - 将剩余文件均匀分配到 N 个 worker（round-robin）
 - 为每个 worker 写文件列表并用 blender -b --python render_ply_worker.py 启动
"""
import os
import sys
import glob
import subprocess
import tempfile
import shutil
import time

# ==================== 配置 ====================
NUM_WORKERS = 60  # 或者 32
SRC_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply"
OUTPUT_DIR = "/root/projects/CAD-MLLM/datasets/Omni-CAD/json_img"
WORKER_SCRIPT = "/root/projects/CAD-MLLM/scripts/render_ply_worker.py"
BLENDER_CMD = "blender"
LOG_DIR = "/root/projects/CAD-MLLM/scripts/logs"


def find_ply(src):
    """扫描所有 PLY 文件"""
    return sorted(glob.glob(os.path.join(src, "**", "*.ply"), recursive=True))


def is_completed(ply_path, output_dir, src_dir):
    """检查 PLY 文件是否已完成渲染（8 张图都存在）"""
    stem = os.path.splitext(os.path.basename(ply_path))[0]
    rel = os.path.relpath(ply_path, src_dir)
    parts = rel.split(os.sep)
    if len(parts) >= 2:
        out_sub = os.path.join(output_dir, parts[0], stem)
    else:
        out_sub = os.path.join(output_dir, stem)
    for i in range(8):
        if not os.path.exists(os.path.join(out_sub, f"{stem}_{i:03d}.png")):
            return False
    return True


def filter_completed(files, output_dir, src_dir):
    """过滤出未完成的文件"""
    remaining = []
    done = 0
    for f in files:
        if is_completed(f, output_dir, src_dir):
            done += 1
        else:
            remaining.append(f)
    return remaining, done


def distribute(files, n):
    """Round-robin 分配文件到 N 个 worker"""
    lists = [[] for _ in range(n)]
    for i, f in enumerate(files):
        lists[i % n].append(f)
    return lists


def write_list(files, path):
    """写文件列表到文本文件"""
    with open(path, 'w') as f:
        for p in files:
            f.write(p + '\n')


def launch_worker(worker_id, list_path):
    """启动一个 worker 进程"""
    os.makedirs(LOG_DIR, exist_ok=True)

    env = os.environ.copy()
    env['WORKER_FILE_LIST'] = list_path
    env['WORKER_ID'] = str(worker_id)
    env['WORKER_SRC'] = SRC_DIR
    env['WORKER_OUTPUTS'] = OUTPUT_DIR
    env['WORKER_RETRY_COUNT'] = '0'
    env['WORKER_LOG_DIR'] = LOG_DIR

    # cmd = ["taskset", "-c", f"{worker_id * 2},{worker_id * 2 + 1}", BLENDER_CMD, "-b", "--python",
    #        WORKER_SCRIPT]
    cmd = [BLENDER_CMD, "-b", "--python",
           WORKER_SCRIPT]

    print(f"Launching worker {worker_id} ({len(open(list_path).readlines())} files)")
    sys.stdout.flush()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )
    # log_file_path = f"{LOG_DIR}/sheduler.log"
    # with open(log_file_path, 'a', buffering=1) as log_f:  # line-buffered
    #     proc = subprocess.Popen(
    #         cmd,
    #         stdout=subprocess.PIPE,
    #         stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
    #         env=env,
    #         text=True,
    #         bufsize=1
    #     )
    #
    #     # 直接同步写入日志
    #     for line in iter(proc.stdout.readline, ''):
    #         log_f.write(f"[Worker {worker_id}] {line}")
    #     proc.stdout.close()
    #     proc.wait()  # 等待进程结束

    return proc


def main():
    print(f"Scanning PLY files in {SRC_DIR}...")
    sys.stdout.flush()

    all_ply = find_ply(SRC_DIR)
    if not all_ply:
        print("No PLY files found.")
        return

    print(f"Found {len(all_ply)} PLY files, filtering completed...")
    sys.stdout.flush()

    remaining, done = filter_completed(all_ply, OUTPUT_DIR, SRC_DIR)
    print(f"Done: {done}, Remaining: {len(remaining)}")
    sys.stdout.flush()

    if not remaining:
        print("All files are already rendered. Exiting.")
        return

    # 分配任务
    lists = distribute(remaining, NUM_WORKERS)

    # 创建临时目录存放 worker 文件列表
    tempdir = tempfile.mkdtemp(prefix="ply_sched_")
    print(f"Temp dir: {tempdir}")
    print(f"Launching {NUM_WORKERS} workers...")
    sys.stdout.flush()

    procs = []
    for i, lst in enumerate(lists):
        if not lst:
            continue
        list_path = os.path.join(tempdir, f"worker_{i}.txt")
        write_list(lst, list_path)
        proc = launch_worker(i, list_path)
        procs.append((i, proc, list_path))

    # 等待所有 worker 完成
    print(f"Waiting for {len(procs)} workers to complete...")
    sys.stdout.flush()

    try:
        while procs:
            still_running = []
            for wid, proc, _ in procs:
                ret = proc.poll()
                print(f"proc {wid} returns {ret}")
                if ret is None:
                    still_running.append((wid, proc, _))
            if still_running:
                print(f"Still running count: {len(still_running)}")
                procs = still_running
                time.sleep(5)
            else:
                break

        print("All workers completed!")
    except KeyboardInterrupt:
        print("Interrupted. Terminating workers...")
        for _, proc, _ in procs:
            proc.terminate()
    finally:
        # 不清理 tempdir 以便调试
        print(f"Temp dir kept at: {tempdir}")


if __name__ == "__main__":
    main()
