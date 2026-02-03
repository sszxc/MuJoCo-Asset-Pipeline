#!/usr/bin/env python3
"""
使用 dm_control.mjcf 将「场景模板」与「物体」组合成自包含的 MuJoCo XML，
保存到 asset/scene 下的子文件夹 <scene_template 名>_<物体名>/，内含 <name>.xml 及资产。
默认会给目标物体的根 body 添加 freejoint（可用 --no-freejoint 关闭）。

用法示例：
  python combine_scene.py -o path/to/object.xml -s asset/scene_template/desktop_table_lights.xml
  python combine_scene.py -o object.xml -s asset/scene_template/ground.xml --out-dir asset/scene --no-freejoint
"""

import argparse
import os
import sys


def _ensure_dm_control():
    try:
        from dm_control import mjcf
        return mjcf
    except ImportError:
        print("错误: 未找到 dm_control，请安装: pip install dm_control", file=sys.stderr)
        sys.exit(1)


def _stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path.rstrip("/")))[0]


def _object_name_from_path(object_path: str) -> str:
    """从物体路径得到用于文件名的物体名：若文件名为 model.xml 等通用名则用父目录名，否则用文件名 stem。"""
    p = os.path.abspath(object_path)
    name = _stem(p)
    parent = os.path.basename(os.path.dirname(p))
    if name.lower() in ("model", "scene", "object", "mesh") and parent and parent != ".":
        return parent
    return name


def _ensure_freejoint(obj):
    """给物体的根 body 默认添加 freejoint（若尚未有关节）。"""
    try:
        bodies = obj.worldbody.find_all("body")
    except Exception:
        bodies = []
    if not bodies:
        return
    first_body = bodies[0]
    has_joint = False
    try:
        if first_body.find_all("joint") or first_body.find_all("freejoint"):
            has_joint = True
    except Exception:
        pass
    if not has_joint:
        first_body.add("freejoint")


def combine_scene(
    scene_template_path: str,
    object_path: str,
    out_dir: str,
    spawn_pos=(0.0, 0.0, 0.45),
    spawn_euler=(0.0, 0.0, 0.0),
    add_freejoint=True,
):
    """
    将场景模板与物体用 mjcf 组合，生成自包含 XML 和资产到 out_dir。

    - scene_template_path: 桌面场景 XML（可含桌子、灯光等）
    - object_path: 物体 MuJoCo XML 路径
    - out_dir: 输出根目录（scene 文件夹），实际写入其子目录 <template>_<object>/ 下
    - spawn_pos / spawn_euler: 物体在场景中的位姿（默认略高于桌面）
    - add_freejoint: 是否给目标物体的根 body 添加 freejoint（默认 True）
    """
    mjcf = _ensure_dm_control()

    scene_template_path = os.path.abspath(scene_template_path)
    object_path = os.path.abspath(object_path)
    out_root = os.path.abspath(out_dir)

    if not os.path.isfile(scene_template_path):
        raise FileNotFoundError(f"场景模板不存在: {scene_template_path}")
    if not os.path.isfile(object_path):
        raise FileNotFoundError(f"物体 XML 不存在: {object_path}")

    template_name = _stem(scene_template_path)
    object_name = _object_name_from_path(object_path)
    out_basename = f"{template_name}_{object_name}"
    # 默认保存到 asset/scene 下的子文件夹 <template>_<object>/
    out_dir = os.path.join(out_root, out_basename)
    os.makedirs(out_dir, exist_ok=True)

    # 1. 加载桌面场景和物体模型
    arena = mjcf.from_path(scene_template_path)
    obj = mjcf.from_path(object_path)

    # 3. 将物体附加到场景：需要 freejoint 时附加到 worldbody（顶层），否则附加到 site
    # 原因：attach 会在父元素下创建 attachment frame；若附加到 site，freejoint 会落在该 frame 下，
    # 而 MuJoCo 要求 freejoint 必须在顶层 body，故需附加到 worldbody，使 attachment frame 本身为顶层。
    if add_freejoint:
        # 附加到 worldbody，attachment frame 即为顶层 body，可合法添加 freejoint
        attachment_frame = arena.worldbody.attach(obj)
        attachment_frame.pos = spawn_pos
        attachment_frame.euler = spawn_euler
        attachment_frame.add("freejoint")
    else:
        # 不需要 freejoint 时保持原有逻辑：在 site 上设置位姿并附加物体
        spawn_site = arena.worldbody.add(
            "site",
            name="spawn_site_0",
            pos=spawn_pos,
            euler=spawn_euler,
        )
        spawn_site.attach(obj)

    # 4. 生成组合后的 XML 和资产
    combined_xml = arena.to_xml_string()
    combined_assets = arena.get_assets()

    # 5. 保存自包含 XML 到 scene 子目录
    out_xml_path = os.path.join(out_dir, f"{out_basename}.xml")
    with open(out_xml_path, "w", encoding="utf-8") as f:
        f.write(combined_xml)

    # 6. 保存资产文件（mesh、texture 等），保持相对路径以便 XML 引用正确
    for asset_name, asset_content in combined_assets.items():
        target = os.path.join(out_dir, asset_name)
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target, "wb") as f:
            f.write(asset_content)

    return out_xml_path, out_basename, len(combined_assets)


def main():
    # 默认输出到 asset/scene 下的子文件夹 <template>_<object>/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_scene_dir = os.path.join(script_dir, "asset", "scene")

    parser = argparse.ArgumentParser(
        description="将场景模板与物体用 MJCF 组合成自包含 XML，保存到 scene 子目录。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-o", "--object",
        required=True,
        help="物体 MuJoCo XML 路径",
    )
    parser.add_argument(
        "-s", "--scene-template",
        required=True,
        help="场景模板 XML 路径（如 asset/scene_template/desktop_table_lights.xml）",
    )
    parser.add_argument(
        "--out-dir",
        default=default_scene_dir,
        help="输出根目录（默认 asset/scene），实际写入其子文件夹 <template>_<object>/",
    )
    parser.add_argument(
        "--no-freejoint",
        action="store_true",
        help="不给目标物体添加 freejoint",
    )
    parser.add_argument(
        "--spawn-pos",
        type=float,
        nargs=3,
        default=[0.0, 0.0, 0.45],
        metavar=("X", "Y", "Z"),
        help="物体生成位置 (x y z)，默认 0 0 0.45",
    )
    parser.add_argument(
        "--spawn-euler",
        type=float,
        nargs=3,
        default=[0.0, 0.0, 0.0],
        metavar=("RX", "RY", "RZ"),
        help="物体生成欧拉角 (弧度)，默认 0 0 0",
    )
    args = parser.parse_args()

    try:
        out_xml_path, out_basename, n_assets = combine_scene(
            scene_template_path=args.scene_template,
            object_path=args.object,
            out_dir=args.out_dir,
            spawn_pos=tuple(args.spawn_pos),
            spawn_euler=tuple(args.spawn_euler),
            add_freejoint=not args.no_freejoint,
        )
        print(f"已生成: {out_xml_path}")
        print(f"场景名: {out_basename}, 资产文件数: {n_assets}")
    except FileNotFoundError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
