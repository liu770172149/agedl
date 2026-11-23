import sys, os, ctypes, ctypes.wintypes as w
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
from PIL import ImageGrab
OUT = r"D:\deepseekproject\shots"; os.makedirs(OUT, exist_ok=True)

def run(name, action, wait_ms):
    app = gui.App(); app.geometry("1160x800+40+40")
    app.after(900, lambda: (app.nb.select(1), action(app)))
    def shoot():
        try:
            hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
            r = w.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
            p = os.path.join(OUT, name + ".png"); img.save(p)
            print(f"{name}: {os.path.getsize(p)}B  stat={app.d_stat_var.get()}  行数={len(app.d_tree.get_children())}")
        finally:
            app.destroy()
    app.after(900 + wait_ms, shoot)
    app.after(900 + wait_ms + 20000, app.destroy)
    app.mainloop()

run("31_search", lambda a: (a.d_search_var.set("斗破苍穹"), a.on_discover_search()), 8000)
run("32_week", lambda a: (a.d_src_var.set("本周排行"), a.on_discover_load()), 6000)
run("33_new",  lambda a: (a.d_src_var.set("新番上架"), a.on_discover_load()), 6000)
