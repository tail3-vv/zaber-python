from zaber_motion import Units
from zaber_motion.ascii import Connection

"""
USB connection name (ie COM3, COM4, COM5) is varies by laptop
Check device manager -> Ports (COM & LPT) to see which connection works
"""
with Connection.open_serial_port("COM5") as connection:
    # allows device to communicate back without preceding requests
    # connection.enable_alerts()

    # look for usb devices that are connected
    device_list = connection.detect_devices()
    print("Found {} devices".format(len(device_list)))

    device = device_list[0]
    axis = device.get_axis(1)

    # unpark zaber device
    if axis.is_parked():
      axis.unpark()

    # Set position to 17mm
    axis.move_absolute(17, Units.LENGTH_MILLIMETRES)
    currentPosition = axis.get_position()
    currentPosition = (currentPosition * 0.04765) / 1000
    print("Current position is: {currentPosition} mm \n\n")

    """
    Prompt User
    Move the base plate down to the designated reference height
    Extrude input should be finalized after finding the distance between
    starts of tip at 17mm and base after moving down to reference height=22mm 
    """
    extrude = input("How far to go down for alignment in mm:")
    axis.move_relative(extrude, Units.LENGTH_MILLIMETRES)

    print("\nEnsure plates are parallel. \n\n")
    retract = input("Once plates are parallel, input '17' to move tip to original position:")
    axis.move_absolute(retract, Units.LENGTH_MILLIMETRES)
  
    print("\nPlace sensor on and start respective test.\n\n")
