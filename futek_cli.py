import clr
import System
clr.AddReference("FUTEK.Devices")
import FUTEK.Devices
from FUTEK.Devices import DeviceRepository

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

        # There may be no use for this variable to exist
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
        System.Environment.Exit(0)

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
