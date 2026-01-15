import clr
import System
clr.AddReference("FUTEK.Devices")
import FUTEK.Devices
from FUTEK.Devices import DeviceRepository

class FUTEKDeviceCLI:
    def __init__(self):
        try:
            self.oFUTEKDeviceRepoDLL = FUTEK.Devices.DeviceRepository()
            print("FUTEK Devices DLL initialized.")
        except Exception as e:
            print(f"Error initializing FUTEK Devices DLL: {e}")
            return

        self.SerialNumber = ""
        self.ModelNumber = ""
        self.UnitCode = 0
        self.NormalData = 0
        self.OpenedConnection = False

        # Initialize and check for connected FUTEK devices (particularly USB225)
        devices = self.oFUTEKDeviceRepoDLL.DetectDevices()
        self.USB225 = devices[0] if devices else None

        if self.oFUTEKDeviceRepoDLL.DeviceCount > 0:
            print("Device connected.")
        else:
            print("No device connected.")
            return

    def start(self):
        if self.OpenedConnection:
            pass

        self.ModelNumber = FUTEK.Devices.Device.GetModelNumber(self.USB225)
        print(f"Model Number: {self.ModelNumber}")

        self.SerialNumber = FUTEK.Devices.Device.GetInstrumentSerialNumber(self.USB225)
        print(f"Serial Number: {self.SerialNumber}")

        self.UnitCode = FUTEK.Devices.DeviceUSB225.GetChannelXUnitOfMeasure(self.USB225, 0)
        print(f"Unit of Measure: {self.UnitCode}")

        self.OpenedConnection = True

        self.NormalData = FUTEK.Devices.DeviceUSB225.GetChannelXReading(self.USB225, 0)
        print(f"Sensor Reading: {self.NormalData:.3f}")

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
            cli.start()
        elif command == 'stop':
            cli.stop()
        elif command == 'exit':
            cli.exit()
        else:
            print("Unknown command. Please enter 'start', 'stop', or 'exit'.")
