import tkinter as tk
from tkinter import ttk

class AnalysisWindow(tk.Toplevel):
    """ Separate window for looking at analysis outputs """
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("Analysis")
        self.geometry("800x600")
        self.resizable(False, False)
        self.main_window = main_window
        

        # On close of window behavior
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.destroy()