from zaber_motion import Units, exceptions
from zaber_motion.ascii import Connection
from zaber_motion.exceptions import MovementFailedExceptionData
from zaber import ZaberCLI

try:
    with Connection.open_serial_port("COM5") as connection:
        device_list = connection.detect_devices()
        print(f"Found {len(device_list)} devices")
        device = device_list[0]
        axis = device.get_axis(1)

        # Try a movement command
        # Ensure units are correct (e.g., Length.MM for millimeters)
        axis.move_absolute(10, unit=Units.LENGTH_MILLIMETRES).wait_until_idle()

except exceptions.MovementFailedException as e:
    print(f"Movement failed due to fault: {e.details.reason}") # Prints the reason for failure
    # You can also access e.data.device and e.data.axis for more info
    
    # After a fault, you may need to home or reset the device
    try:
        print("Attempting to home the device to clear the fault...")
        axis.home().wait_until_idle()
        print("Device homed successfully.")
    except exceptions.MotionLibException as recovery_err:
        print(f"Recovery failed: {recovery_err}")

"""
USB connection name (ie COM3, COM4, COM5) is varies by laptop
Check device manager -> Ports (COM & LPT) to see which connection works
"""
# with Connection.open_serial_port("COM5") as connection:
#     # allows device to communicate back without preceding requests
#     # connection.enable_alerts()

#     # look for usb devices that are connected
#     device_list = connection.detect_devices()
#     print("Found {} devices".format(len(device_list)))

#     device = device_list[0]
#     axis = device.get_axis(1)

#     # unpark zaber device
#     if axis.is_parked():
#       axis.unpark()
#     # if not axis.is_homed():
#     #   axis.home()
#     print(axis.get_position())
#     # Set position to 17mm
#     axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
#     currentPosition = axis.get_position()
#     # currentPosition = (currentPosition * 0.04765) / 1000
#     # print("Current position is: {currentPosition} mm \n\n")

#     # """
#     # Prompt User
#     # Move the base plate down to the designated reference height
#     # Extrude input should be finalized after finding the distance between
#     # starts of tip at 17mm and base after moving down to reference height=22mm 
#     # """
#     # extrude = input("How far to go down for alignment in mm:")
#     # axis.move_relative(extrude, Units.LENGTH_MILLIMETRES)

#     # print("\nEnsure plates are parallel. \n\n")
#     # retract = input("Once plates are parallel, input '17' to move tip to original position:")
#     # axis.move_absolute(retract, Units.LENGTH_MILLIMETRES)
  
#     # print("\nPlace sensor on and start respective test.\n\n")
#     # axis.park()