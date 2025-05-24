import openpyxl

wb = openpyxl.Workbook()
ws = wb.active
ws['A1'] = 'Test'
wb.save('test_output.xlsx')

print("Excel generat!")
