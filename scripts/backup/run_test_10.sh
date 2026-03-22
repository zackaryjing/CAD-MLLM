#!/bin/bash
# 测试渲染 10 个随机选取的 PLY 文件

set -e

echo "=== Testing 10 random PLY files ==="
echo ""

# 文件 1
echo "[1/10] 0074/00744804_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0074/00744804_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0074/00744804_00001

# 文件 2
echo "[2/10] 0010/00105391_00010.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0010/00105391_00010.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0010/00105391_00010

# 文件 3
echo "[3/10] 0002/00027860_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0002/00027860_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0002/00027860_00001

# 文件 4
echo "[4/10] 0086/00861973_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0086/00861973_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0086/00861973_00001

# 文件 5
echo "[5/10] 0031/00315701_00009.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0031/00315701_00009.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0031/00315701_00009

# 文件 6
echo "[6/10] 0027/00279029_00005.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0027/00279029_00005.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0027/00279029_00005

# 文件 7
echo "[7/10] 0022/00227548_00002.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0022/00227548_00002.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0022/00227548_00002

# 文件 8
echo "[8/10] 0015/00153373_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0015/00153373_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0015/00153373_00001

# 文件 9
echo "[9/10] 0085/00856290_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0085/00856290_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0085/00856290_00001

# 文件 10
echo "[10/10] 0009/00099331_00001.ply"
blender -b --python /root/projects/CAD-MLLM/scripts/render_ply_single.py -- \
    --ply /root/projects/CAD-MLLM/datasets/Omni-CAD/json_ply/0009/00099331_00001.ply \
    --out /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random/0009/00099331_00001

echo ""
echo "=== All 10 files processed ==="
echo "Output directory: /root/projects/CAD-MLLM/datasets/Omni-CAD/json_img_random"
