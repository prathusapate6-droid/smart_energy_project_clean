"""
AI Smart Grid — ESP32 Simulator
Supports both HTTP (local) and MQTT (HiveMQ Cloud) modes.

Usage:
  python test_esp32_sim.py          # HTTP mode (local Flask server)
  python test_esp32_sim.py --mqtt   # MQTT mode (HiveMQ Cloud → Render)
"""
import time
import random
import json
import sys
import os

# ── Mode Selection ──
USE_MQTT = '--mqtt' in sys.argv

# ── MQTT Config (HiveMQ Cloud) ──
MQTT_BROKER = os.environ.get('MQTT_BROKER', 'e5c6d611df63436992755767b6967071.s1.eu.hivemq.cloud')
MQTT_PORT = int(os.environ.get('MQTT_PORT', '8883'))
MQTT_USERNAME = os.environ.get('MQTT_USERNAME', 'smartwater')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD', 'SmartWater2026!')
MQTT_TOPIC = os.environ.get('MQTT_TOPIC', 'smartgrid/sensor')

# ── HTTP Config (local Flask server) ──
SERVER_URL = "http://127.0.0.1:5050/api/sensor"

print("═" * 55)
print("  AI Smart Grid — ESP32 Simulator")
print("  Includes high-load spikes for demand response testing")
if USE_MQTT:
    print(f"  Mode: MQTT → {MQTT_BROKER}:{MQTT_PORT}")
    print(f"  Topic: {MQTT_TOPIC}")
else:
    print(f"  Mode: HTTP → {SERVER_URL}")
print("═" * 55)

# ── Setup MQTT or HTTP client ──
mqtt_client = None
if USE_MQTT:
    try:
        import paho.mqtt.client as mqtt
        import ssl

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                print("[MQTT] ✅ Connected to HiveMQ Cloud!")
            else:
                print(f"[MQTT] ❌ Connection failed with code {rc}")

        mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        mqtt_client.on_connect = on_connect
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        time.sleep(2)  # Wait for connection
    except ImportError:
        print("[ERROR] paho-mqtt not installed! Run: pip install paho-mqtt")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] MQTT connection failed: {e}")
        sys.exit(1)
else:
    import requests

cycle = 0

while True:
    cycle += 1

    # ─── Normal load ───
    voltage = 220.0 + random.uniform(-2, 2)
    temperature = 26.0 + random.uniform(-1, 3)
    humidity = 50.0 + random.uniform(-5, 5)
    current = 1.2 + random.uniform(-0.2, 0.5)

    # ─── High-load spike every ~30 seconds (15 cycles × 2s) ───
    if cycle % 15 == 0:
        current = random.uniform(3.5, 4.5)  # Spike above 3.0A threshold
        temperature += random.uniform(2, 5)   # Temperature rises with high load
        print(f"\n⚡ [SPIKE] Simulating heavy load: {current:.2f}A\n")

    power = round(voltage * current, 2)

    data = {
        "voltage": float(int(voltage * 10) / 10),
        "temperature": float(int(temperature * 10) / 10),
        "humidity": float(int(humidity * 10) / 10),
        "current": float(int(current * 100) / 100),
        "power": power,
    }

    if USE_MQTT:
        # ── MQTT mode: publish to HiveMQ Cloud ──
        try:
            payload = json.dumps(data)
            result = mqtt_client.publish(MQTT_TOPIC, payload)
            if result.rc == 0:
                print(
                    f"[{cycle:03d}] MQTT Published | V={data['voltage']}V | "
                    f"I={data['current']}A | P={power}W"
                )
            else:
                print(f"[{cycle:03d}] MQTT Publish failed (rc={result.rc})")
        except Exception as e:
            print(f"[{cycle:03d}] MQTT Error: {e}")
    else:
        # ── HTTP mode: POST to local Flask server ──
        try:
            response = requests.post(SERVER_URL, json=data)
            if response.status_code == 200:
                result = response.json()
                pred = result.get('prediction', 0)
                print(
                    f"[{cycle:03d}] V={data['voltage']}V | "
                    f"I={data['current']}A | "
                    f"P={power}W | "
                    f"Pred={pred:.2f}A"
                )
            else:
                print(f"[{cycle:03d}] Failed. Code: {response.status_code}")
        except Exception as e:
            print(f"[{cycle:03d}] Could not connect: {e}")

    time.sleep(2)  # Send data every 2 seconds
