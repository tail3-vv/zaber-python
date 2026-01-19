from zaber_motion.ascii import Connection
from zaber_motion import exceptions

class ZaberCLI():
    def __init__(self):
        self.connection = Connection.open_serial_port("COM4")

        # Get axis
        device_list = self.connection.detect_devices()
        device = device_list[0]
        self.axis = device.get_axis(1)
        if self.axis.is_parked():
                self.axis.unpark()
        print("Device fully connected")
        
    def disconnect(self):
        print("Device disconnected")
        self.axis = self.axis.park()
        self.connection = self.connection.close()

    def getAxis(self):
        return self.axis
    
if __name__ == '__main__':
    cli = ZaberCLI()
    print(cli.connection)
    print(cli.axis)
    cli.disconnect()
    print(cli.connection)
    print(cli.axis)
    # while True:
    #     command = input("Enter command (start/stop/exit): ").strip().lower()
    #     if command == 'start':
    #         cli.connect()
    #     elif command == 'stop':
    #         cli.disconnect()
    #     else:
    #         print("Unknown command. Please enter 'start', 'stop', or 'exit'.")
