
# Choosing the asset
pair = 0

# Time Frame
horizon = 'H1'
lookback = 14
lower_barrier = 0.20
upper_barrier = 0.80

# Importing the asset as an array
my_data = mass_import(pair, horizon)

# Calling the indicator
my_data = demarker(my_data, lookback, 1, 2, 4)

# Creating the signal function
def signal(data, demarker_column, buy, sell):
 
    data = add_column(data, 10)
    
    for i in range(len(data)):    
        
        try:
        
            # Bullish signal
            if data[i, demarker_column] < lower_barrier and data[i - 1, demarker_column] > lower_barrier:
                
                data[i + 1, buy] = 1
                     
            # Bearish signal
            elif data[i, demarker_column] > upper_barrier and data[i - 1, demarker_column] < upper_barrier:
                
                data[i + 1, sell] = -1
                
        except IndexError:
                 
            pass
         
    return data

# Calling the signal function
my_data = signal(my_data, 4, 5, 6)

# Charting the latest signals
signal_chart_indicator_plot(my_data, 0, 4, 5, 6, barriers = True, window = 250)

# Performance
my_data = performance(my_data, 0, 5, 6, 7, 8, 9)



