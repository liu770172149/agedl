import sys
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
app = gui.App()
trace = []
orig = app._handle
def spy(m):
    trace.append(f"  msg {m.kind} busy_before={app._d_busy} pend={app._d_pending is not None}")
    try:
        orig(m)
    except Exception as e:
        trace.append(f"    !! {type(e).__name__}: {e}")
    trace.append(f"    -> busy={app._d_busy}")
app._handle = spy
def kick():
    app.nb.select(1)
    app.d_search_var.set("斗破苍穹")
    app.on_discover_search()
    trace.append(f"kick done busy={app._d_busy} pend={app._d_pending is not None}")
app.after(900, kick)
def done():
    trace.append(f"FINAL stat={app.d_stat_var.get()} busy={app._d_busy}")
    app.destroy()
app.after(13000, done); app.after(30000, app.destroy)
app.mainloop()
print("\n".join(trace))
