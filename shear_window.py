import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation
import numpy as np
import time
from futek_cli import FUTEKDeviceCLI

"""
Window for Shear testing live graph
TODO: Add option to stop and save the graph
OR just save the graph data once the window closes, including the entire plot
"""
class ShearWindow(tk.Toplevel):
    def __init__(self, parent, main_window):
        super().__init__(parent)
        self.title("Live Sensor Data")
        self.geometry("800x600")
        self.main_window = main_window
        
        # Initial vars for plotting load cell data
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.line, = self.ax.plot([], [], 'r-', lw=2)
        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(-1.5, 1.5)
        
        self.indices = []

        # This connects Matplotlib and tkinter together
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Initialize Load Cell and read initial values
        self.futek = FUTEKDeviceCLI()
        reading_force = self.futek.getNormalData() 
        reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        self.init_val = reading_force 
        self.init_force = 0
        self.force_readings = []
        
        # Starts graphing animation
        # Storing in 'self.anim' prevents garbage collection
        self.anim = FuncAnimation(self.fig, self.update_plot, interval=50, blit=False)
        
        # On close of window behavior
        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def update_plot(self, frame):
        """ 
        This function will display the data live on the screen 
        Y-Axis: Output of load cell in Newtons
        X-Axis: Time Elapsed
        """
        # TODO: Make this actual time not indices
        current_time = len(self.indices)
        self.indices.append(current_time)
        
        # Read force values on load cell
        reading_force = self.futek.getNormalData() 
        reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        stage_force = reading_force - self.init_val

        # Append force readings to y axis
        #self.force_readings[current_time] = stage_force
        self.force_readings.append(stage_force)

        if len(self.x_data) > 100:
            self.ax.set_xlim(self.indices[-100], self.indices[-1])
            
        self.line.set_data(self.indices, self.force_readings)
        return self.line,

    def on_close(self):
        self.futek.stop()
        self.futek.exit()
        self.anim.event_source.stop()
        self.destroy()