from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import numpy as np
import tensorflow as tf
import pickle
import os
import ssl
import json
import socket
import threading
from collections import deque
from datetime import datetime
from typing import Any, Optional
import database

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("[MQTT] paho-mqtt not installed. MQTT disabled.")

app = Flask(__name__)
CORS(app)

# Load the trained model and scaler globally
model: Optional[Any] = None
scaler: Optional[Any] = None

try:
    model = tf.keras.models.load_model('lstm_model.keras')
    with open('scaler.pkl', 'rb') as f:
        scaler = pickle.load(f)
    print("Model and Scaler loaded successfully.")
except Exception as e:
    print(f"Warning: Model/Scaler not loaded. {e}")

# Start background cleanup thread
database.start_cleanup_thread()

# Rolling buffer — last 12 readings for LSTM input
seq_length = 12
recent_history: deque = deque(maxlen=seq_length)

# ── Demand Response config ────────────────────────────────────────────────────
LOAD_THRESHOLD = 3.0
alert_log: list[dict[str, Any]] = []
MAX_ALERTS = 50

# Latest snapshot — polled by dashboard every 2s
latest_data: dict[str, Any] = {
    'current': 0.0,
    'voltage': 0.0,
    'temperature': 0.0,
    'humidity': 0.0,
    'predicted_current': 0.0,
    'power': 0.0,
    'status': "Waiting for Data...",
    'load_threshold': LOAD_THRESHOLD,
}


def add_alert(message: str, action: str = '', severity: str = 'info') -> None:
    alert = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': message,
        'action': action,
        'severity': severity,
    }
    alert_log.insert(0, alert)
    if len(alert_log) > MAX_ALERTS:
        alert_log.pop()
    print(f"[ALERT-{severity.upper()}] {message}")


def predict_future() -> float:
    """Run LSTM prediction if sequence buffer is full."""
    if model is None or scaler is None:
        return 0.0
    if len(recent_history) == seq_length:
        sequence_data = []
        for rd in recent_history:
            arr = np.array([[rd['voltage'], rd['humidity'], rd['temperature'], 0.0]])
            scaled_arr = scaler.transform(arr)[0][:3]
            sequence_data.append(scaled_arr)

        X_input = np.array([sequence_data])
        predicted_scaled = model.predict(X_input, verbose=0)

        dummy = np.zeros((1, 4))
        dummy[0, 3] = predicted_scaled[0][0]
        predicted_actual = scaler.inverse_transform(dummy)[0, 3]
        return float(max(0.0, predicted_actual))
    return 0.0


# ── Flask Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def home() -> str:
    return render_template('index.html')


@app.route('/api/data', methods=['GET'])
def get_data():
    """Live data snapshot for dashboard polling."""
    return jsonify(latest_data)


