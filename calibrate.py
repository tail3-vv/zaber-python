from zaber_motion import Units
from zaber_motion.ascii import Connection
from zaber_motion.exceptions import MovementFailedExceptionData
from zaber_cli import ZaberCLI

# TODO: possibly turn this script into a function
"""
USB connection name (ie COM3, COM4, COM5) is varies by laptop
Check device manager -> Ports (COM & LPT) to see which connection works
"""
cli = ZaberCLI()

axis = cli.axis

# unpark zaber device
if axis.is_parked():
    axis.unpark()

print(axis.get_position())
# Set position to 17mm
axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
currentPosition = axis.get_position()
currentPosition = (currentPosition * 0.04765) / 1000
print(f"Current position is: {currentPosition} mm \n")

"""
Prompt User
Move the base plate down to the designated reference height
Extrude input should be finalized after finding the distance between
starts of tip at 17mm and base after moving down to reference height=22mm 
"""
Extrude = int(input("How far to go down for alignment in mm:"))
axis.move_relative(Extrude, Units.LENGTH_MILLIMETRES)

print("\nEnsure plates are parallel. \n")
Retract = int(input("Once plates are parallel, input '17' to move tip to original position:"))
axis.move_absolute(Retract, Units.LENGTH_MILLIMETRES)

print("\nPlace sensor on and start respective test.\n")
axis.park()
cli.disconnect()