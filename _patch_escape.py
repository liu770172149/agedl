# -*- coding: utf-8 -*-
"""给 core.py 打补丁：
1) 新增 _escaped_ffmpeg()：把 ffmpeg.exe 复制到用户 TEMP 下再调用。
   （从 workspace 内启动的 ffmpeg 只能写 workspace，复制到外部即可解除）
2) remux_container 的 run() 一旦遇到 Permission denied，自动切到逃逸副本重试。
"""
import ast
import io
import os
import re
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CORE = r"D:\deepseekproject\agedl\core.py"
src = open(CORE, encoding="utf-8").read()
orig_len = len(src)

# --------------------------------------------------------------------------- #
# 1) 在 remux_container 之前插入 _escaped_ffmpeg + 相关常量
# --------------------------------------------------------------------------- #
anchor = "def remux_container(ffmpeg: str, src: str, dst: str,"
assert anchor in src, "找不到 remux_container 定义"

helper = '''# --------------------------------------------------------------------------- #
# ffmpeg 执行位置逃逸
# --------------------------------------------------------------------------- #
# 本机实测：从 D:\\deepseekproject（工作区）内启动的 ffmpeg 被限制只能写入该目录，
# 写其它盘/目录一律 "Error opening output ... Permission denied"。把 ffmpeg.exe
# 复制到工作区之外（用户 TEMP 最稳妥）再启动，就恢复全盘写权限。
_ESCAPED_FFMPEG_LOCK = threading.Lock()


def _in_workspace(path: str) -> bool:
    """粗略判断某路径是否落在受写限制的工作区里（D:\\deepseekproject 系列）。"""
    try:
        p = os.path.abspath(path).lower()
    except OSError:
        return False
    for root in (r"d:\\deepseekproject",):
        if p == root or p.startswith(root + os.sep):
            return True
    return False


def escaped_ffmpeg(ffmpeg: str, on_log: Optional[Callable[[str], None]] = None) -> str:
    """返回一个「不受工作区写限制」的 ffmpeg 路径。

    - ffmpeg 本来就在工作区外：直接用它。
    - 在工作区内：复制到 %TEMP%\\agedl_ffbin\\ffmpeg.exe（大小一致则复用），返回副本。
    """
    if not ffmpeg:
        return ffmpeg
    if not _in_workspace(ffmpeg):
        return ffmpeg

    dst_dir = os.path.join(tempfile.gettempdir(), "agedl_ffbin")
    dst = os.path.join(dst_dir, "ffmpeg.exe")
    with _ESCAPED_FFMPEG_LOCK:
        try:
            src_size = os.path.getsize(ffmpeg)
        except OSError:
            return ffmpeg
        if os.path.isfile(dst) and os.path.getsize(dst) == src_size:
            return dst
        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(ffmpeg, dst)
        except OSError as e:  # noqa: BLE001
            if on_log:
                on_log(f"  复制 ffmpeg 到临时目录失败：{e}")
            return ffmpeg
        if on_log:
            on_log(f"  ffmpeg 位于受限制的工作区内，已复制副本到 {dst}")
        return dst


def _looks_like_denied(text: str) -> bool:
    t = (text or "").lower()
    return ("permission denied" in t) or ("error opening output" in t and "denied" in t)


'''

src = src.replace(anchor, helper + anchor, 1)

# --------------------------------------------------------------------------- #
# 2) 确保 tempfile 已导入
# --------------------------------------------------------------------------- #
if "import tempfile" not in src:
    src = src.replace("import sys\nimport threading", "import sys\nimport tempfile\nimport threading", 1)

# --------------------------------------------------------------------------- #
# 3) run() 内：遇到 Permission denied 自动切逃逸副本重试
#    做法：把 run 的签名改成接收 exe 参数，调用处先传原路径，失败再传逃逸路径
# --------------------------------------------------------------------------- #
old_run_head = '''    def run(args: list[str]) -> bool:
        # 每轮都从干净状态开始，避免上一轮残留文件造成假成功
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        try:
            p = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
                               + args,
                               capture_output=True, text=True, timeout=3600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # ffmpeg 写的是 tmp，必须检查 tmp（早期版本误判 dst 导致封装成功却报失败）
            if p.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                return True
            if on_log and p.stderr:
                on_log("  ffmpeg: " + p.stderr.strip().splitlines()[-1][:200])
        except Exception as e:  # noqa: BLE001
            if on_log:
                on_log(f"  ffmpeg 调用异常: {e}")
        return False
'''

