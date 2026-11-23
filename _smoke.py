import io, sys, time
sys.argv = ["gui.py"]
import gui
app = gui.App()
app.update()
print("窗口:", app.geometry())
print("tab 数:", app.nb.index("end"))
for i in range(app.nb.index("end")):
    print(f"  tab{i}: {app.nb.tab(i, 'text')!r}")
print("d_tree 列:", app.d_tree["columns"])
print("detail 控件:", app.d_detail.winfo_exists())
print("下载页 tree:", app.tree["columns"])

# 切到发现页，触发自动加载
app.nb.select(1)
app.update()
print("已切到发现页, _d_loaded_once =", app._d_loaded_once)
app.destroy()
print("OK")
