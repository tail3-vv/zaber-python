import datetime

# Create a datetime object (e.g., the current date and time)
now = datetime.datetime.now()

# Extract components
year = str(now.year)[2:]
month = str(now.month)
day = str(now.day)

if len(month) < 2:
    month = f"0{month}"
if len(day) < 2:
    day = f"0{day}"
# Print the extracted components
print(f"Year: {year}")
print(f"Month: {month}")
print(f"Day: {day}")
