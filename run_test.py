from zaber_motion import Units
from zaber_cli import ZaberCLI
from futek_cli import FUTEKDeviceCLI
import xlsxwriter
from pathlib import Path
"""
This is where the real test will be run. 
TODO: implement the other debug scripts later
"""

init_pos = 5
init_coef = 1
speed = 0.5 # speed of travel in mm/s (millimeter/second)
upper_limit = 20 # 32 Newtons
num_runs = 3 # Number of test runs per sensor
Extract = 12.75 # initial travel distance before starting test cycle
Cycle_Speed = 0.01 # speed of travel in mm/s

# Zaber setup
zaber = ZaberCLI()

# Futek Load Cell setup
futek = FUTEKDeviceCLI()

# Move 12.75 before cycle
# Keep constant:setting gap distance between base with sensor to tip to 1.5mm
zaber.axis.move_relative((Extract-1.8), Units.LENGTH_MILLIMETRES)

# Display current position in mm after relative move
currentPosition = zaber.axis.get_position()
currentPosition_mm = (currentPosition*0.047625)/1000
print("Current Position is: {currentPosition_mm:.2f} mm \n")

# Begin Test Loop
for run_idx in range(num_runs):
    #Initial params per cycle
    init_force = 1
    temp = [0] * 1000 # 1-D array of zeros
    file_name = "Run " + str(run_idx + 1)


zaber.disconnect()