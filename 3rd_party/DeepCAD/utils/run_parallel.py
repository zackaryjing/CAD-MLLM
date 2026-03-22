import os
import glob
import json
import argparse
import subprocess
from multiprocessing import Pool
from math import ceil

def get_total_files(src, form):
    paths = sorted(glob.glob(os.path.join(src, "**", f"*.{form}"), recursive=True))
    return len(paths)

def run_worker(args):
    idx, num, src, form, outputs, output_form = args
    cmd = [
        "python3", "./export2step.py",
        "--src", src,
        "--form", form,
        "--idx", str(idx),
        "--num", str(num),
        "--output_form", output_form,
    ]
    if outputs:
        cmd += ["-o", outputs]

    print(f"[Worker] idx={idx} num={num} started (pid will be shown below)")
    result = subprocess.run(cmd, capture_output=False)
    print(f"[Worker] idx={idx} finished with returncode={result.returncode}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=str, required=True)
    parser.add_argument("--form", type=str, default="json", choices=["h5", "json"])
    parser.add_argument("--output_form", type=str, default="step", choices=["step", "ply"])
    parser.add_argument("-o", "--outputs", type=str, default=None)
    parser.add_argument("--workers", type=int, default=32, help="number of parallel workers")
    args = parser.parse_args()

    total = get_total_files(args.src, args.form)
    print(f"Total files: {total}, Workers: {args.workers}")

    chunk_size = ceil(total / args.workers)
    tasks = []
    for i in range(args.workers):
        idx = i * chunk_size
        if idx >= total:
            break
        num = min(chunk_size, total - idx)
        tasks.append((idx, num, args.src, args.form, args.outputs, args.output_form))

    print(f"Launching {len(tasks)} workers, chunk_size={chunk_size}")

    with Pool(processes=len(tasks)) as pool:
        pool.map(run_worker, tasks)

    print("All done.")
