# AI Smart Grid — Energy Monitoring & Demand Response System

A complete **Real-Time AI-Based Smart Grid** system that predicts future energy consumption using an LSTM neural network and **automatically manages load through demand response** — shedding non-essential loads when predicted demand exceeds the threshold.

## 4-Layer Smart Grid Architecture

The project is built on a four-layer intelligent energy management system:

### Layer-1: Data Acquisition Layer (Sensing & Input)

Collects real-time and historical data required for forecasting.

- **Hardware**: ESP32 NodeMCU
- **Sensors**: Current (ACS712), Voltage (ZMPT101B), Temperature & Humidity (DHT22)
- **Data**: The system factors in both electrical load and weather data, as weather strongly influences demand forecasting.

### Layer-2: Communication & Data Management Layer

Transfers and stores the collected data through an IoT network.

- **Protocol**: HTTP/JSON over Wi-Fi
- **Backend**: Flask API (`app.py`) for data ingestion
- **Storage**: SQLite Database (`database.py`) holding historical datasets for tracking and future AI retraining.

### Layer-3: AI Processing & Load Forecasting Layer

The core intelligence engine processing time-series data.

- **AI Model**: LSTM (Long Short-Term Memory) neural network (TensorFlow/Keras)
- **Function**: Takes the last hour of multi-variate data (voltage, temp, humidity) to accurately predict short-term future load (current). Outperforms traditional algorithms by learning non-linear consumption patterns.

### Layer-4: Decision & Demand Response Control Layer

Converts AI predictions into physical grid actions.

- **Logic**: If Predicted Load > Distributed Supply Threshold (e.g., 3.0A) → Trigger Demand Response
- **Action**: Turns OFF non-essential loads to shift demand, preventing peak stress and grid instability.
- **Feedback**: Sends automated alerts to the interactive web dashboard.

---

## File Structure

### AI Model & Data

| File | Description |
|------|-------------|
| `generate_data.py` | Generates 10,000 rows of synthetic sensor data |
| `train_lstm.py` | Trains the LSTM model (TensorFlow/Keras) |
| `lstm_model.keras` | Saved trained model |
| `scaler.pkl` | MinMaxScaler for feature normalization |

### Backend

| File | Description |
|------|-------------|
| `app.py` | Flask server with APIs, AI prediction, demand response logic |
| `database.py` | SQLite database with readings + relay events tables |

### Frontend

| File | Description |
|------|-------------|
| `templates/index.html` | Premium dashboard with 4 pages: Dashboard, AI Insights, Demand Response, Historical Data |

### Hardware & Simulation

| File | Description |
|------|-------------|
| `esp32_code/esp32_code.ino` | ESP32 firmware (ACS712, ZMPT101B, DHT22, Relay) |
| `test_esp32_sim.py` | Python simulator with high-load spikes for testing |

## Hardware Setup (ESP32)

| Sensor / Module | ESP32 Pin |
|-----------------|-----------|
| ACS712 (Current)| GPIO34 (Analog) |
| ZMPT101B (Voltage)| GPIO35 (Analog) |
| DHT22 (Temp/Hum)| GPIO4 |
| Relay Module | GPIO26 (Digital Out) |

Set `SIMULATION_MODE` to `false` in `esp32_code.ino` before flashing if using physical sensors.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
pip install flask-cors tensorflow

# Start the server
python app.py

# In another terminal, start the simulator to test Demand Response
python test_esp32_sim.py
```

*Open `http://127.0.0.1:5050` to view the dashboard.*
