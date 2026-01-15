from zaber_motion import Units, exceptions
from zaber_motion.ascii import Connection
from zaber_cli import ZaberCLI
"""
This is where the real test will be run. 
TODO: implement the other debug scripts later
"""

init_pos = 5
init_coef = 1
speed = 0.5 # speed of travel in mm/s (millimeter/second)
upper_limit = 20
num_cycle = input("How many cycles")

# Zaber setup
connection = Connection.openSerialPort()