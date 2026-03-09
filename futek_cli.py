import clr
import System
clr.AddReference("FUTEK.Devices")
import FUTEK.Devices
from FUTEK.Devices import DeviceRepository

"""
Controls Futek Loadcell
Connects/Disconnects loadcell
Displays loadcell information
"""
class FUTEKDeviceCLI:
    def __init__(self):
        self.oFUTEKDeviceRepoDLL = self.connect()
        # Initialize and check for connected FUTEK devices (particularly USB225)
        devices = self.oFUTEKDeviceRepoDLL.DetectDevices()
        self.USB225 = devices[0] if devices else None

        self.ModelNumber = FUTEK.Devices.Device.GetModelNumber(self.USB225)
        print(f"Model Number: {self.ModelNumber}")

        self.SerialNumber = FUTEK.Devices.Device.GetInstrumentSerialNumber(self.USB225)
        print(f"Serial Number: {self.SerialNumber}")

        self.UnitCode = FUTEK.Devices.DeviceUSB225.GetChannelXUnitOfMeasure(self.USB225, 0)
        print(f"Unit of Measure: {self.UnitCode}")

        self.OpenedConnection = True

        self.SamplingRate = FUTEK.Devices.DeviceUSB225.GetChannelXSamplingRate(self.USB225, 0)
        # available sampling rates: ['2.5', '5', '10', '16.6', '20', '50', '60', '100', '400', '1200', '2400', '4800']
        print(f"Sampling Rate: {self.SamplingRate} Hz")
        self.USB225.SetChannelXSamplingRate(0, "100") # Set sampling rate to 60 hz to adjust to python's loop speed

        self.NormalData = FUTEK.Devices.DeviceUSB225.GetChannelXReading(self.USB225, 0)
        print(f"Sensor Reading: {self.NormalData:.3f}")

    def getNormalData(self):
        return FUTEK.Devices.DeviceUSB225.GetChannelXReading(self.USB225, 0)
    
    def connect(self):
        try:
            print("FUTEK Devices DLL initialized.")
            return FUTEK.Devices.DeviceRepository()
        except Exception as e:
            print(f"Error initializing FUTEK Devices DLL: {e}")
            return

    def stop(self):
        if not self.OpenedConnection:
            print("No open connection to close.")
            return

        self.oFUTEKDeviceRepoDLL.DisconnectAllDevices()
        if self.oFUTEKDeviceRepoDLL.DeviceCount > 0:
            print("A device is still connected.")
        else:
            print("Session closed.")

        self.SerialNumber = ""
        self.ModelNumber = ""
        self.UnitCode = 0

        self.OpenedConnection = False

    def exit(self):
        if self.OpenedConnection:
            self.stop()
        print("Exiting the CLI...")
        #System.Environment.Exit(0)

if __name__ == '__main__':
    cli = FUTEKDeviceCLI()
    while True:
        command = input("Enter command (start/stop/exit): ").strip().lower()
        if command == 'start':
            print(cli.getNormalData())
        elif command == 'stop':
            cli.stop()
        elif command == 'exit':
            cli.exit()
        else:
            print("Unknown command. Please enter 'start', 'stop', or 'exit'.")
