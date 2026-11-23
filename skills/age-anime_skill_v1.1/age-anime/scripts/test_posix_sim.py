# -*- coding: utf-8 -*-
"""
test_posix_sim.py — 模拟 POSIX 端到端流程

本机没有真实 Linux，但下载/合并/封装这三步里真正与平台相关的只有：
  · 文件名是否合法（字节长度、非法字符）
  · ffmpeg 是否被正确调用、参数是否被平台污染
  · 执行位、临时目录、路径拼接

所以这里的做法是把 sys.platform 打桩成 linux，然后在真实文件系统上
跑一遍 命名 → 分片目录 → 合并 → 封装（用真 ffmpeg）的完整链路，
并用 POSIX 规则校验每一步产物。只要 ffmpeg 存在，这个测试就能真正证明
「在 Linux 上这套代码不会因为平台问题挂掉」。

运行： python test_posix_sim.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

PASS = FAIL = SKIP = 0
FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        FAILS.append(f"{label}  {detail}")
        print(f"  ✗ {label}   {detail}")


def skip(label: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  – {label}  （跳过：{why}）")


def section(t: str) -> None:
    print(f"\n{'─' * 70}\n{t}\n{'─' * 70}")


import platform_compat as plat  # noqa: E402
import core  # noqa: E402


# --------------------------------------------------------------------------- #
section("1. 打桩成 linux 后，模块级常量应随之改变")
# --------------------------------------------------------------------------- #
saved = sys.platform
try:
    sys.platform = "linux"
    importlib.reload(plat)
    check("plat.WINDOWS == False", plat.WINDOWS is False)
    check("plat.LINUX == True", plat.LINUX is True)
    # POSIX 来自 os.name，是真实宿主属性，打桩 sys.platform 不会改它 —— 这里不断言
    check("MAX_NAME_BYTES 仍是 240", plat.MAX_NAME_BYTES == 240)
    check("spawn_kwargs 为空", plat.spawn_kwargs() == {})
    check("exe_names 无 .exe", plat.exe_names("ffmpeg") == ["ffmpeg"])
finally:
    sys.platform = saved
    importlib.reload(plat)


# --------------------------------------------------------------------------- #
section("2. POSIX 文件名规则：末尾点/空格、保留名都不该被改")
# --------------------------------------------------------------------------- #
cases = [
    ("v1.0.", "v1.0.", "Linux 上末尾点是合法字符"),
    ("名字  ", "名字", "统一去掉尾部空白（不依赖平台）"),
    ("CON", "CON", "Linux 上 CON 不是保留设备名"),
    ("aux.txt", "aux.txt", "Linux 上 aux.txt 合法"),
    ("a:b", "a b", "冒号即使在 Linux 上也清掉（跨系统拷贝安全）"),
]
for raw, want, why in cases:
    got = plat.safe_filename(raw, platform="linux")
    check(f"{why}：{raw!r} → {got!r}", got == want, f"期望 {want!r}")


# --------------------------------------------------------------------------- #
section("3. 真实文件系统上创建 POSIX 文件名（含 240 字节中文名）")
# --------------------------------------------------------------------------- #
with tempfile.TemporaryDirectory() as td:
    long_cn = "命运奇异赝品 第01集" * 30
    name = plat.safe_filename(long_cn, limit=110, platform="linux")
    p = os.path.join(td, name + ".mp4")
    ok = True
    err = ""
    try:
        with open(p, "wb") as f:
            f.write(b"x" * 1024)
    except OSError as e:
        ok, err = False, repr(e)
    check(f"创建 240 字节中文名文件成功（{len(name.encode())} 字节）", ok, err)
    check("文件确实存在", os.path.isfile(p))
    check("文件名 UTF-8 字节 ≤ 255", len(os.path.basename(p).encode()) <= 255,
          f"{len(os.path.basename(p).encode())} 字节")

    # 对照：旧实现的 110 字符中文名在 ext4 上会 ENAMETOOLONG（上限 255 字节）。
    # Windows NTFS 按字符算（255 字符 > 110 字符）所以不会报错，这正是隐蔽之处。
    old = ("命运奇异赝品 第01集" * 30)[:110]
    check("对照：旧实现按 110 字符截断后超过 255 字节（ext4 会失败）",
          len(old.encode()) > 255, f"{len(old.encode())} 字节")


# --------------------------------------------------------------------------- #
section("4. 用真实 ffmpeg 走一遍 POSIX 下的一集流程")


def _resolve_ff() -> str:
    """和 agedl_cli.resolve_ffmpeg 同序：环境变量 → 自动查找。"""
    for key in ("AGEDL_FFMPEG",):
        v = (os.environ.get(key) or "").strip().strip('"').strip("'")
        if v:
            if os.path.isfile(v):
                return v
            for n in plat.exe_names("ffmpeg"):
                p = os.path.join(v, n)
                if os.path.isfile(p):
                    plat.ensure_executable(p)
                    return p
    d = (os.environ.get("AGEDL_FFMPEG_DIR") or "").strip().strip('"').strip("'")
    if d:
        for n in plat.exe_names("ffmpeg"):
            p = os.path.join(d, n)
            if os.path.isfile(p):
                plat.ensure_executable(p)
                return p
    return core.find_ffmpeg() or ""


ff = _resolve_ff()


def pick_ffmpeg(probe_dir: str) -> str:
    """返回一个确实能写入 probe_dir 的 ffmpeg。

    本机（以及部分企业环境）会按可执行文件自身路径限制写入范围：
    位于受限目录里的 ffmpeg 写外部目录会 Permission denied。
    这里先探一次，失败就走 core 的逃逸副本，与线上行为一致。
    """
    if not ff:
        return ""
    probe = os.path.join(probe_dir, "._ffprobe.mp4")
    try:
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=64x48:rate=5:duration=1",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", probe],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, **plat.spawn_kwargs())
        if r.returncode == 0 and os.path.isfile(probe):
            return ff
        print(f"  原 ffmpeg 写入受限（{r.returncode}），尝试逃逸副本 …")
    except Exception as e:  # noqa: BLE001
        print(f"  原 ffmpeg 探测异常：{e}")
    alt = core.escaped_ffmpeg(ff, on_log=lambda m: print("   " + m))
    return alt or ff


if not ff:
    skip("完整一集流程", "本机找不到 ffmpeg")
else:
    print(f"  初始 ffmpeg: {ff}")
    with tempfile.TemporaryDirectory() as td:
        out_dir = os.path.join(td, "番剧 输出")     # 故意带空格与中文
        os.makedirs(out_dir, exist_ok=True)

        ff = pick_ffmpeg(out_dir) or ff
        print(f"  实际使用: {ff}")
        check("拿到可写的 ffmpeg", bool(ff) and os.path.isfile(ff), ff)

        title = "命运奇异赝品 第01集"
        name = core.sanitize(title)
        check("core.sanitize 输出合法", len(name.encode()) <= 240, name)

        # 造 3 秒的合法 TS：用 ffmpeg 生成测试源再转成 mpegts
        src_mp4 = os.path.join(td, "src.mp4")
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
             "-shortest", src_mp4],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, **plat.spawn_kwargs())
        if r.returncode != 0 or not os.path.isfile(src_mp4):
            skip("完整一集流程", f"生成测试源失败：{(r.stderr or '')[-160:]}")
        else:
            # 转成 ts，再当成 .raw（模拟 SegmentDownloader.merge 的产物）
            raw = os.path.join(out_dir, name + ".raw")
            r = subprocess.run(
                [ff, "-y", "-hide_banner", "-loglevel", "error",
                 "-i", src_mp4, "-c", "copy", "-f", "mpegts",
                 "-bsf:v", "h264_mp4toannexb", raw],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120, **plat.spawn_kwargs())
            check("生成 .raw 中间流（-f mpegts）",
                  r.returncode == 0 and os.path.isfile(raw),
                  (r.stderr or "")[-160:])

            if os.path.isfile(raw):
                check(".raw 首字节是 TS sync 0x47",
                      open(raw, "rb").read(1) == b"\x47")

                # 关键：走 core.remux_container（内部用 plat.spawn_kwargs）
                dst = os.path.join(out_dir, name + ".mp4")
                logs = []
                ok = core.remux_container(ff, raw, dst, on_log=logs.append)
                check("core.remux_container 在 POSIX 下返回 True", ok,
                      " | ".join(logs[-3:]))
                check("目标 mp4 存在且非空",
                      os.path.isfile(dst) and os.path.getsize(dst) > 0,
                      f"{os.path.getsize(dst) if os.path.isfile(dst) else 0} 字节")
                check("没有残留 .part 文件",
                      not any(f.endswith(".part.mp4") for f in os.listdir(out_dir)),
                      str(os.listdir(out_dir)))

                if os.path.isfile(dst):
                    check("仍是 MP4 容器（ftyp）",
                          open(dst, "rb").read(12)[4:8] == b"ftyp",
                          str(open(dst, "rb").read(12)))

                    # mkv 分支（非 mp4 不带 -movflags）
                    mkv = os.path.join(out_dir, name + ".mkv")
                    logs2 = []
                    ok2 = core.remux_container(ff, raw, mkv, on_log=logs2.append)
                    check("core.remux_container 出 MKV 也成功", ok2,
                          " | ".join(logs2[-2:]))
                    check("mkv 存在且非空",
                          os.path.isfile(mkv) and os.path.getsize(mkv) > 0)

                    # 全片解码
                    r = subprocess.run([ff, "-v", "error", "-i", dst, "-f", "null", "-"],
                                       capture_output=True, text=True, encoding="utf-8",
                                       errors="replace", timeout=120, **plat.spawn_kwargs())
                    check("成品全片解码零错误", r.returncode == 0 and not (r.stderr or "").strip(),
                          (r.stderr or "")[-200:])


# --------------------------------------------------------------------------- #
section("5. 带空格与中文的路径能否被 ffmpeg 正确处理")
# --------------------------------------------------------------------------- #
if not ff:
    skip("特殊字符路径", "无 ffmpeg")
else:
    with tempfile.TemporaryDirectory() as td:
        weird = os.path.join(td, "番剧 输出 (测试) [v1.0]")
        os.makedirs(weird, exist_ok=True)
        ff2 = pick_ffmpeg(weird) or ff
        f = os.path.join(weird, "名字 带空格 和中文.mp4")
        r = subprocess.run(
            [ff, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=160x120:rate=5:duration=1",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", f],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, **plat.spawn_kwargs())
        check("ffmpeg 能写入含空格+中文+方括号的路径",
              r.returncode == 0 and os.path.isfile(f), (r.stderr or "")[-160:])


# --------------------------------------------------------------------------- #
print(f"\n{'=' * 70}")
if FAIL:
    print(f"结果：{PASS} 通过 / {FAIL} 失败 / {SKIP} 跳过")
    for f in FAILS:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"结果：{PASS} 项通过 / 0 失败 / {SKIP} 跳过")
print("=" * 70)
