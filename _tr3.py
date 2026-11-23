import sys
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
app = gui.App()
trace = []
orig = app._handle
def spy(m):
    trace.append(f"msg {m.kind} busy={app._d_busy} pend={app._d_pending is not None}")
    try: orig(m)
    except Exception as e: trace.append(f"  !! {type(e).__name__}: {e}")
app._handle = spy
def kick():
    app.nb.select(1)
    trace.append(f"after select: loaded_once={app._d_loaded_once} busy={app._d_busy}")
    app.d_src_var.set("本周排行")
    app.on_discover_load()
    trace.append(f"after load: busy={app._d_busy} pend={app._d_pending is not None}")
app.after(900, kick)
def done():
    trace.append(f"FINAL stat={app.d_stat_var.get()} rows={len(app.d_tree.get_children())}")
    trace.append("LOG: " + " | ".join(app.log_txt.get("1.0","end").strip().split("\n")[-5:]))
    app.destroy()
app.after(9000, done); app.after(25000, app.destroy)
app.mainloop()
print("\n".join(trace))
