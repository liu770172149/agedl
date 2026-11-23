import gui, time
app = gui.App()
log=[]
def step1():
    app.url_var.set("https://www.age001.com/play/12537-1-1.html")
    app.on_parse(); app.after(30000, step2)
def step2():
    log.append("info=" + app.info_var.get())
    for iid in app.tree.get_children()[:2]:
        log.append("  " + str(app.tree.item(iid,"values")))
    app.destroy()
app.after(500, step1); app.after(45000, app.destroy)
app.mainloop()
print("\n".join(log)); print("DONE")
