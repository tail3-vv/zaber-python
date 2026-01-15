import clr
import sys
import msvcrt
clr.AddReference("FUTEK.Devices")
import FUTEK.Devices
from FUTEK.Devices import DeviceRepository

def main():
    repo = DeviceRepository()

    # Use DetectDevices to discover usb225
    devices = repo.DetectDevices()
    usb225 = devices[0]  # Assuming the first device is the USB225
    sampling_rates = usb225.GetChannelXSamplingRatePossibleValues(0)

    # Set sampling rate to 5 samples per second. This is only used for this example.
    usb225.SetChannelXSamplingRate(0, next(x for x in sampling_rates if x == "20"))

    # Must run pre-streaming operations before using GetStreamingDataConverted or GetStreamingData.
    print("Running pre-streaming operations...")
    usb225.PreStreamingOperations()

    print("Press 'q' to stop")
    try:
        while True:
            if msvcrt.kbhit():
                if msvcrt.getch().decode().lower() == 'q':
                    break

            # GetStreamingConverted will convert stream data collected and return values.
            points = usb225.GetStreamingDataConverted()
            for point in points:
                print(point.ConvertedValue)

    except KeyboardInterrupt:
        pass

    # Must run post-streaming operations once the stream has been completed.
    print("Running post-streaming operations...")
    usb225.PostStreamingOperations()

if __name__ == "__main__":
    main()
