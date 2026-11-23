# -*- coding: utf-8 -*-
"""修 merge 的覆盖容错：目标已存在被占用时先删再换。"""
import ast
import io

P = "core.py"
s = io.open(P, encoding="utf-8").read()

old = '''                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        os.replace(tmp, target)
        return target'''
new = '''                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)

        # 目标已存在（上次中断或被播放器占用）时 os.replace 会抛 WinError 5，
        # 先尝试删除；删不掉就退化为直接写目标路径。
        for attempt in range(3):
            try:
                if os.path.exists(target):
                    os.remove(target)
                os.replace(tmp, target)
                return target
            except PermissionError:
                if attempt == 2:
                    shutil.copyfile(tmp, target)
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    return target
                time.sleep(0.4)
        return target'''

assert old in s, "merge tail not found"
s = s.replace(old, new)

# 确保 time 已导入
if "\nimport time\n" not in s and "^import time" not in s:
    s = s.replace("import threading\n", "import threading\nimport time\n", 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("merge patched; time imported:", "import time" in s)
