import sys, os, ctypes, ctypes.wintypes as w
sys.path.insert(0, r"D:\deepseekproject\agedl")
import gui
from PIL import ImageGrab
app = gui.App(); app.geometry("1160x800+40+40")
shots=[]
def grab(name):
    app.update_idletasks(); app.update()
    hwnd = ctypes.windll.user32.GetParent(app.winfo_id())
    r = w.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    img = ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom))
    p = rf"D:\deepseekproject\shots\{name}.png"; os.makedirs(os.path.dirname(p), exist_ok=True)
    img.save(p); shots.append(p)
def s1():
    app.nb.select(1); app.d_src_var.set("总排行"); app.on_discover_load(); app.after(7000, s2)
def s2():
    grab("11_rank"); app.d_tree.selection_set(app.d_tree.get_children()[0]); app.after(7000, s3)
def s3():
    grab("12_rank_detail"); app.d_search_var.set("命运"); app.on_discover_search(); app.after(9000, s4)
def s4():
    grab("13_search"); app.d_search_var.set("斗破"); app.on_discover_search(); app.after(9000, s5)
def s5():
    grab("14_search2"); app.destroy()
app.after(1200, s1); app.after(60000, app.destroy)
app.mainloop()
for p in shots: print(p, os.path.getsize(p))
