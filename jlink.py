import sys
import signal
import time
import xlsxwriter
from pathlib import Path

def save_data(values, savepath, run):
    """
    Saves the values array into a excel file before exiting this subprocess
    values :: array of dictionaries
    savepath :: string
    run :: int
    """
    path = Path(savepath).parent / "CAP"
    path.mkdir(parents=True, exist_ok=True)
    filename = f"run {run}.xlsx"
    path = path / filename
    workbook = xlsxwriter.Workbook(path)
    worksheet = workbook.add_worksheet(str(run))

    worksheet.write('A1', 'Index')
    worksheet.write('B1', 'CAP1')
    worksheet.write('C1', 'CAP2')
    worksheet.write('D1', 'CAP3')
    worksheet.write('E1', 'CAP4')
    worksheet.write('F1', 'CAP5')
    worksheet.write('G1', 'CAP6')
    worksheet.write('H1', 'CAP7')
    worksheet.write('I1', 'CAP8')
    worksheet.write('J1', 'TIME')
    worksheet.write('K1', 'ACCX')
    worksheet.write('L1', 'ACCY')
    worksheet.write('M1', 'ACCZ')
    for i, entry in enumerate(values):
        worksheet.write(i + 1, 0, i)  # Index
        worksheet.write(i + 1, 1, entry.get('CAP1', ''))  # CAP1
        worksheet.write(i + 1, 2, entry.get('CAP2', ''))  # CAP2
        worksheet.write(i + 1, 3, entry.get('CAP3', ''))  # CAP3
        worksheet.write(i + 1, 4, entry.get('CAP4', ''))  # CAP4
        worksheet.write(i + 1, 5, entry.get('CAP5', ''))  # CAP5
        worksheet.write(i + 1, 6, entry.get('CAP6', ''))  # CAP6
        worksheet.write(i + 1, 7, entry.get('CAP7', ''))  # CAP7
        worksheet.write(i + 1, 8, entry.get('CAP8', ''))  # CAP8
        worksheet.write(i + 1, 9, entry.get('TIME', ''))   # TIME
        worksheet.write(i + 1, 10, entry.get('ACCX', '')) # ACCX
        worksheet.write(i + 1, 11, entry.get('ACCY', '')) # ACCY
        worksheet.write(i + 1, 12, entry.get('ACCZ', '')) # ACCZ
    workbook.close()

def main(savepath, run):
    print(f"Subprocess started. Saving data to: {savepath}")
    values = [] # this is where the data will be stored until the script is killed and it needs to be saved
    def cleanup_and_exit(signum, frame):
        print("Running pre-exit tasks")
        save_data(values, savepath, run)
        print("Cleanup complete. Exiting")
        sys.exit(0)

    # Register the handler 
    signal.signal(signal.SIGTERM, cleanup_and_exit)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, cleanup_and_exit)
    try:
        idx = 0
        while True:
            print(idx)
            entry = {
                'CAP1': idx,
                'CAP2': idx + 1,
                'CAP3': idx + 2,
                'CAP4': idx + 3,
                'CAP5': idx + 4,
                'CAP6': idx + 5,
                'CAP7': idx + 6,
                'CAP8': idx + 7,
                'TIME': idx * 0.1,
                'ACCX': idx * 0.01,
                'ACCY': idx * 0.02,
                'ACCZ': idx * 0.03,
            }
            values.append(entry)
            idx += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        cleanup_and_exit(None, None)

if __name__ == "__main__":
    # Check if the argument was actually passed to avoid IndexErrors
    if len(sys.argv) > 2:
        path = sys.argv[1]
        run = int(sys.argv[2])
    else:
        path = "default_path.txt"
        run = 1

    main(path, run)