#!/usr/bin/env python3
"""
将 YCB 数据集中 google_16k 下的 textured.obj 转为 MuJoCo XML，
并整理到 asset/ycb_xml/<物体文件夹>/ 下。

流程：
1. 只处理 asset/ycb 下存在 google_16k/textured.obj 的物体，否则跳过
2. 拷贝 textured.obj 为「序号_名字.obj」到临时目录，避免冲突
3. 用 obj2mjcf 转换（默认 --decompose）
4. 将生成的 XML 移动到 asset/ycb_xml/<物体文件夹>/
5. 删除临时目录及拷贝的 obj
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


# 默认路径（相对项目根）
DEFAULT_YCB_ROOT = os.path.join("asset", "ycb")
DEFAULT_YCB_XML_ROOT = os.path.join("asset", "ycb_xml")
GOOGLE_16K = "google_16k"
TEXTURED_OBJ = "textured.obj"
TEXTURED_MTL = "textured.mtl"
TEXTURE_PNG = "texture_map.png"


def get_object_folders(ycb_root):
    """列出 asset/ycb 下所有物体文件夹（如 003_cracker_box）。"""
    if not os.path.isdir(ycb_root):
        return []
    folders = []
    for name in sorted(os.listdir(ycb_root)):
        path = os.path.join(ycb_root, name)
        if os.path.isdir(path) and not name.startswith("."):
            folders.append(name)
    return folders


def has_google_16k_textured(ycb_root, folder):
    """检查是否存在 google_16k/textured.obj。"""
    obj_path = os.path.join(ycb_root, folder, GOOGLE_16K, TEXTURED_OBJ)
    return os.path.isfile(obj_path)


def copy_assets_to_temp(ycb_root, folder, temp_dir):
    """
    将 google_16k 下的 textured.obj 拷贝为 <folder>.obj 到 temp_dir，
    并拷贝 textured.mtl 和 texture_map.png（若存在）以便材质正确加载。
    返回临时目录中 obj 的 basename（即 folder，用于 --obj-filter）。
    """
    src_dir = os.path.join(ycb_root, folder, GOOGLE_16K)
    obj_name = f"{folder}.obj"
    dst_obj = os.path.join(temp_dir, obj_name)
    shutil.copy2(os.path.join(src_dir, TEXTURED_OBJ), dst_obj)

    mtl_src = os.path.join(src_dir, TEXTURED_MTL)
    if os.path.isfile(mtl_src):
        shutil.copy2(mtl_src, os.path.join(temp_dir, TEXTURED_MTL))
    png_src = os.path.join(src_dir, TEXTURE_PNG)
    if os.path.isfile(png_src):
        shutil.copy2(png_src, os.path.join(temp_dir, TEXTURE_PNG))

    return folder


def run_obj2mjcf(obj_dir, obj_filter, decompose=True):
    """在 obj_dir 下执行 obj2mjcf，只处理匹配 obj_filter 的 obj。"""
    cmd = [
        "obj2mjcf",
        "--obj_dir", obj_dir,
        "--obj-filter", obj_filter,
        "--save_mjcf",
    ]
    if decompose:
        cmd.append("--decompose")
    result = subprocess.run(cmd, cwd=obj_dir)
    return result.returncode == 0


def move_obj2mjcf_output_to_ycb_xml(temp_dir, ycb_xml_root, folder):
    """
    将 obj2mjcf 在 temp_dir 下生成的子文件夹（与 obj 基名同名的目录）
    内的所有文件拷贝到 ycb_xml_root/<folder>/。
    obj2mjcf 会把结果放在 obj 同路径下的子文件夹里，如 035_power_drill/ 或 textured/。
    """
    dest_dir = os.path.join(ycb_xml_root, folder)
    os.makedirs(dest_dir, exist_ok=True)
    # obj 基名 = folder（我们拷贝为 <folder>.obj），子文件夹名即 folder
    output_subdir = os.path.join(temp_dir, folder)
    if not os.path.isdir(output_subdir):
        return []
    copied = []
    for name in os.listdir(output_subdir):
        src = os.path.join(output_subdir, name)
        dst = os.path.join(dest_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            copied.append(name)
        elif os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
            copied.append(name + "/")
    return copied


def main():
    parser = argparse.ArgumentParser(
        description="将 YCB 的 google_16k/textured.obj 转为 MuJoCo XML 到 asset/ycb_xml"
    )
    parser.add_argument(
        "-y", "--ycb-root",
        default=DEFAULT_YCB_ROOT,
        help="YCB 物体根目录 (默认: %(default)s)",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_YCB_XML_ROOT,
        help="XML 输出根目录 (默认: %(default)s)",
    )
    parser.add_argument(
        "--no-decompose",
        action="store_true",
        help="不使用 --decompose",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="只打印会处理的物体，不执行转换与移动",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="只处理前 N 个物体（调试用）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="等价于 --limit 5，仅测试前 5 个物体",
    )
    args = parser.parse_args()
    if args.debug:
        args.limit = 5

    ycb_root = os.path.abspath(args.ycb_root)
    ycb_xml_root = os.path.abspath(args.output)

    if not os.path.isdir(ycb_root):
        print("错误: YCB 根目录不存在:", ycb_root)
        sys.exit(1)

    if not args.dry_run and shutil.which("obj2mjcf") is None:
        print("错误: 未找到 obj2mjcf，请先安装: pip install obj2mjcf")
        sys.exit(1)

    folders = get_object_folders(ycb_root)
    to_process = [f for f in folders if has_google_16k_textured(ycb_root, f)]
    skipped = [f for f in folders if f not in to_process]

    if skipped:
        print("跳过（无 google_16k/textured.obj）:", ", ".join(skipped))
    if args.limit is not None:
        to_process = to_process[: args.limit]
        print("调试: 仅处理前", args.limit, "个物体")
    print("待处理:", len(to_process), "个:", ", ".join(to_process) if to_process else "无")

    if args.dry_run:
        return

    os.makedirs(ycb_xml_root, exist_ok=True)
    failed = []

    for i, folder in enumerate(to_process, 1):
        print(f"\n[{i}/{len(to_process)}] {folder}")
        with tempfile.TemporaryDirectory(prefix="obj2mjcf_") as temp_dir:
            copy_assets_to_temp(ycb_root, folder, temp_dir)
            ok = run_obj2mjcf(temp_dir, folder, decompose=not args.no_decompose)
            if not ok:
                failed.append(folder)
                continue
            copied = move_obj2mjcf_output_to_ycb_xml(temp_dir, ycb_xml_root, folder)
            print("  已拷贝输出文件:", copied if len(copied) <= 10 else copied[:10] + [f"... 共 {len(copied)} 个"])

    if failed:
        print("\n转换失败的物体:", failed)
        sys.exit(1)
    print("\n全部完成。XML 输出目录:", ycb_xml_root)


if __name__ == "__main__":
    main()
