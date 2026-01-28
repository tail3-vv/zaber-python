import serial.tools.list_ports

# Get an iterable of ListPortInfo objects
ports = serial.tools.list_ports.comports()

# Iterate over the list of ports and print their information
for port in ports:
    print(f"Device: {port.device}")
    print(f"Name: {port.name}")
    print(f"Description: {port.description}")
    print(f"Hardware ID: {port.hwid}\n")

print(f"{len(ports)} ports found")