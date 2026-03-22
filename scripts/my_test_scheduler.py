#!/usr/bin/env python3
import subprocess
import os

LOG_DIR = "/tmp/blender_test"
BLENDER_LOG = os.path.join(LOG_DIR, "blender.log")
SUCCESS_FILE = os.path.join(LOG_DIR, "worker_success.txt")

os.makedirs(LOG_DIR, exist_ok=True)

# 清理旧文件
if os.path.exists(SUCCESS_FILE):
    os.remove(SUCCESS_FILE)

with open(BLENDER_LOG, "w") as f:
    proc = subprocess.Popen(
        [
            "blender",
            "-b",
            "--python",
            "/root/projects/CAD-MLLM/scripts/my_test_worker.py"
        ],
        stdout=f,
        stderr=subprocess.STDOUT
    )

    ret = proc.wait()

print("blender exit code:", ret)

if ret != 0:
    print("Scheduler: blender process failed")
    exit(1)

if not os.path.exists(SUCCESS_FILE):
    print("Scheduler: worker did not signal success")
    exit(2)

print("Scheduler: worker executed successfully")