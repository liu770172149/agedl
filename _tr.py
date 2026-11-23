import sys
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
app = gui.App()
trace = []
def kick():
    trace.append("kick: select tab1")
    app.nb.select(1)
    trace.append(f"  after select busy={app._d_busy}")
    app.d_search_var.set("斗破苍穹")
    app.on_discover_search()
    trace.append(f"  after search busy={app._d_busy} pending={app._d_pending is not None}")
    app.after(12000, done)
def done():
    trace.append(f"final stat={app.d_stat_var.get()} rows={len(app.d_tree.get_children())} busy={app._d_busy} pending={app._d_pending is not None}")
    trace.append("-- log --")
    trace.extend(app.log_txt.get("1.0","end").strip().split("\n")[-10:])
    app.destroy()
app.after(900, kick); app.after(30000, app.destroy)
app.mainloop()
print("\n".join(trace))
