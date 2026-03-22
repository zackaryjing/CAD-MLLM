import os
import sys
import traceback
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict

import gradio as gr
import h5py
import numpy as np
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Extend.DataExchange import write_step_file, write_stl_file

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))
from cadlib.visualize import vec2CADsolid


PYTHON_BIN = sys.executable
DEFAULT_PROJ_DIR = "proj_log"
DEFAULT_EXP_NAME = "pretrained"
DEFAULT_AE_CKPT = "1000"
DEFAULT_LGAN_CKPT = "200000"
DEFAULT_N_SAMPLES = 9000
DEFAULT_GPU = "0"


def run_cmd(args: List[str]) -> Tuple[bool, str]:
    proc = subprocess.run(
        args,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    output = proc.stdout if proc.stdout else ""
    if len(output) > 12000:
        output = output[-12000:]
    ok = proc.returncode == 0
    return ok, output


def build_paths(
    proj_dir: str,
    exp_name: str,
    ae_ckpt: str,
    lgan_ckpt: str,
    n_samples: int,
) -> Dict[str, Path]:
    proj_root = ROOT_DIR / proj_dir
    z_rel = Path(
        f"{proj_dir}/{exp_name}/lgan_{ae_ckpt}/results/fake_z_ckpt{lgan_ckpt}_num{n_samples}.h5"
    )
    z_abs = ROOT_DIR / z_rel
    dec_dir = Path(str(z_abs).rsplit(".", 1)[0] + "_dec")
    render_root = dec_dir / "_web_render"
    step_dir = render_root / "step"
    stl_dir = render_root / "stl"
    return {
        "proj_root": proj_root,
        "z_rel": z_rel,
        "z_abs": z_abs,
        "dec_dir": dec_dir,
        "render_root": render_root,
        "step_dir": step_dir,
        "stl_dir": stl_dir,
    }


def sorted_h5_files(dec_dir: Path) -> List[Path]:
    files = list(dec_dir.glob("*.h5"))

    def sort_key(p: Path):
        stem = p.stem
        return (0, int(stem)) if stem.isdigit() else (1, stem)

    return sorted(files, key=sort_key)


def export_h5_to_step_stl(
    src_h5: Path,
    step_path: Path,
    stl_path: Path,
    filter_invalid: bool = True,
) -> Tuple[bool, str]:
    try:
        with h5py.File(src_h5, "r") as fp:
            out_vec = fp["out_vec"][:].astype(np.float64)
        shape = vec2CADsolid(out_vec)
        if filter_invalid:
            analyzer = BRepCheck_Analyzer(shape)
            if not analyzer.IsValid():
                return False, "invalid shape"
        step_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        write_step_file(shape, str(step_path))
        write_stl_file(shape, str(stl_path))
        return True, ""
    except Exception as e:
        return False, str(e)


def export_decoded_folder(
    dec_dir: Path,
    step_dir: Path,
    stl_dir: Path,
    overwrite: bool = False,
    max_export: int = -1,
    filter_invalid: bool = True,
) -> Dict[str, object]:
    h5_files = sorted_h5_files(dec_dir)
    if max_export is not None and max_export > 0:
        h5_files = h5_files[:max_export]

    total = len(h5_files)
    success = 0
    failed = 0
    failures = []

    for h5_path in h5_files:
        step_path = step_dir / f"{h5_path.stem}.step"
        stl_path = stl_dir / f"{h5_path.stem}.stl"
        if not overwrite and step_path.exists() and stl_path.exists():
            success += 1
            continue

        ok, msg = export_h5_to_step_stl(
            h5_path, step_path, stl_path, filter_invalid=filter_invalid
        )
        if ok:
            success += 1
        else:
            failed += 1
            if len(failures) < 20:
                failures.append(f"{h5_path.name}: {msg}")

    ratio = 0.0 if total == 0 else success / total
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "ratio": ratio,
        "failures": failures,
    }


def list_available_stl(stl_dir: Path) -> List[Path]:
    files = list(stl_dir.glob("*.stl"))

    def sort_key(p: Path):
        stem = p.stem
        return (0, int(stem)) if stem.isdigit() else (1, stem)

    return sorted(files, key=sort_key)


