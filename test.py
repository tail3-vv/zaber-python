import xlsxwriter

run_idx = 0
# Go to folder  TODO: create FUT folder if it does not exist
file_name = "./FUT/Run " + str(run_idx + 1) + ".xlsx"
arr = [100, 200, 232, 67]
workbook = xlsxwriter.Workbook(file_name)
worksheet = workbook.add_worksheet("Run 1")
worksheet.write('A1', 'Index')
worksheet.write('B1', 'Load Cell')
worksheet.write('C1', 'Time')
for index in range(len(arr)):
    if index != len(arr)-1:
        input("skip")
    worksheet.write(index+1, 0, index + 1)
    worksheet.write(index+1, 1, arr[index])

workbook.close()
