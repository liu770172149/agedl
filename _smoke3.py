import ast, io, sys, time
p="gui.py"
s=io.open(p,encoding="utf-8").read()
ast.parse(s); print("AST OK", len(s))

sys.argv=["gui.py"]
import gui
app=gui.App(); app.update()
def pump(sec=8.0):
    t0=time.time()
    while time.time()-t0<sec:
        app.update(); time.sleep(0.02)

app.nb.select(1); app.update(); pump(8)
print("榜单:", app.d_stat_var.get(), "行数", len(app.d_tree.get_children()))
print("  首行:", app.d_tree.item(app.d_tree.get_children()[0],"values"))

print()
print("搜索 命运 并等详情补全")
app.d_search_var.set("命运"); app.on_discover_search(); pump(10)
print("搜索:", app.d_stat_var.get(), "行数", len(app.d_tree.get_children()))
sel=app.d_tree.selection()
print("选中:", sel, app.d_tree.item(sel[0],"values"))
print("--- 详情框 ---")
print(app.d_detail.get("1.0","end").strip())

app.destroy()
print("\nDONE")
