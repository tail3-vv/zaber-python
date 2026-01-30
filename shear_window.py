import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import matplotlib.ticker as ticker

import tkinter as tk
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.figure import Figure
from matplotlib.animation import FuncAnimation
import numpy as np
import time
from datetime import datetime
#from futek_cli import FUTEKDeviceCLI

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
        self.ax.set_xlabel("Time Elapsed (seconds)")
        self.ax.set_ylabel("Force (N)")
        
        # Format x-axis to show MM:SS format
        def format_time(x, pos):
            minutes = int(x // 60)
            seconds = int(x % 60)
            return f"{minutes}:{seconds:02d}"
        self.ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_time))
        
        self.indices = []

        # This connects Matplotlib and tkinter together
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.draw()

        # Create navigation toolbar for matplotlib
        self.toolbar = NavigationToolbar2Tk(self.canvas, self, pack_toolbar=False)
        self.toolbar.update()

        # Create an end test button
        self.exit_btn = tk.Button(self, text="Save and Exit", 
                             command=self.on_close, 
                             width=15, height=1)

        # Pack all widgets
        self.exit_btn.pack(side=tk.BOTTOM, pady=10, padx=10)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)


        # Initialize Load Cell and read initial values
        #self.futek = FUTEKDeviceCLI()
        reading_force = 0 #self.futek.getNormalData() 
        reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        self.init_val = reading_force 
        self.init_force = 0
        self.force_readings = []

        # Find Current Time
        self.init_time = datetime.now()
        self.time_readings = []
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
        current_indice = len(self.indices)
        self.indices.append(current_indice)
        
        current_time = datetime.now()
        elapsed_time = (current_time - self.init_time).total_seconds()
        self.time_readings.append(elapsed_time)
        # Read force values on load cell
        reading_force = 0#self.futek.getNormalData() 
       # reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity
        stage_force = reading_force - self.init_val

        # Append force readings to y axis
        #self.force_readings[current_time] = stage_force
        self.force_readings.append(stage_force)

        if len(self.time_readings) > 100:
            self.ax.set_xlim(self.time_readings[-100], self.time_readings[-1])
            
        self.line.set_data(self.time_readings, self.force_readings)
        return self.line,

    def save(self):
        """ Save plot aswell and related tables """
        pass
    
    def on_close(self):
        print("saving and closing")
       # self.futek.stop()
       # self.futek.exit()
        self.main_window._end_testing()
        self.anim.event_source.stop()
        self.destroy()