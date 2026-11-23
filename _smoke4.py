import sys, time
sys.argv=["gui.py"]
import gui
app=gui.App(); app.update()
def pump(sec=10.0):
    t0=time.time()
    while time.time()-t0<sec:
        app.update(); time.sleep(0.02)

# 直接构造：搜索 命运奇异赝品
app.nb.select(1); app.update()
app.d_search_var.set("命运奇异赝品"); app.on_discover_search(); pump(10)
print("搜索:", app.d_stat_var.get(), "行数", len(app.d_tree.get_children()))
for iid in app.d_tree.get_children()[:3]:
    print("  ", app.d_tree.item(iid,"values"))

# 选中第一条 -> 去下载
sel = app.d_tree.get_children()[0]
app.d_tree.selection_set(sel); app.update()
print("当前 tab:", app.nb.index(app.nb.select()))
app.on_discover_to_download()
pump(15)
print("切到 tab:", app.nb.index(app.nb.select()), "URL:", app.url_var.get())
print("下载页信息:", app.info_var.get())
print("集数表格行数:", len(app.tree.get_children()))
if app.tree.get_children():
    print("  首行:", app.tree.item(app.tree.get_children()[0],"values"))
print("--- 日志尾部 ---")
print("\n".join(app.log_txt.get("1.0","end").strip().split("\n")[-8:]))
app.destroy()
print("\nDONE")
