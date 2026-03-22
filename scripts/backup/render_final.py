import os
import glob
import argparse
import pyvista as pv
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.StlAPI import StlAPI_Writer
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
pv.start_xvfb()

def step_to_mesh(step_path):
    """将 STEP 文件转换为 PyVista 可读取的 Mesh 对象"""
    # 1. 使用 OCC 读取 STEP
    reader = STEPControl_Reader()
    if reader.ReadFile(step_path) != 1:
        return None
    reader.TransferRoot()
    shape = reader.Shape()

    # 2. 网格化 (Meshing) - 这一步是渲染的前提
    # 线性偏离值越小，网格越精细，圆弧越平滑
    mesh_gen = BRepMesh_IncrementalMesh(shape, 0.1)
    mesh_gen.Perform()

    # 3. 导出到临时 STL 并用 PyVista 加载
    temp_stl = "temp_render.stl"
    stl_writer = StlAPI_Writer()
    stl_writer.Write(shape, temp_stl)
    
    mesh = pv.read(temp_stl)
    if os.path.exists(temp_stl):
        os.remove(temp_stl)
    return mesh

def render_8_views(mesh, file_basename, save_dir):
    """PyVista 核心渲染逻辑"""
    plotter = pv.Plotter(off_screen=True, window_size=[224, 224])
    plotter.background_color = "white"
    
    # 样式：浅灰物体 + 加粗黑边 (消隐自动开启)
    plotter.add_mesh(
        mesh, 
        color="#E0E0E0", 
        show_edges=True, 
        edge_color="black", 
        line_width=3,
        lighting=True
    )

    # 定义 8 个角点视角
    directions = [(x, y, z) for x in [-1, 1] for y in [-1, 1] for z in [-1, 1]]

    for i, vec in enumerate(directions):
        # 设置相机：位置，焦点(原点)，上方向
        plotter.camera_position = [vec, (0, 0, 0), (0, 0, 1)]
        plotter.reset_camera()
        
        save_path = os.path.join(save_dir, f"{file_basename}_{i:03d}.png")
        plotter.screenshot(save_path)
    
    plotter.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', type=str, default='datasets/Omni-CAD/json_step')
    parser.add_argument('--num', type=int, default=2)
    parser.add_argument('-o', '--outputs', type=str, default='datasets/Omni-CAD/render_test_img')
    args = parser.parse_args()

    step_files = sorted(glob.glob(os.path.join(args.src, "**/*.step"), recursive=True))
    
    for f in step_files[:args.num]:
        rel_path = os.path.relpath(os.path.dirname(f), args.src)
        out_dir = os.path.join(args.outputs, rel_path)
        os.makedirs(out_dir, exist_ok=True)
        
        base_name = os.path.basename(f).split('.')[0]
        print(f"Processing: {base_name}")
        
        # 执行转换
        mesh_obj = step_to_mesh(f)
        if mesh_obj:
            # 执行渲染
            render_8_views(mesh_obj, base_name, out_dir)
        else:
            print(f"Failed to convert {f}")

    print(f"\n渲染完成。请查看目录: {args.outputs}")
