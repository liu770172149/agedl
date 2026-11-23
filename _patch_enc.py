# -*- coding: utf-8 -*-
"""修 core.py 的 subprocess 解码问题。

真实故障：subprocess.run(..., text=True) 用系统 locale（GBK/cp936）解码 ffmpeg 输出，
而 ffmpeg 打印的中文路径是 UTF-8 字节 → _readerthread 抛 UnicodeDecodeError，
communicate 拿不到完整输出，封装被误判为失败（日志却是一句无关的 "ffmpeg: ..."）。

修法：所有 text=True 的调用都显式 encoding="utf-8", errors="replace"。
"""
import ast
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CORE = r"D:\deepseekproject\agedl\core.py"
src = open(CORE, encoding="utf-8").read()
before = len(src)

# 找所有 text=True 出现在 subprocess.run / Popen 的调用里
hits = [m.start() for m in re.finditer(r"text=True", src)]
print(f"发现 text=True 共 {len(hits)} 处")

n = 0
# 替换 pattern: text=True  ->  text=True, encoding="utf-8", errors="replace"
def repl(m):
    global n
    n += 1
    return 'text=True, encoding="utf-8", errors="replace"'

# 只在 subprocess 相关调用中替换；先看上下文
out = []
last = 0
for m in re.finditer(r"text=True", src):
    s = m.start()
    ctx = src[max(0, s - 400):s]
    if "subprocess" not in ctx and "run(" not in ctx:
        out.append(src[last:m.end()])
        last = m.end()
        continue
    out.append(src[last:s])
    out.append('text=True, encoding="utf-8", errors="replace"')
    last = m.end()
    n += 1
out.append(src[last:])
src = "".join(out)

open(CORE, "w", encoding="utf-8", newline="\n").write(src)
ast.parse(src)
print(f"替换 {n} 处；{before} -> {len(src)} 字符，ast OK")

lines = src.splitlines()
for i, l in enumerate(lines, 1):
    if "text=True" in l:
        print(f"{i:5d}| {l.strip()}")