def format_stats(paths: Dict[str, Path], export_stats: Dict[str, object]) -> str:
    total = int(export_stats.get("total", 0))
    success = int(export_stats.get("success", 0))
    failed = int(export_stats.get("failed", 0))
    ratio = float(export_stats.get("ratio", 0.0))
    failures = export_stats.get("failures", [])

    md = []
    md.append("### 生成与导出统计")
    md.append(f"- 解码目录: `{paths['dec_dir']}`")
    md.append(f"- 可视化目录: `{paths['render_root']}`")
    md.append(f"- 总数: **{total}**")
    md.append(f"- 成功: **{success}**")
    md.append(f"- 失败: **{failed}**")
    md.append(f"- 成功率: **{ratio:.2%}**")
    if failures:
        md.append("- 失败样例(最多20条):")
        for line in failures:
            md.append(f"  - `{line}`")
    return "\n".join(md)


def make_dropdown_choices(stl_files: List[Path]):
    return [(p.name, str(p)) for p in stl_files]


def run_generation(
    proj_dir: str,
    exp_name: str,
    ae_ckpt: str,
    lgan_ckpt: str,
    n_samples: int,
    gpu_id: str,
    overwrite_export: bool,
    max_export: int,
    filter_invalid: bool,
):
    n_samples = int(n_samples)
    max_export = int(max_export)
    logs = []
    paths = build_paths(proj_dir, exp_name, ae_ckpt, lgan_ckpt, n_samples)

    lgan_cmd = [
        PYTHON_BIN,
        "lgan.py",
        "--exp_name",
        exp_name,
        "--ae_ckpt",
        ae_ckpt,
        "--ckpt",
        lgan_ckpt,
        "--test",
        "--n_samples",
        str(n_samples),
        "-g",
        gpu_id,
    ]
    ok, out = run_cmd(lgan_cmd)
    logs.append("[lgan.py]\n" + out)
    if not ok:
        stl_files = list_available_stl(paths["stl_dir"]) if paths["stl_dir"].exists() else []
        choices = make_dropdown_choices(stl_files)
        return (
            "### 生成失败\n请检查日志。",
            "\n\n".join(logs),
            gr.update(choices=choices, value=choices[0][1] if choices else None),
            [str(p) for p in stl_files],
        )

    dec_cmd = [
        PYTHON_BIN,
        "test.py",
        "--exp_name",
        exp_name,
        "--mode",
        "dec",
        "--ckpt",
        ae_ckpt,
        "--z_path",
        str(paths["z_rel"]),
        "-g",
        gpu_id,
    ]
    ok, out = run_cmd(dec_cmd)
    logs.append("[test.py --mode dec]\n" + out)
    if not ok:
        stl_files = list_available_stl(paths["stl_dir"]) if paths["stl_dir"].exists() else []
        choices = make_dropdown_choices(stl_files)
        return (
            "### 解码失败\n请检查日志。",
            "\n\n".join(logs),
            gr.update(choices=choices, value=choices[0][1] if choices else None),
            [str(p) for p in stl_files],
        )

    export_stats = export_decoded_folder(
        dec_dir=paths["dec_dir"],
        step_dir=paths["step_dir"],
        stl_dir=paths["stl_dir"],
        overwrite=overwrite_export,
        max_export=max_export,
        filter_invalid=filter_invalid,
    )
    stats_md = format_stats(paths, export_stats)

    stl_files = list_available_stl(paths["stl_dir"])
    choices = make_dropdown_choices(stl_files)
    return (
        stats_md,
        "\n\n".join(logs),
        gr.update(choices=choices, value=choices[0][1] if choices else None),
        [str(p) for p in stl_files],
    )


def refresh_only(
    proj_dir: str,
    exp_name: str,
    ae_ckpt: str,
    lgan_ckpt: str,
    n_samples: int,
    overwrite_export: bool,
    max_export: int,
    filter_invalid: bool,
):
    n_samples = int(n_samples)
    max_export = int(max_export)
    paths = build_paths(proj_dir, exp_name, ae_ckpt, lgan_ckpt, n_samples)
    if not paths["dec_dir"].exists():
        return (
            "### 未找到解码目录\n请先执行生成。",
            gr.update(choices=[], value=None),
            [],
        )

    export_stats = export_decoded_folder(
        dec_dir=paths["dec_dir"],
        step_dir=paths["step_dir"],
        stl_dir=paths["stl_dir"],
        overwrite=overwrite_export,
        max_export=max_export,
        filter_invalid=filter_invalid,
    )
    stats_md = format_stats(paths, export_stats)
    stl_files = list_available_stl(paths["stl_dir"])
    choices = make_dropdown_choices(stl_files)
    return (
        stats_md,
        gr.update(choices=choices, value=choices[0][1] if choices else None),
        [str(p) for p in stl_files],
    )


