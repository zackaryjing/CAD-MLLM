import pyvista as pv
import os, glob, argparse
import trimesh

def render_model(file_path, save_dir, num_views=8):
    file_name = os.path.basename(file_path).split('.')[0]
    
    # 1. 加载模型 (STEP文件通过trimesh/cascadeno转为Mesh)
    # 如果trimesh加载step失败，建议先用你原来的occ脚本把step转成stl
    try:
        mesh_data = trimesh.load(file_path)
        if isinstance(mesh_data, trimesh.Scene):
            mesh = pv.wrap(mesh_data.to_geometry())
        else:
            mesh = pv.wrap(mesh_data)
    except Exception as e:
        print(f"Skip {file_path}: {e}")
        return

    # 2. 设置渲染器 (强制离屏)
    plotter = pv.Plotter(off_screen=True, window_size=[224, 224])
    plotter.background_color = "white"
    
    # 3. 添加模型：设置单色表面 + 加粗黑边 (消隐效果自动包含)
    plotter.add_mesh(
        mesh, 
        color="#D3D3D3",     # 浅灰色表面
        show_edges=True,      # 显示边缘
        edge_color="black",   # 黑色边缘
        line_width=3,         # 加粗边缘
        lighting=True,
        smooth_shading=False  # 保持硬边感
    )

    # 4. 8个视角方向
    directions = [(x, y, z) for x in [-1, 1] for y in [-1, 1] for z in [-1, 1]]

    for i, vec in enumerate(directions):
        plotter.camera_position = [vec, (0, 0, 0), (0, 0, 1)]
        plotter.reset_camera()
        save_path = os.path.join(save_dir, f"{file_name}_{i:03d}.png")
        plotter.screenshot(save_path)

    plotter.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', type=str, default='datasets/Omni-CAD/json_step')
    parser.add_argument('--num', type=int, default=2)
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.src, "**/*.step"), recursive=True))
    for f in files[:args.num]:
        rel_path = os.path.relpath(os.path.dirname(f), args.src)
        out_dir = os.path.join("datasets/Omni-CAD/render_test_img", rel_path)
        os.makedirs(out_dir, exist_ok=True)
        print(f"Rendering: {f}")
        render_model(f, out_dir)
