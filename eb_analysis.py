
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import interpolate
import copy
import matplotlib.pyplot as plt
"""
Parameters for this function that will be called from the main class
"""
sensor_id = 12345
path = f'C:/Users/emili/OneDrive/Documents/Projects/VenaVitals/zaber-python/12345/02 02 26_325mm2_EB'
sensor_type = 1 # could be 1 or 3 (2 is being archived)

"""
Variables Derived from params
"""
if sensor_type == 1:
    ch_order = np.arange(1, 9)
if sensor_type == 3:
    ch_order = np.array([1,2,3,4,8,7,6,5])

cap_path = Path(path) / "CAP"
fut_path = Path(path) / "FUT"

csv_files  = sorted(cap_path.glob("*.csv"))
xlsx_files = sorted(fut_path.glob("*.xlsx"))
cap_size = len(csv_files)

"""
Find Data folder and copy over files
"""
def create_data(csv_files, xlsx_files):
    cap = []
    fut = []

    for f in csv_files:
        cap.append(pd.read_csv(f, usecols=range(16)))

    for f in xlsx_files:
        fut.append(pd.read_excel(f))
    return cap, fut

cap, fut = create_data(csv_files, xlsx_files)

"""
 Define Pressure Range, # of CH, PCB Board Version, and Eco Blox Surface Area
 TODO: Should this be editable in GUI?
"""
start_force = 0; #kPa
end_force = 45; #kPa
 
ch = 8; # number of channels in sensor
v = 5;  # PCB Board Version: v2 = 2 | v3 = 5

SA = 325e-6; # Eco Blox surface area, current SA is 325mm2

def correct_ch_order(cap):
    """
    Use selected sensor ch order to correct the ch order
    """
    reordered_cap = []

    cols = (
        list(range(0, 5)) +
        list(ch_order + v - 1) +
        list(range(13, 16))
    )

    for df in cap:
        reordered_cap.append(df.iloc[:, cols])

    return reordered_cap
cap = correct_ch_order(cap)

"""
Interpolate CAP for each channel and FUT to 200 Hz
"""
run = []
t_c = []
t_f = []
def interp_cap():
    for i in range(cap_size):
        # Adjust Futek Time
        time_col = fut[i].iloc[:, 2]
        
        if pd.api.types.is_datetime64_any_dtype(time_col):
            time_diffs = time_col.diff()
            elapsed = time_diffs.fillna(pd.Timedelta(0)).cumsum().dt.total_seconds()
        else:
            elapsed = np.concatenate([[0], np.cumsum(np.diff(time_col))])
        
        elapsed = np.array(elapsed)
        
        # There is NaN values in the CAP time column, which mess up the interpolation
        # We need to remove these NaN values before interpolation
        cap_time = cap[i].iloc[:, 0].values
        valid_mask = ~np.isnan(cap_time)  # Boolean mask of non-NaN values
        
        cap_time_clean = cap_time[valid_mask]
        
        # Create time vectors at 200 Hz using cleaned time
        t_c_i = np.arange(0, cap_time_clean[-1] + 0.005, 0.005)
        t_f_i = np.arange(0, elapsed[-1] + 0.005, 0.005)
        
        t_c.append(t_c_i)
        t_f.append(t_f_i)
        
        # Interpolate CAP for each channel
        cap_interp = np.zeros((len(t_c_i), ch))
        
        for j in range(ch):
            col_idx = j + v
            
            # Get capacitance data and remove corresponding NaN indices
            cap_data = cap[i].iloc[:, col_idx].values
            cap_data_clean = cap_data[valid_mask]  # Use same mask as time
            
            # Subtract baseline (first valid value)
            baseline = cap_data_clean[0]
            cap_data_clean = cap_data_clean - baseline
            
            # Interpolate with cleaned data
            cap_interp[:, j] = np.interp(
                t_c_i,                  # New time grid
                cap_time_clean,         # Cleaned original time
                cap_data_clean          # Cleaned capacitance data
            )
        
        # Interpolate FUT (same process if needed)
        fut_interp = np.interp(t_f_i, elapsed, fut[i].iloc[:, 1])
        
        # Store results
        run.append([cap_interp, fut_interp])


interp_cap() # list (length 3) of dicts

