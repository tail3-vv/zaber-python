from zaber_motion import Units
from zaber_cli import ZaberCLI
from futek_cli import FUTEKDeviceCLI
import xlsxwriter
from pathlib import Path
from datetime import datetime
import numpy as np
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
isNewerUSB225 = 1 #### do we need this?

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
    force_readings = [0] * 1000 # 1-D array of zeros
    init_time = datetime.now()
    init_seconds = init_time.second + init_time.microsecond / 1e6

    # Move actuator down
    zaber.axis.move_velocity(speed*0.1, Units.VELOCITY_MILLIMETRES_PER_SECOND)
    init_val = 0 # initial value for force
    force_idx = 0
    while True:
        reading_force = futek.getNormalData() # Read force value

        if isNewerUSB225:
            reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity

        if init_force: # Verify initial values
            init_val = reading_force # TODO: There should be an easier way than this flag
            init_force = 0
        
        # Take the residual of the current force vs inital one
        # Store residual in force_readings and print out residual
        stage_force = reading_force - init_val
        force_readings[force_idx] = stage_force
        force_idx = force_idx + 1
        print("Force Value: " + str(force_idx))

        # Once sample is hit, stop the axis
        if stage_force >= upper_limit:
            zaber.axis.stop()
            break
    
    # Move actuator back up
    zaber.axis.move_velocity(-speed*2, Units.VELOCITY_MILLIMETRES_PER_SECOND)
    while True:
        reading_force = futek.getNormalData()

        if isNewerUSB225:
            reading_force = reading_force * (-4.44822) # convert pounds to Newtons and change polarity

        # Take the residual of the current force vs inital one
        # Store residual in force_readings and print out residual
        stage_force = reading_force - init_val
        force_readings[force_idx] = stage_force
        force_idx = force_idx + 1
        print("Force Value: " + str(force_idx))

        # Grab current position
        curr_pos = zaber.axis.get_position()
        last_position = (curr_pos*0.047625)/1000
        print("Position: " + str(last_position))
        if last_position <= (currentPosition*0.047625)/1000:
            zaber.axis.stop()
            break

    # move back to original position
    zaber.axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
    print("Run " + str(run_idx) + " completed")

    # Save data to run file
    # We could make this a separate function
    file_name = "Run " + str(run_idx + 1) + ".xlsx" # create file name TODO: Will need to create folder if it does not exist 
    path = Path("./FUT/" + file_name)
    workbook = xlsxwriter.Workbook(file_name)
    worksheet = workbook.add_worksheet(str(run_idx + 1))

    # Create Column headers
    worksheet.write('A1', 'Index')
    worksheet.write('B1', 'Load Cell')
    worksheet.write('C1', 'Time')

    # create time array

    time = np.linspace(init_seconds, 
                    (len(force_readings)- 1) * 0.016 + init_seconds,
                    len(force_readings))
    
    # Save data arrays to file
    for index in range(len(force_readings)):
        worksheet.write(index+1, 0, index + 1)
        worksheet.write(index+1, 1, force_readings[index])
        worksheet.write(index+1, 2, time[index])
    workbook.close()

    # Pause current run, reset sensor position manually and press enter to go to next run
    if(run_idx != num_runs - 1):
        input("Run is now paused.\nPress Enter to Continue to next run")
    else:
        print("All runs complete.")

zaber.disconnect()
