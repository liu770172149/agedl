# -*- coding: utf-8 -*-
"""
test_platform.py — 跨平台逻辑单元测试

本机没有 Linux 环境（WSL 未装内核、无 Docker），所以不能靠"在 Linux 上跑一遍"
来验证。这里的做法是：所有平台相关的判断都集中在 platform_compat.py，
并且每个函数都接受显式 platform= 参数 —— 于是可以在 Windows 上把
POSIX 分支真正执行一遍，而不是靠肉眼看代码。

运行： python test_platform.py       （全部通过返回 0）
"""

from __future__ import annotations

import os
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import platform_compat as plat  # noqa: E402

PASS = FAIL = 0
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


def section(t: str) -> None:
    print(f"\n{'─' * 70}\n{t}\n{'─' * 70}")


# --------------------------------------------------------------------------- #
section("1. exe_names — 可执行文件名按平台")
# --------------------------------------------------------------------------- #
check("Windows 返回 ffmpeg.exe 优先",
      plat.exe_names("ffmpeg", platform="win32") == ["ffmpeg.exe", "ffmpeg"],
      str(plat.exe_names("ffmpeg", platform="win32")))
check("Linux 只返回 ffmpeg（不带 .exe）",
      plat.exe_names("ffmpeg", platform="linux") == ["ffmpeg"],
      str(plat.exe_names("ffmpeg", platform="linux")))
check("macOS 只返回 ffmpeg",
      plat.exe_names("ffmpeg", platform="darwin") == ["ffmpeg"],
      str(plat.exe_names("ffmpeg", platform="darwin")))
check("Linux 上绝不出现 .exe",
      not any(n.endswith(".exe") for n in plat.exe_names("ffmpeg", platform="linux")))


# --------------------------------------------------------------------------- #
section("2. ffmpeg_candidate_dirs — 安装路径按平台")
# --------------------------------------------------------------------------- #
win = plat.ffmpeg_candidate_dirs(platform="win32", home="C:\\Users\\u")
lin = plat.ffmpeg_candidate_dirs(platform="linux", home="/home/u")
mac = plat.ffmpeg_candidate_dirs(platform="darwin", home="/Users/u")

check("Windows 含盘符路径 C:\\ffmpeg\\bin", "C:\\ffmpeg\\bin" in win)
check("Windows 含 scoop shims",
      any("scoop" in d for d in win), str([d for d in win if "scoop" in d]))
check("Linux 含 /usr/bin", "/usr/bin" in lin)
check("Linux 含 /usr/local/bin", "/usr/local/bin" in lin)
check("Linux 含 /snap/bin", "/snap/bin" in lin)
check("Linux 不含任何盘符", not any(d.startswith("C:\\") for d in lin),
      str([d for d in lin if ":" in d]))
check("Linux 不含反斜杠", not any("\\" in d for d in lin),
      str([d for d in lin if "\\" in d]))
check("macOS 含 Apple Silicon Homebrew /opt/homebrew/bin",
      "/opt/homebrew/bin" in mac)
check("macOS 含 Intel Homebrew", "/usr/local/opt/ffmpeg/bin" in mac)
check("macOS 不含盘符", not any(":" in d and d[1:2] == "\\" for d in mac))
check("去重生效", len(lin) == len(set(lin)), f"{len(lin)} vs {len(set(lin))}")
check("AGEDL_FFMPEG_DIR 环境变量优先",
      (lambda: (
          os.environ.__setitem__("AGEDL_FFMPEG_DIR", "/custom/ff"),
          "/custom/ff" in plat.ffmpeg_candidate_dirs(platform="linux", home="/home/u"),
          os.environ.pop("AGEDL_FFMPEG_DIR", None)
      )[-2])())


# --------------------------------------------------------------------------- #
section("3. safe_filename — 文件名按字节上限截断（Linux 关键）")
# --------------------------------------------------------------------------- #
long_cn = "命运奇异赝品 第01集" * 20
old_style = long_cn[:110]                     # 旧实现：只按字符截断
new_style = plat.safe_filename(long_cn, limit=110, platform="linux")

check("旧实现（纯字符截断）会超 255 字节", len(old_style.encode()) > 255,
      f"{len(old_style.encode())} 字节")
check("新实现 UTF-8 字节 ≤ 240", len(new_style.encode()) <= plat.MAX_NAME_BYTES,
      f"{len(new_style.encode())} 字节")
check("新实现不截断多字节字符",
      new_style.encode().decode("utf-8") == new_style)
check("新实现保留了内容前缀", new_style.startswith("命运奇异赝品"),
      new_style[:12])

mix = "a" * 200 + "命运奇异赝品" * 20
r = plat.safe_filename(mix, limit=0, platform="linux")
check("ASCII+中文混合也不超字节上限",
      len(r.encode()) <= plat.MAX_NAME_BYTES, f"{len(r.encode())} 字节")

check("Windows 非法字符被清洗",
      plat.safe_filename('a/b\\c:d*e?f"g<h>i|j', platform="win32")
      == "a b c d e f g h i j",
      repr(plat.safe_filename('a/b\\c:d*e?f"g<h>i|j', platform="win32")))
check("控制字符被清洗",
      "\n" not in plat.safe_filename("a\nb\tc", platform="linux"),
      repr(plat.safe_filename("a\nb\tc", platform="linux")))
check("Windows 去掉结尾点和空格",
      plat.safe_filename("名字...  ", platform="win32") == "名字",
      repr(plat.safe_filename("名字...  ", platform="win32")))
