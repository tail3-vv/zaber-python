import tkinter as tk
from shear_window import ShearWindow

def launch_graph():
    # We pass 'root' to the class so it knows who its parent is
    window = ShearWindow(root)

root = tk.Tk()
root.title("Main Dashboard")
root.geometry("300x200")

btn = tk.Button(root, text="Open Live Graph", command=launch_graph)
btn.pack(pady=50, padx=50)

root.mainloop()