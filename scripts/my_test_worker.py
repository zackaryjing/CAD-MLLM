#!/usr/bin/env python3
import os
import sys

# print("Hello from worker")
print()
sys.stdout.flush()

LOG_DIR = "/tmp/blender_test"
WORKER_LOG = os.path.join(LOG_DIR, "worker.log")
SUCCESS_FILE = os.path.join(LOG_DIR, "worker_success.txt")

os.makedirs(LOG_DIR, exist_ok=True)

def log(msg):
    with open(WORKER_LOG, "a") as f:
        f.write(msg + "\n")
        f.flush()

log("worker started")

# print("Hello from worker")
# sys.stdout.flush()

# 写测试文件
with open(os.path.join(LOG_DIR, "worker_test.txt"), "w") as f:
    f.write("written by worker")

log("test file written")

# 成功标记
with open(SUCCESS_FILE, "w") as f:
    f.write("OK\n")

log("worker finished successfully")
print("end")