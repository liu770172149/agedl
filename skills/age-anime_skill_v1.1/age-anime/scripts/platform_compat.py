# -*- coding: utf-8 -*-
"""
platform_compat.py — 跨平台差异集中处（Windows / Linux / macOS）

所有平台相关的判断只放在这个文件里，其余模块一律调用这里。
每个函数都可以显式传 platform= 参数，方便在任意系统上做单元测试
（本机没有 Linux 环境，靠这个把 POSIX 分支真正跑起来）。

对外 API：
    exe_names(base)                     按平台返回可执行文件名候选
    ffmpeg_candidate_dirs(...)          按平台返回 ffmpeg 常见安装目录
    spawn_kwargs()                      subprocess 需要的平台参数（Windows 隐藏窗口）
    ensure_executable(path)             POSIX 上补 +x
    safe_filename(name, limit, max_bytes)  跨平台安全文件名（含字节长度截断）
    describe()                          平台摘要（doctor 用）
"""

from __future__ import annotations

import ntpath
import os
import posixpath
import stat
import subprocess
import sys

# --------------------------------------------------------------------------- #
# 平台标识
# --------------------------------------------------------------------------- #
WINDOWS = sys.platform.startswith("win")
MACOS = sys.platform == "darwin"
LINUX = sys.platform.startswith("linux")
POSIX = os.name == "posix"

# 文件名单个分量的字节上限：ext4/xfs 是 255，APFS 是 255，NTFS 是 255 字符。
# 中文在 UTF-8 里占 3 字节，所以「110 个汉字」= 330 字节，在 Linux 上会 ENAMETOOLONG。
MAX_NAME_BYTES = 240

# Windows 保留设备名（含扩展名也算，如 CON.txt）
WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# 一律按 Windows 的非法字符清洗：这样同一批文件在两边都能创建、也能互相拷贝
ILLEGAL_RE_CHARS = '\\/:*?"<>|'


# --------------------------------------------------------------------------- #
# 可执行文件
# --------------------------------------------------------------------------- #
def exe_names(base: str = "ffmpeg", platform: str | None = None) -> list[str]:
    """按平台返回可执行文件名候选（Windows 优先带 .exe）。"""
    p = platform or sys.platform
    if p.startswith("win"):
        return [base + ".exe", base]
    return [base]


def ffmpeg_candidate_dirs(platform: str | None = None,
                          home: str | None = None,
                          exe_dir: str | None = None) -> list[str]:
    """按平台返回 ffmpeg 可能所在目录，顺序即优先级。

    platform  显式平台（测试用），默认当前平台
    home      家目录，默认 expanduser("~")
    exe_dir   当前程序所在目录（调用方自己知道的相对位置）

    注意：这里按**目标平台**选路径模块，不能用 os.path.join ——
    否则在 Windows 上测 linux 分支时，会拼出 "/home/u\\bin" 这种混合分隔符。
    """
    p = platform or sys.platform
    is_win = p.startswith("win")
    # 按目标平台决定分隔符，保证跨平台测试拿到的是真实形态
    jp = ntpath.join if is_win else posixpath.join

    h = home if home is not None else os.path.expanduser("~")
    dirs: list[str] = []

    if exe_dir:
        dirs.append(exe_dir)

    # 用户显式指定的目录永远优先
    env = os.environ.get("AGEDL_FFMPEG_DIR", "").strip().strip('"')
    if env:
        dirs.append(env)

    if is_win:
        dirs += [
            "C:\\ffmpeg\\bin",
            "D:\\ffmpeg\\bin",
            "E:\\ffmpeg\\bin",
            jp(h, "ffmpeg", "bin"),
            jp(h, "scoop", "shims"),
            jp(h, "scoop", "apps", "ffmpeg", "current", "bin"),
            jp(os.environ.get("LOCALAPPDATA") or jp(h, "AppData", "Local"),
               "Microsoft", "WinGet", "Links"),
            "C:\\ProgramData\\chocolatey\\bin",
        ]
    else:
        # Linux / macOS：包管理器与 Homebrew / MacPorts / snap
        dirs += [
            "/usr/bin",
            "/usr/local/bin",
            "/bin",
            "/snap/bin",
            "/opt/homebrew/bin",          # Apple Silicon Homebrew
            "/usr/local/opt/ffmpeg/bin",  # Intel Homebrew（keg-only）
            "/opt/local/bin",             # MacPorts
            "/opt/ffmpeg/bin",
            jp(h, ".local", "bin"),
            jp(h, "bin"),
            jp(h, "ffmpeg", "bin"),
        ]

    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def spawn_kwargs(platform: str | None = None) -> dict:
    """subprocess 的平台参数：Windows 上不让控制台窗口闪出来，其它平台为空。"""
    p = platform or sys.platform
    if p.startswith("win"):
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def ensure_executable(path: str) -> None:
    """POSIX 上确保有执行位（从 zip 解压出来的 ffmpeg 常常没有 +x）。"""
    if not path or WINDOWS:
        return
    try:
        st = os.stat(path)
        if not (st.st_mode & stat.S_IXUSR):
            os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# 文件名
