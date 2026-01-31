import tkinter as tk
from tkinter import ttk
from main_window import MainWindow
from analysis_window import AnalysisWindow

class App(tk.Tk):
    """Main application controller that manages view switching"""
    
    def __init__(self):
        super().__init__()
        self.title("Zaber Control Stage")
        self.geometry("625x375")
        self.resizable(False, False)
        
        # Container for all frames
        self.container = tk.Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        
        # Dictionary to store all views
        self.frames = {}
        
        # Shared state variables for all views
        self.saved_path = tk.StringVar()
        self.sensor_id = tk.StringVar()
        self.is_create_files = tk.BooleanVar(value=1)
        self.is_pause_between_runs = tk.BooleanVar(value=1)
        self.is_test_started = tk.BooleanVar(value=0)
        self.n_runs = tk.IntVar(value=3)
        self.current_run = tk.IntVar(value=1)
        self.zaber_comport = tk.StringVar(value="COM3")
        self.test_type = tk.StringVar(value="EB")
        self.surface_area = tk.StringVar(value="325mm2")
        self.toggle_pause = tk.IntVar(value=0)
        
        # Create all views
        self._create_views()
        
        # Show the main window first
        self.show_frame(MainWindow)
    
    def _create_views(self):
        """Initialize all view frames"""
        for FrameClass in (MainWindow, AnalysisWindow):
            frame = FrameClass(self.container, self)
            self.frames[FrameClass] = frame
            frame.grid(row=0, column=0, sticky="nsew")
    
    def show_frame(self, cont):
        """Raise the specified frame to the front"""
        frame = self.frames[cont]
        frame.tkraise()
    
    def switch_to_analysis(self):
        """Navigate to analysis view"""
        self.show_frame(AnalysisWindow)
    
    def switch_to_main(self):
        """Navigate back to main view"""
        self.show_frame(MainWindow)


if __name__ == "__main__":
    app = App()
    app.mainloop()
