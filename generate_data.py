import csv
import math
import random
from datetime import datetime, timedelta


def generate_lstm_data(num_rows: int = 10000, filename: str = 'sensor_data_large.csv') -> None:
    """Generate synthetic sensor data for LSTM model training."""
    start_date = datetime(2026, 1, 1, 0, 0, 0)

    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp', 'current', 'voltage', 'humidity', 'temperature'])

        for i in range(num_rows):
            current_time = start_date + timedelta(minutes=5 * i)

            # Voltage: around 220V with noise
            voltage = 220.0 + random.gauss(0, 1.5)
            voltage = float(round(voltage, 2))

            # Temperature: diurnal cycle + noise
            # roughly one cycle per day if 1 interval = 5 mins, 288 intervals = 1 day
            temp_cycle = math.sin((i / 288) * 2 * math.pi)
            temperature = 25.0 + 5.0 * temp_cycle + random.gauss(0, 0.5)
            temperature = float(round(temperature, 2))

            # Humidity: inverse to temperature + noise
            humidity = 60.0 - 20.0 * temp_cycle + random.gauss(0, 2.0)
            humidity = max(0.0, min(100.0, humidity))  # clamp between 0 and 100
            humidity = float(round(humidity, 2))

            # Current: somewhat proportional to temperature extremes (AC/heating) + noise
            current_base = 1.0
            if temperature > 28:
                current_base += 0.5 * (temperature - 28)
            current_val = current_base + random.gauss(0, 0.2)
            current_val = max(0.0, current_val)  # non-negative
            current_val = float(round(current_val, 2))

            writer.writerow([
                current_time.strftime("%Y-%m-%d %H:%M:%S"),
                current_val,
                voltage,
                humidity,
                temperature
            ])

    print(f"Generated {num_rows} rows of data and saved to {filename}")


if __name__ == "__main__":
    generate_lstm_data()