# --------------------------------------------------------------------------- #
def _truncate_utf8(s: str, max_bytes: int) -> str:
    """按 UTF-8 字节数截断，且不把多字节字符切成两半。"""
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    cut = b[:max_bytes]
    # 去掉可能被切断的尾部残缺序列
    while cut:
        try:
            return cut.decode("utf-8")
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def safe_filename(name: str, limit: int = 110, max_bytes: int = MAX_NAME_BYTES,
                  platform: str | None = None, fallback: str = "video") -> str:
    """生成跨平台可用的文件名（不含目录、不含扩展名）。

    规则：
      1. Windows 非法字符一律替换成空格（NTFS 不允许，ext4 允许但没必要留）
      2. 连续空白折叠
      3. 先按字符数 limit 截断，再按 UTF-8 字节数 max_bytes 截断
         —— ext4/APFS 的单个文件名上限是 255 字节，中文占 3 字节，
            纯按字符截断会写出 330 字节的名字，Linux 上直接 ENAMETOOLONG
      4. Windows 上去掉结尾的点和空格（资源管理器无法创建）
      5. Windows 保留设备名加下划线前缀
    """
    p = platform or sys.platform
    s = name or ""
    for ch in ILLEGAL_RE_CHARS:
        s = s.replace(ch, " ")
    s = s.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    # 控制字符
    s = "".join(" " if ord(c) < 32 else c for c in s)
    s = " ".join(s.split()).strip()

    if limit and len(s) > limit:
        s = s[:limit].strip()
    s = _truncate_utf8(s, max_bytes).strip()

    if p.startswith("win"):
        s = s.rstrip(" .")
        if s.split(".")[0].upper() in WIN_RESERVED:
            s = "_" + s

    return s or fallback


# --------------------------------------------------------------------------- #
# 摘要
# --------------------------------------------------------------------------- #
def install_hint(platform: str | None = None) -> str:
    """找不到 ffmpeg 时给出按平台的安装建议（doctor 用）。"""
    p = platform or sys.platform
    if p.startswith("win"):
        return ("没找到 ffmpeg。任选一种：winget install Gyan.FFmpeg；"
                "scoop install ffmpeg；或下载便携版解压后把 bin 目录设成环境变量 AGEDL_FFMPEG_DIR")
    if p == "darwin":
        return ("没找到 ffmpeg。用 Homebrew：brew install ffmpeg；"
                "或把二进制所在目录设成环境变量 AGEDL_FFMPEG_DIR")
    return ("没找到 ffmpeg。Debian/Ubuntu：sudo apt install -y ffmpeg；"
            "Fedora：sudo dnf install -y ffmpeg；Arch：sudo pacman -S ffmpeg；"
            "或把二进制所在目录设成环境变量 AGEDL_FFMPEG_DIR")


def describe() -> dict:
    """平台摘要，doctor 子命令用。"""
    return {
        "platform": sys.platform,
        "os_name": os.name,
        "is_windows": WINDOWS,
        "is_linux": LINUX,
        "is_macos": MACOS,
        "path_sep": os.sep,
        "max_name_bytes": MAX_NAME_BYTES,
    }
