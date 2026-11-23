import ast, io, sys, time
p="gui.py"; s=io.open(p,encoding="utf-8").read(); ast.parse(s); print("AST OK", len(s))

import tkinter as tk
import gui
app = gui.App()
steps = []
def later(ms, fn): app.after(ms, fn)

log = []
def step1():
    app.nb.select(1)
    app.d_search_var.set("命运奇异赝品")
    app.on_discover_search()
    later(9000, step2)
def step2():
    n = len(app.d_tree.get_children())
    log.append(f"搜索结果 {n} 行: {[app.d_tree.item(i,'values')[1] for i in app.d_tree.get_children()[:3]]}")
    if n:
        app.d_tree.selection_set(app.d_tree.get_children()[0])
        app.update()
    later(500, step3)
def step3():
    sel = app.d_tree.selection()
    log.append(f"选中 {sel}")
    log.append("详情片段: " + app.d_detail.get("1.0","end").strip().replace("\n"," | ")[:220])
    app.on_discover_to_download()
    later(12000, step4)
def step4():
    log.append(f"tab={app.nb.index(app.nb.select())} url={app.url_var.get()}")
    log.append(f"info={app.info_var.get()}")
    rows = app.tree.get_children()
    log.append(f"集数 {len(rows)} 行")
    for iid in rows[:3]:
        log.append("   " + str(app.tree.item(iid,"values")))
    later(500, step5)
def step5():
    log.append("日志尾部:")
    for L in app.log_txt.get("1.0","end").strip().split("\n")[-6:]:
        log.append("   " + L)
    app.destroy()

app.after(500, step1)
app.after(40000, app.destroy)
app.mainloop()
print("\n".join(log))
print("DONE")