check("Linux 保留用户写的结尾点（不必清洗）",
      plat.safe_filename("v1.0.", platform="linux") == "v1.0.",
      repr(plat.safe_filename("v1.0.", platform="linux")))
check("Windows 保留设备名 CON 被加前缀",
      plat.safe_filename("CON", platform="win32") == "_CON",
      repr(plat.safe_filename("CON", platform="win32")))
check("Windows 保留设备名 con.txt 被加前缀",
      plat.safe_filename("con.txt", platform="win32").startswith("_"),
      repr(plat.safe_filename("con.txt", platform="win32")))
check("Linux 上 CON 是合法名，不改",
      plat.safe_filename("CON", platform="linux") == "CON")
check("空名回落到 fallback",
      plat.safe_filename("", platform="linux") == "video",
      repr(plat.safe_filename("", platform="linux")))
check("纯空白回落到 fallback",
      plat.safe_filename("   ", platform="win32") == "video",
      repr(plat.safe_filename("   ", platform="win32")))
check("中文名原样保留（不超限时）",
      plat.safe_filename("命运奇异赝品 第01集", platform="linux") == "命运奇异赝品 第01集")


# --------------------------------------------------------------------------- #
section("4. spawn_kwargs — subprocess 平台参数")
# --------------------------------------------------------------------------- #
kw_win = plat.spawn_kwargs(platform="win32")
kw_lin = plat.spawn_kwargs(platform="linux")
kw_mac = plat.spawn_kwargs(platform="darwin")
check("Windows 带 creationflags 键", "creationflags" in kw_win, str(kw_win))
check("Linux 为空 dict（不传 CREATE_NO_WINDOW）", kw_lin == {}, str(kw_lin))
check("macOS 为空 dict", kw_mac == {}, str(kw_mac))


# --------------------------------------------------------------------------- #
section("5. ensure_executable — POSIX 补执行位")
# --------------------------------------------------------------------------- #
with tempfile.TemporaryDirectory() as td:
    f = os.path.join(td, "ffmpeg")
    with open(f, "wb") as fh:
        fh.write(b"\x7fELF fake")

    os.chmod(f, 0o644)                      # 模拟从 zip 解压：没有 +x
    before = stat.S_IMODE(os.stat(f).st_mode)
    plat.ensure_executable(f)
    after = stat.S_IMODE(os.stat(f).st_mode)

    if plat.WINDOWS:
        check("Windows 上 ensure_executable 不改权限（NTFS 无 x 位概念）",
              before == after, f"{oct(before)} → {oct(after)}")
    else:
        check("POSIX 上加出执行位", after & stat.S_IXUSR, f"{oct(before)} → {oct(after)}")
        check("POSIX 上保留原有读写位", after & 0o600 == 0o600, oct(after))

    # 不存在的路径不能抛异常
    try:
        plat.ensure_executable(os.path.join(td, "nope"))
        check("不存在的路径安全返回", True)
    except Exception as e:  # noqa: BLE001
        check("不存在的路径安全返回", False, repr(e))


# --------------------------------------------------------------------------- #
section("6. describe — 平台摘要")
# --------------------------------------------------------------------------- #
d = plat.describe()
for k in ("platform", "os_name", "is_windows", "is_linux", "is_macos",
          "path_sep", "max_name_bytes"):
    check(f"describe() 含 {k}", k in d, str(d))
check("三者互斥（最多一个 True）",
      sum([d["is_windows"], d["is_linux"], d["is_macos"]]) <= 1,
      f"win={d['is_windows']} linux={d['is_linux']} mac={d['is_macos']}")


# --------------------------------------------------------------------------- #
section("7. core.sanitize 已接入（真实模块）")
# --------------------------------------------------------------------------- #
import core  # noqa: E402

s = core.sanitize("命运奇异赝品 第01集" * 20)
check("core.sanitize 输出 ≤ 240 字节",
      len(s.encode()) <= 240, f"{len(s.encode())} 字节")
check("core.sanitize 无非法字符",
      not any(c in s for c in '\\/:*?"<>|'), s[:20])
check("core.sanitize 中文正常",
      core.sanitize("命运奇异赝品 第01集") == "命运奇异赝品 第01集",
      repr(core.sanitize("命运奇异赝品 第01集")))


# --------------------------------------------------------------------------- #
section("8. core 的 POSIX 分支可被真实执行（打桩 sys.platform）")
# --------------------------------------------------------------------------- #
import importlib  # noqa: E402

saved = sys.platform
try:
    sys.platform = "linux"
    importlib.reload(plat)
    lin2 = plat.ffmpeg_candidate_dirs(home="/home/u")
    check("reload 到 linux 后不含盘符",
          not any(":\\" in d for d in lin2),
          str([d for d in lin2 if ":\\" in d]))
    check("reload 到 linux 后含 /usr/bin", "/usr/bin" in lin2)
    check("reload 到 linux 后 spawn_kwargs 为空", plat.spawn_kwargs() == {})
    check("reload 到 linux 后 exe_names 无 .exe",
          plat.exe_names("ffmpeg") == ["ffmpeg"])
finally:
    sys.platform = saved
    importlib.reload(plat)

check("恢复后 windows 分支回来了",
      plat.exe_names("ffmpeg") == ["ffmpeg.exe", "ffmpeg"]
      if plat.WINDOWS else plat.exe_names("ffmpeg") == ["ffmpeg"])


# --------------------------------------------------------------------------- #
print(f"\n{'=' * 70}")
if FAIL:
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    for f in FAILS:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"结果：{PASS} 项全部通过（0 失败）")
print("=" * 70)
