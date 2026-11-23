import sys, time
sys.argv = ["gui.py"]
import gui
app = gui.App()
app.update()

def pump(sec=6.0):
    t0 = time.time()
    while time.time() - t0 < sec:
        app.update()
        time.sleep(0.02)

print("=== 切到发现页 ===")
app.nb.select(1); app.update()
pump(8)
print("状态:", app.d_stat_var.get())
print("行数:", len(app.d_tree.get_children()))
for iid in app.d_tree.get_children()[:5]:
    print("  ", app.d_tree.item(iid, "values"))

print()
print("=== 搜索 命运 ===")
app.d_search_var.set("命运")
app.on_discover_search()
pump(8)
print("状态:", app.d_stat_var.get())
print("行数:", len(app.d_tree.get_children()))
for iid in app.d_tree.get_children()[:4]:
    print("  ", app.d_tree.item(iid, "values"))
print("详情框首 4 行:")
print("\n".join(app.d_detail.get("1.0","end").strip().split("\n")[:4]))

print()
print("=== 切到最新入库 + 翻页 ===")
app.d_src_var.set("最新入库")
app.on_discover_page()
pump(8)
print("状态:", app.d_stat_var.get())
print("行数:", len(app.d_tree.get_children()))
app.on_discover_next(); pump(8)
print("翻到:", app.d_stat_var.get())

app.destroy()
print("OK")
