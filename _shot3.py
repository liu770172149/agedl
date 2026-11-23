import sys, os, ctypes, ctypes.wintypes as w
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
from PIL import ImageGrab
OUT = r"D:\deepseekproject\shots"
os.makedirs(OUT, exist_ok=True)

def run(name, action, wait_ms):
    app = gui.App(); app.geometry("1160x800+40+40")
    def kick():
        app.nb.select(1)
        action(app)
    def shoot():
        try:
            hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
            r = w.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
            img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
            p = os.path.join(OUT, name + ".png"); img.save(p)
            print(f"{name}: {os.path.getsize(p)} 字节  stat={app.d_stat_var.get()}")
        finally:
            app.destroy()
    app.after(1000, kick)
    app.after(1000 + wait_ms, shoot)
    app.after(1000 + wait_ms + 20000, app.destroy)
    app.mainloop()

def a_search_show(app):
    app.d_search_var.set("斗破苍穹")
    app.on_discover_search()
run("21_search_doupo", a_search_show, 8000)

def a_rank(app):
    app.d_src_var.set("本周排行"); app.on_discover_load()
run("22_week_rank", a_rank, 6000)

def a_latest(app):
    app.d_src_var.set("最新入库"); app.on_discover_load()
run("23_latest", a_latest, 6000)
