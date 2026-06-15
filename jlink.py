"""
Use the pylink library to automatically read and parse
incoming data from the jlink connection

Current structure:
0) Main Zaber script starts THIS subprocess
1) Main function for this script takes in args from main Zaber script (save path)
2) Opens Jlink connection
3) Verifies that Jlink is recieving CAP data TODO: (Not done)
4) Begins data reading
5) Once test is finished in main script:
    5a) End data reading
    5b) Save data to CAP folder
    5c) Exit subprocess

Requires:
pylink
pylink-square
"""
import pylink
import time
import re
import signal
import sys
from pathlib import Path
import xlsxwriter
from pylink.enums import JLinkInterfaces
import math

# Sensor constants for motion data conversion
# These values depend on your specific IMU configuration
# Typical values for nRF52833 with standard IMU:
# - Accelerometer: ±16g full scale
# - Gyroscope: ±2000°/s full scale
# - Magnetometer: ±4800 µT full scale (adjust based on your sensor)
ACCEL_FULL_SCALE = 16.0  # g (±16g)
GYRO_FULL_SCALE = 2000.0  # °/s (±2000°/s)
MAG_FULL_SCALE = 4800.0  # µT (±4800 µT) - adjust if needed

# Capacitance conversion constants
CAPACITANCE_CONSTANTS = [13, 13, 13, 13,
                         30, 30, 30, 30,
                         22, 22, 22, 22,
                         39, 39, 39, 39]


def convert_capacitance(raw_value, channel):
    """
    Convert raw capacitance value to picoFarads.
    Based on BluetoothController.swift capacitorValues() function.
    
    Args:
        raw_value: Raw 32-bit integer from device
        channel: Channel index (0-15) for selecting appropriate constant
    
    Returns:
        Capacitance value in picoFarads (pF)
    """
    # Scale the raw value by the internal hardware clock running at 40Mhz
    # Scale by 2 to account for the rising/falling edges of the clock signal
    # (This is a hardware edge prescaler)
    cap_reading = 2.0 * 40000000.0 * raw_value
    
    # Normalize by 2^28 (this is the chip's 28-bit limit)
    cap_reading = cap_reading / (2.0 ** 28.0)
    
    # Using the resonant frequency formula with inductance/capacitance
    # we solve for capacitance (c) instead of frequency (f)
    # 18e-6: Fixed hardware inductance 
    # This solved for the denominator of the frequency formula
    L = 18e-6
    cap_reading = L * ((2.0 * math.pi * cap_reading) ** 2.0)
    
    # Invert and convert to picoFarads (10^12)
    cap_reading = (1.0 / cap_reading) * (10.0 ** 12.0)
    
    # Adjust capacitance value for parasitic capacitance
    if channel < len(CAPACITANCE_CONSTANTS):
        cap_reading = cap_reading - CAPACITANCE_CONSTANTS[channel]
    
    return cap_reading


def convert_motion_value(raw_value, sensor_index):
    """
    Convert raw motion value to physical units.
    Based on BluetoothController.swift motionValues() function.
    
    Sensor index mapping:
        0-2: Accelerometer (X, Y, Z) -> g (gravitational acceleration)
        3-5: Gyroscope (X, Y, Z) -> °/s (degrees per second)
        6-8: Magnetometer (X, Y, Z) -> µT (microtesla)
    
    Args:
        raw_value: Raw 16-bit signed integer from device
        sensor_index: Index determining sensor type and full scale
    
    Returns:
        Physical unit value (g, °/s, or µT depending on sensor type)
    """
    motion_constants = [ACCEL_FULL_SCALE, ACCEL_FULL_SCALE, ACCEL_FULL_SCALE,
                        GYRO_FULL_SCALE, GYRO_FULL_SCALE, GYRO_FULL_SCALE,
                        MAG_FULL_SCALE, MAG_FULL_SCALE, MAG_FULL_SCALE]
    
    if sensor_index < len(motion_constants):
        # Convert from 16-bit representation to physical units
        return raw_value * motion_constants[sensor_index] / 32768.0
    
    return float(raw_value)


def try_create_entry(cap_data, acc_data, values):
    """Create entry if both CAP and ACC data are available"""
    if cap_data and acc_data:
        entry = cap_data | acc_data
        values.append(entry)
        #print(entry)
        return True
    return False


def save_data(values, savepath, run):
    """
    Saves the values array into a excel file before exiting this subprocess
    values :: array of dictionaries
    savepath :: string
    run :: int
    """
    path = Path(savepath)
    filename = f"run {run}.xlsx"
    path = path / filename 
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet(str(run))

    worksheet.write('A1', 'TIME(s)')
    worksheet.write('B1', 'CAP1(pF)')
    worksheet.write('C1', 'CAP2(pF)')
    worksheet.write('D1', 'CAP3(pF)')
    worksheet.write('E1', 'CAP4(pF)')
    worksheet.write('F1', 'CAP5(pF)')
    worksheet.write('G1', 'CAP6(pF)')
    worksheet.write('H1', 'CAP7(pF)')
    worksheet.write('I1', 'CAP8(pF)')
    worksheet.write('K1', 'ACCX')
    worksheet.write('L1', 'ACCY')
    worksheet.write('M1', 'ACCZ')
    for i, entry in enumerate(values):
        worksheet.write(i + 1, 0, entry.get('TIME', ''))  # TIME
        worksheet.write(i + 1, 1, entry.get('CAP1', ''))  # CAP1
        worksheet.write(i + 1, 2, entry.get('CAP2', ''))  # CAP2
        worksheet.write(i + 1, 3, entry.get('CAP3', ''))  # CAP3
        worksheet.write(i + 1, 4, entry.get('CAP4', ''))  # CAP4
        worksheet.write(i + 1, 5, entry.get('CAP5', ''))  # CAP5
        worksheet.write(i + 1, 6, entry.get('CAP6', ''))  # CAP6
        worksheet.write(i + 1, 7, entry.get('CAP7', ''))  # CAP7
        worksheet.write(i + 1, 8, entry.get('CAP8', ''))  # CAP8
        worksheet.write(i + 1, 10, entry.get('ACCX', '')) # ACCX
        worksheet.write(i + 1, 11, entry.get('ACCY', '')) # ACCY
        worksheet.write(i + 1, 12, entry.get('ACCZ', '')) # ACCZ
    workbook.close()

