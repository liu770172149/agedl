import io
s = io.open("gui.py", encoding="utf-8").read()
lines = s.split("\n")
# 找 _handle 里 d_rows 分支
start = None
for n, l in enumerate(lines):
    if "d_rows" in l and "==" in l:
        start = n
        break
print("\n".join(f"{i+1}: {lines[i]}" for i in range(start-3, start+30)))
