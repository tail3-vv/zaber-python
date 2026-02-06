from eb_analysis import Analysis

sensor_id = 12345
path = rf'C:/Users/emili/OneDrive/Documents/Projects/VenaVitals/zaber-python/12345/02 02 26_325mm2_EB'
sensor_type = 3

# Create analysis instance
analysis = Analysis(path, sensor_id, sensor_type)

# Get results
result = analysis.save_data()

print(result)