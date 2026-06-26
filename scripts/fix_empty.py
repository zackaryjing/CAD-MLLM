import os
import subprocess
from pathlib import Path

# ===== 配置 =====
EMPTY_LIST_FILE = "empty_png.txt"   # 你扫描出来的列表
SRC_DIR = "/root/projects/dm-cad/datasets/dataset_v0/cad_ply"
OUTPUT_DIR = "/root/projects/dm-cad/datasets/dataset_v0/cad_img"
WORKER_SCRIPT = "/root/projects/CAD-MLLM/scripts/render_ply_worker.py"
BLENDER_CMD = "blender"

TMP_LIST = "/tmp/rerender_list.txt"


def png_to_ply(png_path):
    """
    从:
    cad_img/0002/00026320_00013/00026320_00013_007.png

    还原到:
    cad_ply/0002/00026320_00013.ply
    """
    png_path = Path(png_path)

    stem = png_path.stem  # 00026320_00013_007
    base = "_".join(stem.split("_")[:-1])  # 去掉 _007

    subdir = png_path.parts[-3]  # 0002

    ply_path = Path(SRC_DIR) / subdir / f"{base}.ply"
    return str(ply_path)


def get_output_dir(png_path):
    """
    返回整个样本目录（需要删掉重跑）
    """
    return str(Path(png_path).parent)


def main():
    with open(EMPTY_LIST_FILE, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    # 提取 ply 去重
    ply_set = set()
    for line in lines:
        if "[EMPTY]" in line:
            png_path = line.split(" ", 1)[1]
            ply = png_to_ply(png_path)
            ply_set.add(ply)

    ply_list = sorted(ply_set)

    print(f"Need to rerender {len(ply_list)} samples")

    # 删除旧输出（避免 is_completed 误判）
    for line in lines:
        if "[EMPTY]" in line:
            png_path = line.split(" ", 1)[1]
            out_dir = get_output_dir(png_path)
            if os.path.exists(out_dir):
                print(f"Removing {out_dir}")
                subprocess.run(["rm", "-rf", out_dir])

    # 写临时 list
    with open(TMP_LIST, "w") as f:
        for p in ply_list:
            f.write(p + "\n")

    print("Start rerendering...")

    env = os.environ.copy()
    env["WORKER_FILE_LIST"] = TMP_LIST
    env["WORKER_ID"] = "fix"
    env["WORKER_SRC"] = SRC_DIR
    env["WORKER_OUTPUTS"] = OUTPUT_DIR
    env["WORKER_LOG_DIR"] = "/tmp"

    cmd = [BLENDER_CMD, "-b", "--python", WORKER_SCRIPT]

    subprocess.run(cmd, env=env)

    print("Done.")


if __name__ == "__main__":
    main()
