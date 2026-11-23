# -*- coding: utf-8 -*-
"""把 gui.py 里的 TS 格式选项改成 MKV。"""
import ast
import io

P = "gui.py"
s = io.open(P, encoding="utf-8").read()
lines = s.splitlines()
n = 0

for i, l in enumerate(lines):
    if "MP4 无损封装 / 原始 TS" in l:
        lines[i] = "  4. 选输出格式（MP4 / MKV，均无损封装）"
        n += 1
    elif "✗ 未找到（只能用 TS）" in l:
        lines[i] = l.replace("✗ 未找到（只能用 TS）", "✗ 未找到（无法封装）")
        n += 1
    elif l.strip() == 'fmt = "ts"':
        lines[i] = l.replace('"ts"', '"mkv"')
        n += 1
    elif 'choices=["mp4", "ts"]' in l:
        lines[i] = l.replace('"ts"', '"mkv"')
        n += 1

out = "\n".join(lines) + "\n"
ast.parse(out)
io.open(P, "w", encoding="utf-8", newline="\n").write(out)
print("patched lines:", n)

left = [(i, l) for i, l in enumerate(out.splitlines(), 1)
        if "TS" in l or '"ts"' in l]
print("remaining TS refs:", left)