TIME_PATTERN = re.compile(r"TIME:\s*([-+]?\d+(?:\.\d+)?)")
A_PATTERN = re.compile(r"A:\s*([-+]?\d+),([-+]?\d+),([-+]?\d+)")
C_PATTERN = re.compile(r"C:\s*([-+]?\d+),([-+]?\d+),([-+]?\d+),([-+]?\d+)")


def is_complete_entry(entry):
    if not entry:
        return False
    required_keys = ["TIME", "ACCX", "ACCY", "ACCZ"] + [f"CAP{i}" for i in range(1, 9)]
    return all(key in entry for key in required_keys)


def append_entry(entry, values):
    if is_complete_entry(entry):
        values.append(entry.copy())
        return True
    return False


def verify_rtt_connection(jlink, timeout=10):
    """
    Verify that RTT is receiving data from the device.
    Returns True if data is received, False otherwise.
    """
    print(f"Verifying RTT connection (timeout: {timeout}s)...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        data = jlink.rtt_read(0, 1024)
        if data:
            text = bytes(data).decode('utf-8', errors='ignore')
            if text.strip():
                print(f"RTT connection verified! Initial data: {text[:100]}...")
                return True
        time.sleep(0.5)
    
    print("Warning: No data received from RTT within timeout period")
    return False


def main(savepath, run):
    """
    savepath:: string
    run:: int
    """
    print(f"Subprocess started. Saving data to: {savepath}")
    jlink = pylink.JLink()
    jlink.open()
    jlink.set_tif(JLinkInterfaces.SWD)
    jlink.connect('nRF52833_xxAA')

    # Configure Real Time Transfer (RTT)
    jlink.rtt_start()
    
    # Verify RTT connection before starting data collection
    if not verify_rtt_connection(jlink, timeout=10):
        print("Warning: Proceeding despite RTT verification failure")
    
    values = []
    buffer = ""  # Accumulate data across reads
    current_entry = {}

    def cleanup_and_exit(signum, frame):
        """
        Closes RTT link and saves values array
        """
        print("Running pre-exit tasks")
        append_entry(current_entry, values)
        try:
            jlink.rtt_stop()
        except Exception as exc:
            print(f"Failed to stop RTT cleanly: {exc}")
        try:
            jlink.close()
        except Exception as exc:
            print(f"Failed to close JLink cleanly: {exc}")
        save_data(values, savepath, run)
        print("Cleanup complete. Exiting")
        sys.exit(0)

    # Register the handlers
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, cleanup_and_exit)

    try:
        while True:
            # Read from RTT terminal 0
            data = jlink.rtt_read(0, 1024)

            # Convert byte list to string
            text = bytes(data).decode('utf-8')
            if text:
                buffer += text
                lines = buffer.splitlines(keepends=True)
                if lines and not lines[-1].endswith("\n"):
                    process_lines = lines[:-1]
                    buffer = lines[-1]
                else:
                    process_lines = lines
                    buffer = ""

                for raw_line in process_lines:
                    line = raw_line.strip()
                    if not line:
                        continue

                    time_match = TIME_PATTERN.search(line)
                    if time_match:
                        append_entry(current_entry, values)
                        current_entry = {
                            "TIME": float(time_match.group(1)),
                            "C_count": 0,
                        }
                        continue

                    a_match = A_PATTERN.search(line)
                    if a_match and current_entry is not None:
                        # Convert raw acceleration values to physical units (g)
                        current_entry["ACCX"] = convert_motion_value(int(a_match.group(1)), 0)
                        current_entry["ACCY"] = convert_motion_value(int(a_match.group(2)), 1)
                        current_entry["ACCZ"] = convert_motion_value(int(a_match.group(3)), 2)
                        continue

                    c_match = C_PATTERN.search(line)
                    if c_match and current_entry is not None:
                        count = current_entry.get("C_count", 0)
                        for idx, value in enumerate(c_match.groups(), start=1):
                            channel = count * 4 + idx
                            # Convert raw capacitance value to picoFarads (pF)
                            # channel indices are 1-16, but CAPACITANCE_CONSTANTS are 0-indexed
                            cap_index = channel - 1
                            current_entry[f"CAP{channel}"] = convert_capacitance(int(value), cap_index)
                        current_entry["C_count"] = count + 1
                        continue

            #time.sleep(0.1)
    except KeyboardInterrupt:
        cleanup_and_exit(None, None)


if __name__ == "__main__":
    # Check if the argument was actually passed to avoid IndexErrors
    if len(sys.argv) > 2:
        path = sys.argv[1]
        run = int(sys.argv[2])
    else:
        path = "./"
        run = 0
        
    main(path, run)