@app.route('/api/sensor', methods=['POST'])
def receive_sensor_data():
    """ESP32 pushes real sensor readings here every 5s (HTTP fallback)."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        _process_sensor_json(data)

        return jsonify({
            "message": "Data received",
            "prediction": latest_data.get('predicted_current', 0),
            "power": latest_data.get('power', 0),
        }), 200

    except Exception as e:
        print(f"Error handling sensor data: {e}")
        return jsonify({"error": "Server error", "details": str(e)}), 500


@app.route('/api/energy-forecast', methods=['GET'])
def energy_forecast():
    """
    Returns:
    - Actual energy consumed (from DB historical readings)
    - Actual electricity bill (based on ₹8/unit Indian tariff)
    - Future predicted kWh and bill (from LSTM AI prediction)
    """
    # ── Indian Electricity Tariff ──────────────────────────
    RATE_PER_UNIT = 8.0   # ₹ per kWh (adjust for your state)

    # ── Actual Consumed kWh from database ─────────────────
    actual_kwh_today   = 0.0
    actual_kwh_30d     = 0.0
    try:
        conn = database.get_connection()
        # Today's consumption: sum(power * interval) / 1000
        # Each reading is ~5s apart → 5/3600 hours per reading
        interval_hours = 5.0 / 3600.0

        row_today = conn.execute(
            """SELECT SUM(power) as total_w FROM readings
               WHERE timestamp >= datetime('now','localtime','-1 day')"""
        ).fetchone()
        if row_today and row_today['total_w']:
            actual_kwh_today = round(row_today['total_w'] * interval_hours / 1000.0, 4)

        row_30d = conn.execute(
            """SELECT SUM(power) as total_w FROM readings
               WHERE timestamp >= datetime('now','localtime','-30 days')"""
        ).fetchone()
        if row_30d and row_30d['total_w']:
            actual_kwh_30d = round(row_30d['total_w'] * interval_hours / 1000.0, 3)

        conn.close()
    except Exception as e:
        print(f"[Forecast] DB error: {e}")

    # ── Future Predicted kWh from AI ──────────────────────
    pred_a = latest_data.get('predicted_current', 0.0)
    volt   = latest_data.get('voltage', 220.0) or 220.0
    if volt == 0:
        volt = 220.0

    pred_kw  = round((volt * pred_a) / 1000.0, 4)
    next_1h  = round(pred_kw * 1,     4)
    next_24h = round(pred_kw * 24,    3)
    next_30d = round(pred_kw * 24*30, 2)

    # ── Bill Calculations ─────────────────────────────────
    bill_today_actual = round(actual_kwh_today * RATE_PER_UNIT, 2)
    bill_30d_actual   = round(actual_kwh_30d   * RATE_PER_UNIT, 2)
    bill_1h_future    = round(next_1h  * RATE_PER_UNIT, 2)
    bill_24h_future   = round(next_24h * RATE_PER_UNIT, 2)
    bill_30d_future   = round(next_30d * RATE_PER_UNIT, 2)

    return jsonify({
        # Live AI prediction
        'predicted_current_A': pred_a,
        'predicted_power_kW':  pred_kw,
        'rate_per_unit_inr':   RATE_PER_UNIT,
        'ready': pred_a > 0,
        # Actual consumption from real sensor history
        'actual_kwh_today':      actual_kwh_today,
        'actual_kwh_30d':        actual_kwh_30d,
        'actual_bill_today_inr': bill_today_actual,
        'actual_bill_30d_inr':   bill_30d_actual,
        # Future AI predictions
        'next_1h_kWh':   next_1h,
        'next_24h_kWh':  next_24h,
        'next_30d_kWh':  next_30d,
        'next_1h_units':  next_1h,
        'next_24h_units': next_24h,
        'next_30d_units': next_30d,
        'bill_1h_inr':   bill_1h_future,
        'bill_24h_inr':  bill_24h_future,
        'bill_30d_inr':  bill_30d_future,
        'note': '1 Unit = 1 kWh | Rate: ₹8/unit | Based on LSTM AI prediction',
    })


@app.route('/api/ai-info', methods=['GET'])
def get_ai_info():
    total_readings = 0
    try:
        conn = database.get_connection()
        row = conn.execute('SELECT COUNT(*) as cnt FROM readings').fetchone()
        total_readings = row['cnt'] if row else 0
        conn.close()
    except Exception:
        pass

    return jsonify({
        'model_type': 'LSTM (Long Short-Term Memory)',
        'framework': 'TensorFlow / Keras',
        'architecture': [
            {'layer': 'LSTM', 'units': 50, 'return_sequences': True},
            {'layer': 'Dropout', 'rate': 0.2},
            {'layer': 'LSTM', 'units': 50, 'return_sequences': False},
            {'layer': 'Dropout', 'rate': 0.2},
            {'layer': 'Dense', 'units': 1},
        ],
        'input_features': ['Voltage (V)', 'Humidity (%)', 'Temperature (°C)'],
        'output': 'Predicted Current (A)',
        'sequence_length': seq_length,
        'training_data_rows': 10000,
        'training_epochs': 10,
        'optimizer': 'Adam',
        'loss_function': 'Mean Squared Error (MSE)',
        'prediction_horizon': '5 minutes ahead',
        'model_loaded': model is not None,
        'scaler_loaded': scaler is not None,
        'total_readings_stored': total_readings,
        'sequence_buffer_fill': len(recent_history),
        'retention_days': 15,
        'load_threshold': LOAD_THRESHOLD,
        'demand_response_active': True,
    })


@app.route('/api/history', methods=['GET'])
def get_history():
    time_range = request.args.get('range', '1h')
    hours_map = {'1h': 1, '6h': 6, '24h': 24, '7d': 168, '15d': 360}
    hours = hours_map.get(time_range, 1)
    return jsonify(database.get_readings(hours=hours))


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    return jsonify(alert_log)


@app.route('/api/smart-forecast', methods=['GET'])
def smart_forecast():
    """
    Context-aware AI energy prediction.
    Considers real sensor data (temperature, humidity, voltage, current)
    and applies real-world load patterns:
      - High temp (>30°C) → AC likely running → more energy
      - Cold (<15°C)      → Heater/geyser → more energy
      - High humidity (>80%) → Monsoon/fan load
      - Normal             → Baseline LSTM prediction
    Returns 24-hour hourly forecast with kW, kWh, units, ₹ bill.
    """
    RATE_PER_UNIT = 8.0

    temp    = latest_data.get('temperature', 25.0) or 25.0
    hum     = latest_data.get('humidity', 50.0)    or 50.0
    volt    = latest_data.get('voltage', 220.0)    or 220.0
    current = latest_data.get('current', 0.0)      or 0.0
    pred_a  = latest_data.get('predicted_current', 0.0) or current

    # ── Determine condition & load multiplier ──────────────────────────────
    if temp >= 35:
        condition = "Extreme Heat 🌡️"
        condition_detail = f"Temp {temp:.1f}°C — Heavy AC usage expected"
        base_multiplier = 1.8
        load_type = "AC + Cooling loads"
        color = "#ef4444"
    elif temp >= 30:
        condition = "Hot Weather ☀️"
        condition_detail = f"Temp {temp:.1f}°C — AC likely running"
        base_multiplier = 1.5
        load_type = "Air Conditioning"
        color = "#f97316"
    elif temp <= 10:
        condition = "Extreme Cold ❄️"
        condition_detail = f"Temp {temp:.1f}°C — Room heater + geyser active"
        base_multiplier = 1.6
        load_type = "Heater + Geyser loads"
        color = "#3b82f6"
    elif temp <= 18:
        condition = "Cold Weather 🧊"
        condition_detail = f"Temp {temp:.1f}°C — Water heater likely on"
        base_multiplier = 1.3
        load_type = "Water Heater"
        color = "#60a5fa"
    elif hum >= 85:
        condition = "Monsoon / Heavy Rain 🌧️"
        condition_detail = f"Humidity {hum:.1f}% — Fans + dehumidifiers running"
        base_multiplier = 1.2
        load_type = "Fans + Humid loads"
        color = "#06b6d4"
    elif hum >= 70:
        condition = "Humid Weather 💧"
        condition_detail = f"Humidity {hum:.1f}% — Increased fan usage"
        base_multiplier = 1.1
        load_type = "Fans + Coolers"
        color = "#22d3ee"
    else:
        condition = "Comfortable ✅"
        condition_detail = f"Temp {temp:.1f}°C, Humidity {hum:.1f}% — Normal"
        base_multiplier = 1.0
        load_type = "Normal household loads"
        color = "#10b981"

    # ── 24-hour hourly forecast (simulate diurnal pattern) ─────────────────
    import math
    from datetime import datetime, timedelta
    base_kw = (volt * pred_a) / 1000.0 if pred_a > 0 else (volt * current) / 1000.0
    if base_kw <= 0:
        base_kw = (volt * 1.0) / 1000.0  # fallback 1A baseline

    now = datetime.now()
    labels   = []
    kw_vals  = []
    kwh_vals = []
    bill_vals = []
    total_kwh = 0.0

    for h in range(25):
        t_future = now + timedelta(hours=h)
        hour_of_day = t_future.hour

        # Diurnal pattern: peak at midday and evening, low at night
        if 0 <= hour_of_day < 6:
            time_factor = 0.4    # night — mostly idle
        elif 6 <= hour_of_day < 9:
            time_factor = 0.85   # morning — geyser, lights
        elif 9 <= hour_of_day < 12:
            time_factor = 0.9    # mid-morning
        elif 12 <= hour_of_day < 15:
            time_factor = 1.1    # afternoon — AC peak if hot
        elif 15 <= hour_of_day < 18:
            time_factor = 0.95
        elif 18 <= hour_of_day < 22:
            time_factor = 1.15   # evening — all loads on
        else:
            time_factor = 0.5    # late night

        predicted_kw = round(base_kw * base_multiplier * time_factor, 4)
        predicted_kwh = round(predicted_kw * 1, 4)  # 1 hour
        predicted_bill = round(predicted_kwh * RATE_PER_UNIT, 2)
        total_kwh += predicted_kwh

        labels.append(t_future.strftime('%H:%M'))
        kw_vals.append(predicted_kw)
        kwh_vals.append(predicted_kwh)
        bill_vals.append(predicted_bill)

    total_bill = round(total_kwh * RATE_PER_UNIT, 2)
    peak_kw = max(kw_vals)
    avg_kw  = round(sum(kw_vals) / len(kw_vals), 4)

    return jsonify({
        'condition':        condition,
        'condition_detail': condition_detail,
        'load_type':        load_type,
        'color':            color,
        'temperature':      temp,
        'humidity':         hum,
        'voltage':          volt,
        'base_multiplier':  base_multiplier,
        # 24h chart data
        'labels':      labels,
        'kw_values':   kw_vals,
        'kwh_values':  kwh_vals,
        'bill_values': bill_vals,
        # Summary
        'total_24h_kwh':  round(total_kwh, 3),
        'total_24h_bill': total_bill,
        'peak_kw':         peak_kw,
        'avg_kw':          avg_kw,
        'total_24h_units': round(total_kwh, 3),
    })


# ── MQTT Subscriber — receives ESP32 data from HiveMQ Cloud ──────────────────
def _process_sensor_json(data: dict) -> None:
    """Shared logic: process a sensor JSON payload (from MQTT or HTTP POST)."""
    global latest_data
    try:
        v = float(data.get('voltage', 0))
        h = float(data.get('humidity', 0))
        t = float(data.get('temperature', 0))
        c = float(data.get('current', 0))
        power = round(v * c, 2)

        recent_history.append({"voltage": v, "humidity": h, "temperature": t, "current": c})

        pred_current = 0.0
        status_msg = f"Collecting Sequence... ({len(recent_history)}/{seq_length})"

        if len(recent_history) == seq_length:
            pred_current = predict_future()
            if pred_current > LOAD_THRESHOLD:
                status_msg = "⚠️ WARNING: Heavy Load Predicted"
                add_alert(
                    f"Heavy load predicted: {pred_current:.2f}A > {LOAD_THRESHOLD}A",
                    action="Monitor Loads",
                    severity="warning"
                )
            elif pred_current > c * 1.5 and c > 0:
                status_msg = "⚡ Notice: Load Spike Imminent"
            else:
                status_msg = "✅ System Normal"

        predicted_rounded = round(pred_current, 2)

        database.insert_reading(
            voltage=v,
            current_val=c,
            temperature=t,
            humidity=h,
            predicted_current=predicted_rounded,
            power=power,
            relay_state='N/A',
        )

        latest_data = {
            'current': c,
            'voltage': v,
            'temperature': t,
            'humidity': h,
            'predicted_current': predicted_rounded,
            'power': power,
            'status': status_msg,
            'load_threshold': LOAD_THRESHOLD,
        }
        print(f"[DATA] V={v} I={c} T={t} H={h} Pred={predicted_rounded}A")

    except Exception as e:
        print(f"[DATA] Error processing sensor data: {e}")


def _start_mqtt() -> None:
    """Connect to HiveMQ Cloud and subscribe to ESP32 sensor topic."""
    if not MQTT_AVAILABLE:
        print("[MQTT] paho-mqtt not available, skipping.")
        return

    broker = os.environ.get('MQTT_BROKER', 'e5c6d611df63436992755767b6967071.s1.eu.hivemq.cloud')
    port = int(os.environ.get('MQTT_PORT', '8883'))
    username = os.environ.get('MQTT_USERNAME', 'smartwater')
    password = os.environ.get('MQTT_PASSWORD', 'SmartWater2026!')
    topic = os.environ.get('MQTT_TOPIC', 'smartgrid/sensor')

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[MQTT] ✅ Connected to HiveMQ Cloud!")
            client.subscribe(topic)
            print(f"[MQTT] Subscribed to topic: {topic}")
        else:
            print(f"[MQTT] ❌ Connection failed with code {rc}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            print(f"[MQTT] Received on {msg.topic}: {payload}")
            _process_sensor_json(payload)
        except Exception as e:
            print(f"[MQTT] Error parsing message: {e}")

    def on_disconnect(client, userdata, rc, properties=None):
        print(f"[MQTT] Disconnected (rc={rc}). Will auto-reconnect...")

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(username, password)
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.connect(broker, port, keepalive=60)
        client.loop_start()  # Non-blocking background loop
        print(f"[MQTT] Connecting to {broker}:{port}...")
    except Exception as e:
        print(f"[MQTT] Failed to start: {e}")


# Start MQTT subscriber in background thread
threading.Thread(target=_start_mqtt, daemon=True).start()
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print("=" * 50)
    print("  AI Smart Grid — Energy Monitoring System")
    print(f"  Dashboard : http://127.0.0.1:{port}")
    print(f"  MQTT      : Subscribing to smartgrid/sensor")
    print("=" * 50)
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(host='0.0.0.0', port=port, debug=False)
