from pathlib import Path
import numpy as np
import pandas as pd
from scipy import interpolate
import matplotlib.pyplot as plt
from datetime import datetime
import pickle


class ShearAnalysis():
    def __init__(self, path, sensor_id):
        """
        Initialize Shear Analysis with parameters
        
        Parameters:
            path: Path to data directory
            sensor_id: Sensor ID number
        """
        # Store parameters
        self.sensor_id = sensor_id
        self.path = Path(path).parent  # this is because Path(path) is in fut folder


        # Define paths and get file lists
        self.cap_path = self.path / "cap"  # Changed to lowercase to match MATLAB
        self.fut_path = self.path / "fut"  # Changed to lowercase to match MATLAB

        # Load all cap and fut files
        self.csv_files = sorted(self.cap_path.glob("*.csv"))
        self.xlsx_files = sorted(self.fut_path.glob("*.xlsx"))
        self.cap_size = len(self.csv_files)

        self.ch = 8  # number of channels in sensor
        self.v = 5   # PCB Board Version: v2 = 2 | v3 = 5

        # Load data
        self.cap_data = []
        self.fut_data = []
        self._load_data()

    def _load_data(self):
        """Load all CAP and FUT files into memory"""

        for csv_file in self.csv_files:
            df = pd.read_csv(csv_file)
            self.cap_data.append(df)
        

        for xlsx_file in self.xlsx_files:
            df = pd.read_excel(xlsx_file)
            self.fut_data.append(df)
        

    def plot_cap_and_force(self):
        """
        Plot raw sensor capacitance and futek load cell data for visual inspection.
        Identifies instances where capacitance signal goes negative and/or 
        delta capacitance signal exceeds 10 pF.
        """
        # Create full-screen figure
        fig = plt.figure(figsize=(19.2, 10.8))  # Full HD resolution
        fig.canvas.manager.set_window_title('Shear Analysis')
        
        # Store axes for linking
        axes = []
        
        # Iterate through each file
        # Iterate through each file
        for file_idx in range(len(self.cap_data)):
            cap_df = self.cap_data[file_idx]
            fut_df = self.fut_data[file_idx]

            axes = []

            # ---- FUT time base ----
            if len(fut_df.columns) >= 4:
                time_col = fut_df.iloc[:, 3]

                if pd.api.types.is_datetime64_any_dtype(time_col):
                    elapsed = (
                        time_col.diff()
                        .dt.total_seconds()
                        .fillna(0)
                        .cumsum()
                        .values
                    )
                
                elif pd.api.types.is_numeric_dtype(time_col):
                    # already elapsed time (float or int)
                    elapsed = time_col.values
                else:
                    elapsed = np.arange(len(fut_df))
            else:
                elapsed = np.arange(len(fut_df))

            # ---- CAP time ----
            cap_time = cap_df.iloc[:, 0].values

            # ---- CAP channels (1–8) ----
            for ch_idx in range(self.ch):
                ax = plt.subplot(
                    9, 1, ch_idx + 1,
                    sharex=axes[0] if axes else None
                )
                axes.append(ax)

                cap_values = cap_df.iloc[:, ch_idx + self.v].values
                initial_cap = cap_values[0]
                delta_cap = cap_values - initial_cap

                # Left axis: raw CAP
                ax.plot(cap_time, cap_values, color='tab:blue')
                ax.set_ylabel('CAP (pF)', color='tab:blue')
                ax.tick_params(axis='y', labelcolor='tab:blue')
                ax.set_title(f'CH {ch_idx + 1}')
                ax.grid(True, alpha=0.3)

                # Right axis: delta CAP
                ax_r = ax.twinx()
                ax_r.plot(cap_time, delta_cap, color='tab:orange')
                ax_r.set_ylabel('ΔCAP (pF)', color='tab:orange')
                ax_r.tick_params(axis='y', labelcolor='tab:orange')

                if ch_idx < self.ch - 1:
                    ax.tick_params(labelbottom=False)

            # ---- FORCE (9th subplot) ----
            ax_force = plt.subplot(9, 1, 9, sharex=axes[0])
            axes.append(ax_force)

            if len(fut_df.columns) >= 2:
                force_values = fut_df.iloc[:, 1].values
                n = min(len(elapsed), len(force_values))
                ax_force.plot(elapsed[:n], force_values[:n], 'g-', linewidth=1.5)

            ax_force.set_ylabel('Force (N)')
            ax_force.set_xlabel('Time (s)')
            ax_force.grid(True, alpha=0.3)

        
        plt.tight_layout()
        
        # Save figure
        output_path = self.path / 'Raw Fig_ Shearing.png'
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        
        plt.show()
        plt.close()

    def analyze_shorted_channels(self):
        """
        Identify shorted channels based on:
        1. Negative capacitance values
        2. Delta capacitance exceeding 10 pF
        
        Returns:
            dict: Dictionary containing analysis results
        """
        shorted_ch_neg = {j: [] for j in range(1, self.ch + 1)}
        shorted_ch_delta_cap = {j: [] for j in range(1, self.ch + 1)}
        
        # Iterate through each file
        for file_idx in range(len(self.cap_data)):
            cap_df = self.cap_data[file_idx]
            
            # Check each channel
            for ch_idx in range(self.ch):
                ch_num = ch_idx + 1
                
                # Get capacitance data
                cap_values = cap_df.iloc[:, ch_idx + self.v].values
                initial_cap = cap_values[0]
                delta_cap = cap_values - initial_cap
                
                # Find negative values
                neg_values = cap_values[cap_values < 0]
                if len(neg_values) > 0:
                    shorted_ch_neg[ch_num].extend(neg_values.tolist())
                
                # Find delta CAP > 10 pF
                high_delta = delta_cap[delta_cap > 10]
                if len(high_delta) > 0:
                    shorted_ch_delta_cap[ch_num].extend(high_delta.tolist())
        
        # Convert to numpy arrays
        for ch_num in range(1, self.ch + 1):
            shorted_ch_neg[ch_num] = np.array(shorted_ch_neg[ch_num])
            shorted_ch_delta_cap[ch_num] = np.array(shorted_ch_delta_cap[ch_num])
        
        # Create results dictionary
        SHEAR = {
            'shorted_ch_neg': shorted_ch_neg,
            'shorted_ch_delt_CAP': shorted_ch_delta_cap,
            'sensor_id': self.sensor_id,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # Save results
        self._save_results(SHEAR)
        

        
        return SHEAR

    def _save_results(self, SHEAR):
        """Save analysis results to Excel file"""
        output_file = self.path / 'SHEAR_RESULT.xlsx'

        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            # ---- Negative capacitance sheet ----
            neg_rows = []
            for ch, values in SHEAR['shorted_ch_neg'].items():
                for v in values:
                    neg_rows.append({
                        'Channel': ch,
                        'Capacitance (pF)': v
                    })

            df_neg = pd.DataFrame(neg_rows)
            df_neg.to_excel(writer, sheet_name='Negative_CAP', index=False)

            # ---- Delta CAP > 10 pF sheet ----
            delta_rows = []
            for ch, values in SHEAR['shorted_ch_delt_CAP'].items():
                for v in values:
                    delta_rows.append({
                        'Channel': ch,
                        'Delta CAP (pF)': v
                    })

            df_delta = pd.DataFrame(delta_rows)
            df_delta.to_excel(writer, sheet_name='Delta_CAP_gt_10pF', index=False)

            # ---- Metadata sheet ----
            meta_df = pd.DataFrame({
                'Sensor ID': [SHEAR['sensor_id']],
                'Analysis Date': [SHEAR['analysis_date']]
            })
            meta_df.to_excel(writer, sheet_name='Metadata', index=False)


    def run_full_analysis(self):
        """
        Run complete shear analysis pipeline:
        1. Plot capacitance and force data
        2. Analyze shorted channels
        """

        
        # Plot data

        self.plot_cap_and_force()
        
        # Analyze shorted channels
        results = self.analyze_shorted_channels()
        
        return results


# Example usage
if __name__ == "__main__":
    # Example: Initialize with your data path
    path = "C:/Users/emili/Downloads/250527B03S03AB-20260210T193039Z-1-001/250527B03S03AB/08 04 25_50.27_SHEAR"
    analyzer = ShearAnalysis(path, sensor_id=1)
    results = analyzer.run_full_analysis()
    
    pass