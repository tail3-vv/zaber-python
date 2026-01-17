from zaber_motion.ascii import Connection
from zaber_motion import exceptions

class ZaberCLI():
    def __init__(self):
        self.connection = None
        self.axis = None
    
    def connect(self, comport="COM3"):
        """
        Attempt to connect to the Zaber serial port
        If it does not connect, raise error
        
        :param comport: Specify the comport that your PC uses to connect to Zaber
                        Note: Will raise error if using incorrect comport
        """
        try:
            self.connection = Connection.open_serial_port(comport)
            device_list = self.connection.detect_devices()
            device = device_list[0]
            self.axis = device.get_axis(1)
            return self.connection
        except exceptions.ConnectionFailedException:
            print("Device not found")
            pass
        except AttributeError:
            print("Device not found")
            pass
        
    def disconnect(self):
        self.connection.close()

if __name__ == '__main__':
    cli = ZaberCLI()
    while True:
        command = input("Enter command (start/stop/exit): ").strip().lower()
        if command == 'start':
            cli.connect()
        elif command == 'stop':
            cli.disconnect()
        else:
            print("Unknown command. Please enter 'start', 'stop', or 'exit'.")