def show_selected_model(selected_path: str):
    if not selected_path:
        return None, "未选择模型。"
    p = Path(selected_path)
    if not p.exists():
        return None, f"文件不存在: `{selected_path}`"
    info = f"- 当前模型: `{p.name}`\n- 路径: `{p}`"
    return str(p), info


def browse_relative(model_list: List[str], selected_path: str, delta: int):
    if not model_list:
        return gr.update(), None, "当前没有可浏览模型。"
    if not selected_path or selected_path not in model_list:
        idx = 0
    else:
        idx = model_list.index(selected_path)
    idx = (idx + delta) % len(model_list)
    new_path = model_list[idx]
    model_path, info = show_selected_model(new_path)
    return gr.update(value=new_path), model_path, info


def build_demo():
    with gr.Blocks(title="DeepCAD 生成与可视化") as demo:
        gr.Markdown(
            """
            # DeepCAD Web App
            一键执行 `lgan -> decode`，并导出 `step + stl` 用于网页端 3D 浏览。
            """
        )

        with gr.Row():
            proj_dir = gr.Textbox(label="proj_dir", value=DEFAULT_PROJ_DIR)
            exp_name = gr.Textbox(label="exp_name", value=DEFAULT_EXP_NAME)
            ae_ckpt = gr.Textbox(label="ae_ckpt", value=DEFAULT_AE_CKPT)
            lgan_ckpt = gr.Textbox(label="lgan_ckpt", value=DEFAULT_LGAN_CKPT)
            gpu_id = gr.Textbox(label="gpu_id", value=DEFAULT_GPU)

        with gr.Row():
            n_samples = gr.Number(label="n_samples", value=DEFAULT_N_SAMPLES, precision=0)
            max_export = gr.Number(
                label="max_export (-1: all)",
                value=300,
                precision=0,
            )
            overwrite_export = gr.Checkbox(label="overwrite_export", value=False)
            filter_invalid = gr.Checkbox(label="filter_invalid", value=True)

        with gr.Row():
            run_btn = gr.Button("一键生成并刷新", variant="primary")
            refresh_btn = gr.Button("仅刷新导出与统计")

        stats_md = gr.Markdown("### 等待执行")
        logs = gr.Textbox(label="执行日志(尾部截断)", lines=16)

        gr.Markdown("## 模型浏览")
        model_list_state = gr.State([])
        with gr.Row():
            model_selector = gr.Dropdown(
                label="选择模型(STL)",
                choices=[],
                value=None,
                allow_custom_value=False,
            )
            prev_btn = gr.Button("上一模型")
            next_btn = gr.Button("下一模型")
        model_info = gr.Markdown("未选择模型。")
        viewer = gr.Model3D(label="CAD 预览", clear_color=[0.95, 0.95, 0.95, 1.0])

        run_btn.click(
            fn=run_generation,
            inputs=[
                proj_dir,
                exp_name,
                ae_ckpt,
                lgan_ckpt,
                n_samples,
                gpu_id,
                overwrite_export,
                max_export,
                filter_invalid,
            ],
            outputs=[stats_md, logs, model_selector, model_list_state],
        )

        refresh_btn.click(
            fn=refresh_only,
            inputs=[
                proj_dir,
                exp_name,
                ae_ckpt,
                lgan_ckpt,
                n_samples,
                overwrite_export,
                max_export,
                filter_invalid,
            ],
            outputs=[stats_md, model_selector, model_list_state],
        )

        model_selector.change(
            fn=show_selected_model,
            inputs=[model_selector],
            outputs=[viewer, model_info],
        )

        prev_btn.click(
            fn=lambda mlist, selected: browse_relative(mlist, selected, -1),
            inputs=[model_list_state, model_selector],
            outputs=[model_selector, viewer, model_info],
        )

        next_btn.click(
            fn=lambda mlist, selected: browse_relative(mlist, selected, 1),
            inputs=[model_list_state, model_selector],
            outputs=[model_selector, viewer, model_info],
        )

    return demo


if __name__ == "__main__":
    try:
        app = build_demo()
        app.launch(server_name="0.0.0.0", share=False, server_port=7862, show_api=False)
    except Exception:
        print(traceback.format_exc())