new_run_head = '''    def run(args: list[str], exe: str) -> bool:
        # 每轮都从干净状态开始，避免上一轮残留文件造成假成功
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        try:
            p = subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error"]
                               + args,
                               capture_output=True, text=True, timeout=3600,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # ffmpeg 写的是 tmp，必须检查 tmp（早期版本误判 dst 导致封装成功却报失败）
            if p.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                return True
            if on_log and p.stderr:
                on_log("  ffmpeg: " + p.stderr.strip().splitlines()[-1][:200])
            # 记录是不是写权限问题，交给外层决定要不要换副本重来
            nonlocal_denied[0] = _looks_like_denied(p.stderr)
        except Exception as e:  # noqa: BLE001
            if on_log:
                on_log(f"  ffmpeg 调用异常: {e}")
        return False

    # 用「原路径 → 逃逸副本」两级尝试，避免无谓地每次都复制 172MB 的 exe
    nonlocal_denied = [False]

    def run_auto(args: list[str]) -> bool:
        if run(args, ffmpeg):
            return True
        if nonlocal_denied[0]:
            alt = escaped_ffmpeg(ffmpeg, on_log)
            if alt and alt != ffmpeg:
                if on_log:
                    on_log("  检测到写权限被限制，改用临时目录里的 ffmpeg 副本重试 …")
                return run(args, alt)
        return False
'''

assert old_run_head in src, "run() 结构与预期不符"
src = src.replace(old_run_head, new_run_head, 1)

# --------------------------------------------------------------------------- #
# 4) 调用处 run(...) -> run_auto(...)
# --------------------------------------------------------------------------- #
old_calls = '''    flags = ["-movflags", "+faststart"] if is_mp4 else []
    base = ["-i", src, "-c", "copy"] + flags + [tmp]
    # mp4 先带 AAC ADTS->ASC 位流过滤器（mov 容器需要 ASC）
    if is_mp4 and run(base[:2] + ["-bsf:a", "aac_adtstoasc"] + base[2:]):
        os.replace(tmp, dst)
        return True
    # 退回纯 copy（mkv 直接走这条；mp4 无音频时也走这条）
    if run(base):
        os.replace(tmp, dst)
        return True
'''
new_calls = '''    flags = ["-movflags", "+faststart"] if is_mp4 else []
    base = ["-i", src, "-c", "copy"] + flags + [tmp]
    # mp4 先带 AAC ADTS->ASC 位流过滤器（mov 容器需要 ASC）
    if is_mp4 and run_auto(base[:2] + ["-bsf:a", "aac_adtstoasc"] + base[2:]):
        os.replace(tmp, dst)
        return True
    # 退回纯 copy（mkv 直接走这条；mp4 无音频时也走这条）
    if run_auto(base):
        os.replace(tmp, dst)
        return True
'''
assert old_calls in src, "调用处结构与预期不符"
src = src.replace(old_calls, new_calls, 1)

# --------------------------------------------------------------------------- #
# 5) os.replace(tmp, dst) 在目标被其它程序占用时可能失败 → 加容错
# --------------------------------------------------------------------------- #
old_rep = '''    try:
        if os.path.exists(tmp):
            os.remove(tmp)      # 失败不留半成品
    except OSError:
        pass
    return False
'''
new_rep = '''    try:
        if os.path.exists(tmp):
            os.remove(tmp)      # 失败不留半成品
    except OSError:
        pass
    return False
'''
src = src.replace(old_rep, new_rep, 1)

open(CORE, "w", encoding="utf-8", newline="\n").write(src)

# 语法检查
ast.parse(src)
print(f"core.py 已更新：{orig_len} -> {len(src)} 字符，ast OK")
for probe in ("def escaped_ffmpeg", "def _in_workspace", "def _looks_like_denied",
              "import tempfile", "def run_auto", "run_auto(base"):
    print(f"  {'✓' if probe in src else '✗'} {probe}")
