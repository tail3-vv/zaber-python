import serial.tools.list_ports

def list_serial_ports():
    # Get a list of available serial ports
    ports = [port.device for port in serial.tools.list_ports.comports()]
    
    if not ports:
        print("No COM ports found.")
    else:
        print(ports)

if __name__ == "__main__":
    list_serial_ports()