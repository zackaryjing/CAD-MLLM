#!/usr/bin/env python3
"""
简洁调度器
功能：
 - 扫描 src 下所有 .ply
 - 跳过已完成（8 张图都存在）
 - 将剩余文件均匀分配到 N 个 worker（round-robin）
 - 为每个 worker 写文件列表并用 blender -b --python worker_wrapper.py 启动
 - 如果 worker 失败，重新过滤该 worker 的文件列表（只保留未完成项）并在未超过 max_retries 时重试
"""
import os
import sys
import glob
import argparse
import tempfile
import shutil
import subprocess
import time
from pathlib import Path

def find_ply(src):
    return sorted(glob.glob(os.path.join(src, "**", "*.ply"), recursive=True))

def ply_completed(ply_path, output_dir, src_dir):
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
    rem = []
    done = 0
    for f in files:
        if ply_completed(f, output_dir, src_dir):
            done += 1
        else:
            rem.append(f)
    return rem, done

def distribute(files, n):
    lists = [[] for _ in range(n)]
    for i, f in enumerate(files):
        lists[i % n].append(f)
    return lists

def write_list(files, path):
    with open(path, 'w') as f:
        for p in files:
            f.write(p + '\n')

def launch_worker(worker_id, list_path, blender, worker_script, src, outputs, log_dir, retry):
    log_path = os.path.join(log_dir, f"worker_{worker_id}.log")
    env = os.environ.copy()
    env['WORKER_FILE_LIST'] = list_path
    env['WORKER_ID'] = str(worker_id)
    env['WORKER_SRC'] = src
    env['WORKER_OUTPUTS'] = outputs
    env['WORKER_RETRY_COUNT'] = str(retry)
    cmd = [blender, "-b", "--python", worker_script]
    # ensure log dir exists
    os.makedirs(log_dir, exist_ok=True)
    lf = open(log_path, 'a', buffering=1)
    print(f"Launching worker {worker_id} (retry {retry}) -> {log_path}")
    proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env)
    return proc, log_path, lf

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--src", type=str, required=True)
    p.add_argument("--outputs", type=str, required=True)
    p.add_argument("--blender", type=str, default="blender")
    p.add_argument("--worker-script", type=str, default="worker_wrapper.py",
                   help="脚本位于同目录，Blender 将运行它 (不要修改 core render)")
    p.add_argument("--log-dir", type=str, default="./logs")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    src = os.path.abspath(args.src)
    outputs = os.path.abspath(args.outputs)
    worker_script = os.path.abspath(args.worker_script)
    blender = args.blender

    os.makedirs(outputs, exist_ok=True)
    os.makedirs(args.log_dir, exist_ok=True)

    all_ply = find_ply(src)
    if not all_ply:
        print("No PLY files found.")
        return

    remaining, done = filter_completed(all_ply, outputs, src)
    print(f"Found {len(all_ply)} ply, done={done}, remaining={len(remaining)}")
    if not remaining:
        print("All done.")
        return

    lists = distribute(remaining, args.workers)
    if args.dry_run:
        for i, lst in enumerate(lists):
            if lst:
                print(f"Worker {i}: {len(lst)} files")
        return

    tempdir = tempfile.mkdtemp(prefix="ply_sched_")
    procs = {}  # worker_id -> dict with proc, list_path, retry, log_file
    for i, lst in enumerate(lists):
        if not lst:
            continue
        lp = os.path.join(tempdir, f"worker_{i}.txt")
        write_list(lst, lp)
        proc, log_path, lf = launch_worker(i, lp, blender, worker_script, src, outputs, args.log_dir, retry=0)
        procs[i] = {'proc': proc, 'list': lp, 'retry': 0, 'log': lf}

    failed_workers = set()
    # wait loop
    try:
        while procs:
            to_remove = []
            for wid, info in list(procs.items()):
                proc = info['proc']
                ret = proc.poll()
                if ret is None:
                    continue  # still running
                # process ended
                info['log'].close()
                if ret == 0:
                    print(f"Worker {wid} finished OK")
                    to_remove.append(wid)
                else:
                    print(f"Worker {wid} FAILED (exit {ret})")
                    # read its file list, filter completed, retry if allowed
                    with open(info['list'], 'r') as f:
                        files = [l.strip() for l in f if l.strip()]
                    remaining_files = [f for f in files if not ply_completed(f, outputs, src)]
                    if remaining_files and info['retry'] < args.max_retries:
                        info['retry'] += 1
                        new_list = info['list'] + f".retry{info['retry']}"
                        write_list(remaining_files, new_list)
                        proc2, log_path, lf2 = launch_worker(wid, new_list, blender, worker_script, src, outputs, args.log_dir, retry=info['retry'])
                        # replace entry
                        procs[wid] = {'proc': proc2, 'list': new_list, 'retry': info['retry'], 'log': lf2}
                        print(f"  -> Retried worker {wid} ({len(remaining_files)} files), attempt {info['retry']}/{args.max_retries}")
                    else:
                        if remaining_files:
                            print(f"  -> Max retries reached for worker {wid}, skipping {len(remaining_files)} files")
                        failed_workers.add(wid)
                        to_remove.append(wid)
            for wid in to_remove:
                procs.pop(wid, None)
            if procs:
                time.sleep(3)
    finally:
        # ensure all opened logs closed and subprocesses cleaned
        for info in procs.values():
            try:
                info['log'].close()
            except Exception:
                pass
            try:
                info['proc'].terminate()
            except Exception:
                pass
        # do not remove tempdir if debugging desired
        shutil.rmtree(tempdir)

    total_launched = len(lists)
    success_count = total_launched - len(failed_workers)
    print("\nSUMMARY")
    print(f"Total workers launched: {total_launched}")
    print(f"Successful workers: {success_count}")
    if failed_workers:
        print(f"Failed workers: {len(failed_workers)} -> {sorted(list(failed_workers))}")
        print("Check logs in", args.log_dir)
    else:
        print("All workers completed successfully.")

if __name__ == "__main__":
    main()