'''
Sync CAP and FUT by aligning peaks
'''

temp_run = copy.deepcopy(run)
test = []  # Will store synchronized data
c = np.zeros((cap_size, ch))  # Store max CAP values for all channels

def synch():
    for i in range(cap_size):
        # Find maximum point which corresponds to when Futek released pressure from sensor (Inflection)
        temp_max_cap = np.max(temp_run[i][0], axis=0) # returns row vector of 8 channels
        shorted_ch = np.where(temp_max_cap > 10)[0]  # Find channels where max > 10

        # Exclude shorted channel(s) when identifying max CH to sync FUT data
        temp_run[i][0][:,shorted_ch] = 0

        # identify channel with the highest change in capacitance - sync signals based on this channel
        max_per_channel = np.max(temp_run[i][0], axis=0)
        chan = np.argmax(max_per_channel)  # Channel with highest max

        # Find location of maximum values
        loc_c = np.argmax(run[i][0], axis=0)  # Index of max for each channel
        loc_f = np.argmax(run[i][1])  # Index of max for FUT
        M = run[i][1][loc_f]  # Max value of FUT
        
        # Calculate offset (number of data points to offset by)
        offset = int((t_c[i][loc_c[chan]] - t_f[i][loc_f]) * 200)

        if offset > 0:
            # CAP starts after FUT - shift CAP backward
            timec = t_c[i][offset:]-(offset*(1/200))
            caps = run[i][0][offset:, :]

            # Trim to loc_f to ensure same length:
            # Use loc_f to ensure that data points are exactly 
            # the same length between cap and force
            test_cap = np.column_stack([timec[:loc_f], caps[:loc_f, :]])

            timef = t_f[i][:]
            futs = run[i][1][:]

            # Normalize by surface area and convert to kPa
            test_fut = np.column_stack([timef[:loc_f], futs[:loc_f] / SA / 1000])    

        else:

            offset = abs(offset)
            timec = t_c[i][:]
            caps = run[i][0][:,:]
            test_cap = np.column_stack([timec[:loc_f], caps[:loc_f, :]])
            
            timef = t_f[i][offset:]-(offset*(1/200))
            futs = run[i][1][offset:]
            test_fut = np.column_stack([timef[:loc_f], futs[:loc_f] / SA / 1000])   

        c[i,:] = np.max(caps, axis=0) # finding max CAP of all channels

        ### Remove end portion (500 data points) from test data to combat
        ### instances where the last data points include the drop off values
        test_cap = test_cap[:-500, :]
        test_fut = test_fut[:-500, :]

        # Store results
        test.append([test_cap, test_fut])

        """
        Now within the same loop, we can now
        Plot the Raw Signal of All Channels and Runs
        """
        for j in range(ch):
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))

            # Subplot 1: CAP vs Time
            ax1.plot(test[i][0][:, 0], test[i][0][:, j+1])
            ax1.set_ylabel('Change in CAP (pF)', fontsize=12)
            ax1.set_xlabel('Time (s)', fontsize=12)
            ax1.set_title(f'Raw Signal - Run #{i+1} - CH{j+1}', fontsize=14, fontweight='bold')
            ax1.grid(True, alpha=0.3)

            # Subplot 2: Force vs Time
            ax2.plot(test[i][1][:, 0], test[i][1][:, 1])
            ax2.set_ylabel('Force (kPa)', fontsize=12)
            ax2.set_xlabel('Time (s)', fontsize=12)
            ax2.grid(True, alpha=0.3)

            # Subplot 3: CAP vs Force (Hysteresis)
            ax3.plot(test[i][1][:, 1], test[i][0][:, j+1])
            ax3.set_xlabel('Force (kPa)', fontsize=12)
            ax3.set_ylabel('Change in CAP (pF)', fontsize=12)
            ax3.grid(True, alpha=0.3)

            # Link x-axes of first two subplots
            ax1.sharex(ax2)
            # Adjust layout to prevent overlap
            plt.tight_layout()

            # Save figure
            filename = f'analysis/test/Raw Signal_Run #{i+1}_CH{j+1}.png'
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            print(f'  Saved: {filename}')
            
            # Close figure to free memory
            plt.close(fig)


synch()