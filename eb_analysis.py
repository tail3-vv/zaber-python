from pathlib import Path
import numpy as np
import pandas as pd
from scipy import interpolate
import copy
import matplotlib.pyplot as plt

from scipy.signal import find_peaks
from scipy.ndimage import uniform_filter1d
import pickle

class Analysis():
    def __init__(self, path, sensor_id, sensor_type):
        """
        Initialize Analysis with parameters
        
        Parameters:
            path: Path to data directory
            sensor_id: Sensor ID number
            sensor_type: 1 or 3 (2 is archived)
        """
        # Store parameters
        self.sensor_id = sensor_id
        self.path = Path(path) # this is because Path(path) is in fut folder
        self.sensor_type = sensor_type
        print(self.path)
        
        # Initialize channel order based on sensor type
        if sensor_type == 1:
            self.ch_order = np.arange(1, 9)
        elif sensor_type == 3:
            self.ch_order = np.array([1, 2, 3, 4, 8, 7, 6, 5])
        else:
            raise ValueError(f"Invalid sensor_type: {sensor_type}")

        # Define paths and get file lists
        self.cap_path = Path(path) / "CAP"
        self.fut_path = Path(path) / "FUT"

        csv_files = sorted(self.cap_path.glob("*.csv"))
        xlsx_files = sorted(self.fut_path.glob("*.xlsx"))
        self.cap_size = len(csv_files)

        # Load data
        self.cap, self.fut = self._create_data(csv_files, xlsx_files)

        # Define pressure parameters
        self.start_force = 0  # kPa
        self.end_force = 45  # kPa
        
        self.ch = 8  # number of channels in sensor
        self.v = 5   # PCB Board Version: v2 = 2 | v3 = 5

        self.SA = 325e-6  # Eco Blox surface area (325mm2)

        # Correct channel order
        self.cap = self._correct_ch_order(self.cap)

        # Initialize storage lists
        self.run = []
        self.t_c = []
        self.t_f = []
        self.test = []
        self.c = np.zeros((self.cap_size, self.ch))
        self.shorted_ch = None

        self.zaber_x = []
        self.zaber_y = []
        self.fir_dev = []
        self.valz = []
        self.locz = []
        self.max_ps = []
        self.max_kPa = []
        self.inf_CAP = []
        self.cap_inc = []

        # Numeric arrays for results
        self.max_ps_numeric = np.zeros((self.cap_size, self.ch))
        self.max_kPa_numeric = np.zeros((self.cap_size, self.ch))
        self.inf_CAP_numeric = np.zeros((self.cap_size, self.ch))

        # Run the analysis pipeline
        self._interp_cap()
        self._synch_and_plot()
        self._derive_and_plot()
        self._plot_all_chs_across_runs()
        self._plot_all_runs_across_chs()

    def _create_data(self, csv_files, xlsx_files):
        """Load CAP and FUT data from files"""
        cap = []
        fut = []

        for f in csv_files:
            cap.append(pd.read_csv(f, usecols=range(16)))

        for f in xlsx_files:
            fut.append(pd.read_excel(f))
        
        return cap, fut

    def _correct_ch_order(self, cap):
        """Reorder channels according to sensor configuration"""
        reordered_cap = []

        cols = (
            list(range(0, 5)) +
            list(self.ch_order + self.v - 1) +
            list(range(13, 16))
        )

        for df in cap:
            reordered_cap.append(df.iloc[:, cols])

        return reordered_cap

    def _interp_cap(self):
        """Interpolate CAP and FUT data to 200 Hz"""
        for i in range(self.cap_size):
            # Adjust Futek Time
            time_col = self.fut[i].iloc[:, 2]
            
            if pd.api.types.is_datetime64_any_dtype(time_col):
                time_diffs = time_col.diff()
                elapsed = time_diffs.fillna(pd.Timedelta(0)).cumsum().dt.total_seconds()
            else:
                elapsed = np.concatenate([[0], np.cumsum(np.diff(time_col))])
            
            elapsed = np.array(elapsed)
            
            # There is NaN values in the CAP time column, which mess up the interpolation
            # We need to remove these NaN values before interpolation
            cap_time = self.cap[i].iloc[:, 0].values
            valid_mask = ~np.isnan(cap_time)  # Boolean mask of non-NaN values
            
            cap_time_clean = cap_time[valid_mask]
            
            # Create time vectors at 200 Hz using cleaned time
            t_c_i = np.arange(0, cap_time_clean[-1] + 0.005, 0.005)
            t_f_i = np.arange(0, elapsed[-1] + 0.005, 0.005)
            
            self.t_c.append(t_c_i)
            self.t_f.append(t_f_i)
            
            # Interpolate CAP for each channel
            cap_interp = np.zeros((len(t_c_i), self.ch))
            
            for j in range(self.ch):
                col_idx = j + self.v
                
                # Get capacitance data and remove corresponding NaN indices
                cap_data = self.cap[i].iloc[:, col_idx].values
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
            
            # Interpolate FUT
            fut_interp = np.interp(t_f_i, elapsed, self.fut[i].iloc[:, 1])
            
            # Store results
            self.run.append([cap_interp, fut_interp])

    def _synch_and_plot(self):
        """Sync CAP and FUT data by aligning peaks"""
        temp_run = copy.deepcopy(self.run)
        
        for i in range(self.cap_size):
            # Find maximum point which corresponds to when Futek released pressure from sensor (Inflection)
            temp_max_cap = np.max(temp_run[i][0], axis=0) # returns row vector of 8 channels
            self.shorted_ch = np.where(temp_max_cap > 10)[0]  # Find channels where max > 10

            # Exclude shorted channel(s) when identifying max CH to sync FUT data
            temp_run[i][0][:,self.shorted_ch] = 0

            # identify channel with the highest change in capacitance - sync signals based on this channel
            max_per_channel = np.max(temp_run[i][0], axis=0)
            chan = np.argmax(max_per_channel)  # Channel with highest max

            # Find location of maximum values
            loc_c = np.argmax(self.run[i][0], axis=0)  # Index of max for each channel
            loc_f = np.argmax(self.run[i][1])  # Index of max for FUT
            M = self.run[i][1][loc_f]  # Max value of FUT
            
            # Calculate offset (number of data points to offset by)
            offset = int((self.t_c[i][loc_c[chan]] - self.t_f[i][loc_f]) * 200)

            if offset > 0:
                # CAP starts after FUT - shift CAP backward
                timec = self.t_c[i][offset:]-(offset*(1/200))
                caps = self.run[i][0][offset:, :]

                # Trim to loc_f to ensure same length:
                # Use loc_f to ensure that data points are exactly 
                # the same length between cap and force
                test_cap = np.column_stack([timec[:loc_f], caps[:loc_f, :]])

                timef = self.t_f[i][:]
                futs = self.run[i][1][:]

                # Normalize by surface area and convert to kPa
                test_fut = np.column_stack([timef[:loc_f], futs[:loc_f] / self.SA / 1000])    

            else:

                offset = abs(offset)
                timec = self.t_c[i][:]
                caps = self.run[i][0][:,:]  
                test_cap = np.column_stack([timec[:loc_f], caps[:loc_f, :]])
                
                timef = self.t_f[i][offset:]-(offset*(1/200))
                futs = self.run[i][1][offset:]
                test_fut = np.column_stack([timef[:loc_f], futs[:loc_f] / self.SA / 1000])   

            self.c[i,:] = np.max(caps, axis=0) # finding max CAP of all channels

            ### Remove end portion (500 data points) from test data to combat
            ### instances where the last data points include the drop off values
            test_cap = test_cap[:-500, :]
            test_fut = test_fut[:-500, :]

            # Store results
            self.test.append([test_cap, test_fut])

            # Plot the Raw Signal of All Channels and Runs
            for j in range(self.ch):
                fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12))

                # Subplot 1: CAP vs Time
                ax1.plot(self.test[i][0][:, 0], self.test[i][0][:, j+1])
                ax1.set_ylabel('Change in CAP (pF)', fontsize=12)
                ax1.set_xlabel('Time (s)', fontsize=12)
                ax1.set_title(f'Raw Signal - Run #{i+1} - CH{j+1}', fontsize=14, fontweight='bold')
                ax1.grid(True, alpha=0.3)

                # Subplot 2: Force vs Time
                ax2.plot(self.test[i][1][:, 0], self.test[i][1][:, 1])
                ax2.set_ylabel('Force (kPa)', fontsize=12)
                ax2.set_xlabel('Time (s)', fontsize=12)
                ax2.grid(True, alpha=0.3)

                # Subplot 3: CAP vs Force (Hysteresis)
                ax3.plot(self.test[i][1][:, 1], self.test[i][0][:, j+1])
                ax3.set_xlabel('Force (kPa)', fontsize=12)
                ax3.set_ylabel('Change in CAP (pF)', fontsize=12)
                ax3.grid(True, alpha=0.3)

                # Link x-axes of first two subplots
                ax1.sharex(ax2)
                # Adjust layout to prevent overlap
                plt.tight_layout()

                # Save figure
                filename = f'Raw Signal_Run #{i+1}_CH{j+1}.png'
                plt.savefig(filename, dpi=300, bbox_inches='tight')
                
                # Close figure to free memory
                plt.close(fig)

    def _derive_and_plot(self):
        """Determine 1st derivative and incremental points on the P.S Curve"""
        # Iterate through each Run
        for i in range(self.cap_size):
            # Create fig with all channels
            fig = plt.figure(figsize=(20, 10))

            # Initial storage for this run
            zaber_x_i = None
            zaber_y_i = []
            fir_dev_i = []
            valz_i = []
            locz_i = []
            max_ps_i = []
            max_kPa_i = []
            inf_CAP_i = []
            cap_inc_i = []

            # Iterate through each Channel
            for j in range(self.ch):
                # Find start and end indices based on force thresholds
                k = np.where(self.test[i][1][:,1] - self.start_force > 0)[0][0]
                f = np.where(self.test[i][1][:,1] - self.end_force > 0)[0][0]

                x = self.test[i][1][k:f, 1]  # Force data
                y = self.test[i][0][k:f, j+1]  # CAP data for channel j
                
                # Smooth data (using moving average with window=100)
                st_pt = np.where(x-0 > 0)[0][0]

                # Smooth x and y
                x_smooth = uniform_filter1d(x[st_pt:], size=100, mode='nearest')
                y_smooth = uniform_filter1d(y[st_pt:], size=100, mode='nearest')

                # Store smoothed data (x is same for all channels)
                if zaber_x_i is None:
                    zaber_x_i = x_smooth
                zaber_y_i.append(y_smooth)

                # 1st derivative of P.S Curve
                fir_dev_ij = np.diff(y_smooth) / np.diff(x_smooth)

                ### First round of filter: set values > 1 or < 0 to 0
                fir_dev_ij[(fir_dev_ij > 1) | (fir_dev_ij < 0)] = 0

                # Find peaks in first derivative
                peaks, properties = find_peaks(fir_dev_ij, 
                                            prominence=0.08, 
                                            width=300)
                
                if len(peaks) > 1:
                    # Multiple peaks found - select the one with max prominence
                    peak_values = fir_dev_ij[peaks]
                    max_idx = np.argmax(peak_values)
                    locz_ij = peaks[max_idx]
                    valz_ij = peak_values[max_idx]
                elif len(peaks) == 1:
                    locz_ij = peaks[0]
                    valz_ij = fir_dev_ij[locz_ij]
                else:
                    locz_ij = None
                    valz_ij = None

                ### Second round of filter: set values > max peak to 0
                if valz_ij is not None:
                    fir_dev_ij[fir_dev_ij > valz_ij] = 0
                
                fir_dev_i.append(fir_dev_ij)

                # Pressure at max pressure sensitivity: 1st derivative
                if valz_ij is None or locz_ij is None:
                    max_ps_i.append(np.nan)
                    max_kPa_i.append(np.nan)
                    inf_CAP_i.append(np.nan)
                    self.max_ps_numeric[i, j] = np.nan
                    self.max_kPa_numeric[i, j] = np.nan
                    self.inf_CAP_numeric[i, j] = np.nan
                else:
                    max_ps_i.append(valz_ij)
                    max_kPa_i.append(x_smooth[locz_ij])
                    inf_CAP_i.append(y_smooth[locz_ij])
                    self.max_ps_numeric[i, j] = valz_ij
                    self.max_kPa_numeric[i, j] = x_smooth[locz_ij]
                    self.inf_CAP_numeric[i, j] = y_smooth[locz_ij]
                
                # Find CAP values at 5 kPa increments (5, 10, 15, ..., 45 kPa)
                cap_inc_ij = []
                for p in range(1, 10):  # 1 to 9
                    inc_mult = p * 5
                    # Find index where x is closest to inc_mult
                    idx = np.argmin(np.abs(x_smooth - inc_mult))
                    if np.abs(x_smooth[idx] - inc_mult) < 2.0:
                        cap_inc_ij.append(y_smooth[idx])
                    else:
                        cap_inc_ij.append(np.nan)
                cap_inc_i.append(cap_inc_ij)

                # Plot P.S curve with 1st derivative inflection
                ax = plt.subplot(2, 4, j+1)
                ax.set_title(f'Run# {i+1} - CH {j+1}', fontsize=12, fontweight='bold')
                
                # Left y-axis: CAP
                ax.plot(x_smooth, y_smooth, '-o', markersize=2, 
                        linewidth=1.5, color='tab:blue', label='CAP')
                if locz_ij is not None:
                    ax.plot(x_smooth[locz_ij], y_smooth[locz_ij], 'or', 
                        markersize=10, linewidth=2, label='Inflection Point')
                ax.set_xlabel('Force (kPa)', fontsize=10)
                ax.set_ylabel('Change in CAP (pF)', fontsize=10, color='tab:blue')
                ax.tick_params(axis='y', labelcolor='tab:blue')

                # Right y-axis: 1st derivative
                ax2 = ax.twinx()
                ax2.plot(x_smooth[:-1], fir_dev_ij, color='tab:orange', 
                        linewidth=1.5, label='1st Derivative')
                if locz_ij is not None:
                    ax2.plot(x_smooth[locz_ij], fir_dev_ij[locz_ij], 'ok', 
                            markersize=8, linewidth=2, label='Max Slope')
                ax2.set_ylabel('1st Derivative (pF/kPa)', fontsize=10, color='tab:orange')
                ax2.tick_params(axis='y', labelcolor='tab:orange')
                
                ax.grid(True, alpha=0.3)

            # Store data for this run
            self.zaber_x.append(zaber_x_i)
            self.zaber_y.append(zaber_y_i)
            self.fir_dev.append(fir_dev_i)
            self.valz.append(valz_i)
            self.locz.append(locz_i)
            self.max_ps.append(max_ps_i)
            self.max_kPa.append(max_kPa_i)
            self.inf_CAP.append(inf_CAP_i)
            self.cap_inc.append(cap_inc_i)
            
            plt.tight_layout()

            # Save figure
            filename = f'PS curve all CHs number #{i+1}.png'
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            plt.close(fig)

    def _plot_all_chs_across_runs(self):
        """Plot P.S curves of all channels across runs"""
        fig, axes = plt.subplots(1, self.cap_size, figsize=(8*self.cap_size, 6))
        fig.suptitle('P.S Curves of All CHs Across Runs', fontsize=16, fontweight='bold')

        for i in range(self.cap_size):
            print(f"Processing run {i+1}/{self.cap_size}...")
            
            for j in range(self.ch):
                # Find start point
                k = np.where(self.test[i][1][:, 1] - self.start_force > 0)[0][0]
                
                # Find end point based on max force from first run
                max_force_threshold = np.floor(np.max(self.test[0][1][:, 1]) - 1)
                f = np.where(self.test[i][1][:, 1] - max_force_threshold > 0)[0][0]
                
                x = self.test[i][1][k:f, 1]  # Force data
                y = self.test[i][0][k:f, j+1]  # CAP data for channel j
                
                # Smooth data
                st_pt = np.where(x - 0 > 0)[0][0]
                
                x_smooth = uniform_filter1d(x[st_pt:], size=100, mode='nearest')
                y_smooth = uniform_filter1d(y[st_pt:], size=100, mode='nearest')
                
                # Plot P.S curve
                axes[i].plot(x_smooth, y_smooth, '-', linewidth=2, label=f'Ch. #: {j+1}')
                axes[i].set_title(f'Run {i+1}', fontsize=14, fontweight='bold')
                axes[i].set_xlabel('Force (kPa)', fontsize=12)
                axes[i].set_ylabel('Change in CAP (pF)', fontsize=12)
                axes[i].grid(True, alpha=0.3)
                axes[i].legend(loc='lower right', fontsize=10)

        plt.tight_layout()
        filename = 'PS curves all ch per run.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close(fig)

    def _plot_all_runs_across_chs(self):
        """Plot P.S curves of all runs across channels"""
        fig, axes = plt.subplots(2, 4, figsize=(20, 10))
        fig.suptitle('P.S Curves of All Runs Across Channels', fontsize=18, fontweight='bold')

        # Flatten axes for easier indexing
        axes = axes.flatten()

        # Define colors for each run
        num_runs = len(self.test)
        colors = plt.cm.tab10(np.linspace(0, 1, num_runs))
        for i in range(num_runs):
            for j in range(self.ch):
                # Plot P.S curve for run i, channel j
                axes[j].plot(self.zaber_x[i], self.zaber_y[i][j], '-', 
                            linewidth=2.5, 
                            color=colors[i],
                            label=f'Run {i+1}',
                            alpha=0.8)
                
                axes[j].set_title(f'CH {j+1}', fontsize=14, fontweight='bold')
                axes[j].set_xlabel('Force (kPa)', fontsize=11)
                axes[j].set_ylabel('Change in CAP (pF)', fontsize=11)
                axes[j].grid(True, alpha=0.3)

        # Add legend to each subplot (only once after all runs are plotted)
        for j in range(self.ch):
            axes[j].legend(loc='lower right', fontsize=10, framealpha=0.9)

        # Hide extra subplots if ch < 8
        for j in range(self.ch, 8):
            axes[j].axis('off')

        plt.tight_layout()
        # Save figure
        filename = 'PS curves all run per CH.png'
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        plt.close(fig)

    def save_data(self):
        """
        Calculate and return analysis results as a dictionary.
        Calculates Mean, STD, and COV of P.S and Force at Inflection; Max CAP; Incremental CAP values
        """
        result = {}
        
        # P.S Curve Inflection Point pressure sensitivity and force: mean, std, and cov
        result['max_ps'] = self.max_ps_numeric
        result['mean_max_ps'] = np.mean(result['max_ps'], axis=0)
        result['std_max_ps'] = np.std(result['max_ps'], axis=0, ddof=1) 
        result['cov_max_ps'] = result['std_max_ps'] / result['mean_max_ps']
        
        result['max_kpa'] = self.max_kPa_numeric 
        result['mean_max_kpa'] = np.mean(result['max_kpa'], axis=0) 
        result['std_max_kpa'] = np.std(result['max_kpa'], ddof=1, axis=0)
        result['cov_max_kpa'] = result['std_max_kpa'] / result['mean_max_kpa']

        # P.S Curve Max CAP
        result['max_cap'] = self.c
        result['mean_max_cap'] = np.mean(result['max_cap'], axis=0)
        result['std_max_cap'] = np.std(result['max_cap'], ddof=1, axis=0)
        result['max_cap_cov'] = result['std_max_cap'] / result['mean_max_cap']

        # P.S Curve CAP at Inflection Point
        result['inf_cap'] = self.inf_CAP_numeric
        result['mean_inf_cap'] = np.mean(result['inf_cap'], axis=0)
        result['std_inf_cap'] = np.std(result['inf_cap'], ddof=1, axis=0)
        result['cov_inf_cap'] = result['std_inf_cap'] / result['mean_inf_cap']

        # CH Variability Calculation:
        # CHs variability across 9 incremental points along the P.S curve (increments of 5kPa)
        n_channels = len(self.cap_inc)           # Number of runs (first dimension)
        n_runs = len(self.cap_inc[0])    # Number of channels (second dimension) 
        inc_arr = []
        ch_var_center4_mean = np.zeros((n_channels, 9))
        ch_var_center4_std = np.zeros((n_channels, 9))
        ch_var_outer4_mean = np.zeros((n_channels, 9))
        ch_var_outer4_std = np.zeros((n_channels, 9))
        ch_var_allch_mean = np.zeros((n_channels, 9))
        ch_var_allch_std = np.zeros((n_channels, 9))
        
        for a in range(n_channels):
            # Collect all runs for this channel
            run_data = []
            for b in range(n_runs):
                run_data.append(self.cap_inc[a][b])
            
            # Stack into array (9 increments × n_runs)
            inc_arr.append(np.column_stack(run_data))
            
            for inc in range(9):
                # Center 4 CHs: 
                ch_var_center4_mean[a, inc] = np.mean(inc_arr[a][inc, 2:6], axis=0)
                ch_var_center4_std[a, inc] = np.std(inc_arr[a][inc, 2:6], ddof=1, axis=0)

                # Outer 4 CHs: 
                ch_var_outer4_mean[a, inc] = np.mean(inc_arr[a][inc, [0, 1, 6, 7]], axis=0)
                ch_var_outer4_std[a, inc] = np.std(inc_arr[a][inc, [0, 1, 6, 7]], ddof=1, axis=0)

                # All CHs
                ch_var_allch_mean[a, inc] = np.mean(inc_arr[a][inc, :], axis=0)
                ch_var_allch_std[a, inc] = np.std(inc_arr[a][inc, :], ddof=1, axis=0)

        # save data for CH variability calculation for center 4 CHs
        result['inc_arr'] = inc_arr
        result['ch_var_center4_mean'] = ch_var_center4_mean
        result['ch_var_center4_std'] = ch_var_center4_std
        result['ch_var_center4_cov'] = result['ch_var_center4_std'] / result['ch_var_center4_mean']
        result['avg_ch_var_center4_mean'] = np.mean(result['ch_var_center4_mean'], axis=0)
        result['avg_ch_var_center4_cov'] = np.mean(result['ch_var_center4_cov'], axis=0)

        # save data for CH variability calculation for outer 4 CHs
        result['ch_var_outer4_mean'] = ch_var_outer4_mean
        result['ch_var_outer4_std'] = ch_var_outer4_std
        result['ch_var_outer4_cov'] = result['ch_var_outer4_std'] / result['ch_var_outer4_mean']
        result['avg_ch_var_outer4_mean'] = np.mean(result['ch_var_outer4_mean'], axis=0)
        result['avg_ch_var_outer4_cov'] = np.mean(result['ch_var_outer4_cov'], axis=0)

        # Save data for CH variability calculation for all CHs
        result['ch_var_allch_mean'] = ch_var_allch_mean
        result['ch_var_allch_std'] = ch_var_allch_std
        result['ch_var_allch_cov'] = result['ch_var_allch_std'] / result['ch_var_allch_mean']
        result['avg_ch_var_allch_mean'] = np.mean(result['ch_var_allch_mean'], axis=0)  # Average across runs
        result['avg_ch_var_allch_cov'] = np.mean(result['ch_var_allch_cov'], axis=0)    # Average across runs

        result['shorted_ch'] = self.shorted_ch

        # CAP and FUT data
        result['test'] = self.test

        # zaber_x and zaber_y data
        result['zaber_x'] = self.zaber_x
        result['zaber_y'] = self.zaber_y

        return result


