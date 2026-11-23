import sys, os, ctypes, ctypes.wintypes as w
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
from PIL import ImageGrab

app = gui.App()
app.geometry("1160x800+40+40")
shots = []

def grab(name):
    app.update_idletasks(); app.update()
    hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
    r = w.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    p = rf"D:\deepseekproject\shots\{name}.png"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p)
    shots.append((p, img.size))

def s1():
    app.nb.select(1)
    app.d_src_var.set("总排行")
    app.on_discover_load()
    app.after(7000, s2)

def s2():
    grab("01_rank_total")
    app.d_tree.selection_set(app.d_tree.get_children()[0])
    app.after(600, s3)

def s3():
    grab("02_rank_detail")
    app.d_search_var.set("命运奇异赝品")
    app.on_discover_search()
    app.after(9000, s4)

def s4():
    grab("03_search")
    app.nb.select(0)
    app.after(800, s5)

def s5():
    grab("04_download_tab")
    app.destroy()

app.after(1200, s1)
app.after(60000, app.destroy)
app.mainloop()
for p, sz in shots:
    print(f"{p}  {sz[0]}x{sz[1]}  {os.path.getsize(p)} 字节")
