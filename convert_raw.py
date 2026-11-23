# -*- coding: utf-8 -*-
"""批量把用户目录里已下载的 .raw 无损封装成 .mp4。

用打过补丁的 core.remux_container：内部会自动处理
  - 工作区内 ffmpeg 的写权限限制（复制副本到 TEMP 重试）
  - subprocess 的 UTF-8 解码
成功后删除 .raw（可选 --keep）。
"""
import argparse
import glob
import io
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\deepseekproject\agedl")
import core  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?", default=r"D:\迅雷下载\video")
    ap.add_argument("--keep", action="store_true", help="保留 .raw 原件")
    ap.add_argument("--ffmpeg", default="")
    a = ap.parse_args()

    ff = core.find_ffmpeg(a.ffmpeg)
    if not ff:
        print("✗ 找不到 ffmpeg")
        return 2
    print(f"ffmpeg: {ff}")
    print(f"版本  : {core.ffmpeg_version(ff)}")
    print(f"目录  : {a.dir}")
    print()

    raws = sorted(glob.glob(os.path.join(a.dir, "*.raw")))
    if not raws:
        print("该目录下没有 .raw 文件")
        return 0

    # 跳过已存在同名 mp4 的
    todo = []
    for r in raws:
        dst = os.path.splitext(r)[0] + ".mp4"
        if os.path.isfile(dst) and os.path.getsize(dst) > 0:
            print(f"  跳过（已有 mp4）: {os.path.basename(dst)}  {os.path.getsize(dst):,} 字节")
            continue
        todo.append(r)

    if not todo:
        print("\n全部已转换完成。")
        return 0

    print(f"待转换 {len(todo)} 个\n" + "-" * 70)
    ok_n = fail_n = 0
    t_all = time.time()

    for i, r in enumerate(todo, 1):
        base = os.path.basename(r)
        dst = os.path.splitext(r)[0] + ".mp4"
        src_size = os.path.getsize(r)
        print(f"[{i}/{len(todo)}] {base}  {src_size:,} 字节")
        t0 = time.time()
        ok = core.remux_container(ff, r, dst, on_log=lambda m: print("   " + m.strip()))
        dt = time.time() - t0
        if ok and os.path.isfile(dst) and os.path.getsize(dst) > 0:
            ok_n += 1
            print(f"   ✓ {os.path.getsize(dst):,} 字节  {dt:.1f}s")
            if not a.keep:
                try:
                    os.remove(r)
                    print("   - 已删除 .raw")
                except OSError as e:
                    print(f"   ! 删除 .raw 失败: {e}")
        else:
            fail_n += 1
            print(f"   ✗ 失败  {dt:.1f}s")

    print("-" * 70)
    print(f"完成：成功 {ok_n}  失败 {fail_n}  用时 {time.time() - t_all:.1f}s")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
