import io, re
p = "gui.py"
s = io.open(p, encoding="utf-8").read()
pairs = [
 ('mid = ttk.LabelFrame(self, text=" 2. 选择要下载的集 ")',
  'mid = ttk.LabelFrame(root, text=" 2. 选择要下载的集 ")'),
 ('bot = ttk.LabelFrame(self, text=" 3. 输出设置 ")',
  'bot = ttk.LabelFrame(root, text=" 3. 输出设置 ")'),
 ('pr = ttk.LabelFrame(self, text=" 4. 下载 ")',
  'pr = ttk.LabelFrame(root, text=" 4. 下载 ")'),
 ('lg = ttk.LabelFrame(self, text=" 运行日志 ")',
  'lg = ttk.LabelFrame(root, text=" 运行日志 ")'),
]
n = 0
for a, b in pairs:
    if a in s:
        s = s.replace(a, b); n += 1
    else:
        print("MISS:", a)
io.open(p, "w", encoding="utf-8", newline="\n").write(s)
print("replaced", n)
