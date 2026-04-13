#include <DHT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>

// ══════════════════════════════════════════════════════════
//  AI Smart Grid — ESP32 Firmware v6 (MQTT + HiveMQ Cloud) 1
//  Prathamesh Sapate
//  Sends sensor data via MQTT to HiveMQ Cloud broker
//  Server (Flask on Render) subscribes to receive data
// ══════════════════════════════════════════════════════════

// ────── WiFi Credentials ──────
const char *ssid = "Project";
const char *password = "1234567890";

// ────── HiveMQ Cloud MQTT Credentials ──────
#define MQTT_BROKER "e5c6d611df63436992755767b6967071.s1.eu.hivemq.cloud"
#define MQTT_PORT 8883                   // TLS encrypted port (secure)
#define MQTT_USERNAME "smartwater"       // HiveMQ Cloud username
#define MQTT_PASSWORD "SmartWater2026!"  // HiveMQ Cloud password
#define MQTT_TOPIC "smartgrid/sensor"    // Topic to publish sensor data

// ────── Voltage Calibration ──────
// If voltage reads HIGH: decrease VOLTAGE_SCALE
// If voltage reads LOW : increase VOLTAGE_SCALE
// Formula: VOLTAGE_SCALE = actual_voltage / measured_voltage
// Example: 220.0 / 349.3 = 0.630
#define VOLTAGE_SCALE 0.630f

// ────── Current Calibration ──────
// If current reads HIGH: decrease CURRENT_SCALE
// If current reads LOW : increase CURRENT_SCALE
// Example: measured=1.79A, actual=0.26A (60W/234V) → scale = 0.26/1.79 = 0.145
#define CURRENT_SCALE 0.145f // ← Tune: actual_A / measured_A

// ══════════ SENSOR PINS (unchanged from original) ══════════
#define ACS712_PIN 34   // Current sensor (ACS712)  — Analog
#define ZMPT101B_PIN 35 // Voltage sensor (ZMPT101B) — Analog
#define DHT_PIN 4       // DHT11 temperature & humidity
#define DHT_TYPE DHT11

// ══════════ ACS712 CALIBRATION ══════════
// ACS712-20A module → 100 mV/A
// Change to 185 for 5A module, 66 for 30A module
int mVperAmp = 100;

// Auto-calibrated at startup: stores no-load ADC noise baseline
// This prevents ESP32 ADC noise from showing as phantom amps
float zeroCurrentVpp = 0.0;

DHT dht(DHT_PIN, DHT_TYPE);

// ══════════ MQTT Client ══════════
WiFiClientSecure espClient;
PubSubClient mqttClient(espClient);

// ══════════ TIMER ══════════
unsigned long lastTime = 0;
unsigned long sendDelay = 5000; // Send every 5 seconds

// HiveMQ Cloud root CA certificate (ISRG Root X1 — used by Let's Encrypt)
// This is needed for TLS connection to HiveMQ Cloud
static const char *root_ca PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogZiUvsNV8jalnFBtjodEnLkxvLoFuoP0RgBaV30QLvIbwP
dVJBkIBIyRFXQklJRZSu9PYGfWcuH3Hh1QDWNhFrJv+qlHaFR5HTRVBVUVFV4L7b
bwRasvTaXnVD1Pf1ZG3BEKjfio7oV0wQ1IYeV06p+r0gaSFW7GKaSS4e6inDnkaj
AAEKQ+AAAFq9AlQ/T3JSaYDv455C6V1j8pV7xtC6fz8WPahW9snqZ6JbMcOw1PO2
9aZh/BQEK4j0JBI+RuWVyYCLRedHfMnVZNYV4zoZh2gaZrBGGkCmnUJkxqm2bR8a
YDZPfwpNC8RC8CNA7BH1SrfC9de2ppSJ0Z9/a2SDq6Z7YD7BdN5nagmYuHrfQv41
tLdHfKOaL1p7RDa2hD1dBv3fbi1HH7D65tjEQXcbJ7xP1TRz2qkMpEKx8HNzPnCP
Jst2U0CJJoIq1ZAMqUi95pe+grVGPV6Qd0I9afI0POxbJ7ELttox+JGXnHc=
-----END CERTIFICATE-----
)EOF";


// ══════════════════════════════════════════════════════════
//  CURRENT SENSOR — ACS712
//  Exact algorithm from Current_Sensor_ACS712.ino
//  Uses peak-to-peak Vpp method (works correctly for AC loads)
// ══════════════════════════════════════════════════════════
float getVPP() {
  float result;
  int readValue;
  int maxValue = 0;
  int minValue = 4095; // ESP32 ADC 12-bit max

  uint32_t start_time = millis();
  while ((millis() - start_time) < 500) { // Sample for 500ms
    readValue = analogRead(ACS712_PIN);
    if (readValue > maxValue)
      maxValue = readValue;
    if (readValue < minValue)
      minValue = readValue;
  }
  result = ((maxValue - minValue) * 4.9) / 4095.0; // ESP32 ADC → Volts
  return result;
}

// Called once in setup() with NO LOAD connected.
// Measures baseline ADC noise and stores it as zero reference.
void calibrateCurrentSensor() {
  Serial.println(
      "[CAL] Calibrating current sensor — ensure no load is connected!");
  float sum = 0.0;
  int samples = 5;
  for (int i = 0; i < samples; i++) {
    sum += getVPP();
    delay(100);
  }
  zeroCurrentVpp = sum / samples;
  Serial.print("[CAL] Zero-load Vpp baseline = ");
  Serial.print(zeroCurrentVpp, 4);
  Serial.println(" V (this is subtracted from every reading)");
}

float readCurrent() {
  float Voltage = getVPP() - zeroCurrentVpp; // subtract calibrated baseline
  if (Voltage < 0.0)
    Voltage = 0.0;
  double VRMS = (Voltage / 2.0) * 0.707;       // Vpp → Vrms
  double AmpsRMS = (VRMS * 1000.0) / mVperAmp; // NO -0.3 offset!
                                               // zeroCurrentVpp handles it
  if (AmpsRMS < 0.0)
    AmpsRMS = 0.0;
  AmpsRMS *= CURRENT_SCALE;
  return (float)AmpsRMS;
}

// ══════════════════════════════════════════════════════════
//  VOLTAGE SENSOR — ZMPT101B
//  Exact algorithm from AC_voltage_sensor_ON_esp32.ino
//  Uses peak detection with ADC threshold 3300
// ══════════════════════════════════════════════════════════
float readVoltage() {
  double sensorValue1;
  int val[100];
  int max_v = 0;
  double VmaxD = 0;
  double VeffD = 0;
  double Veff = 0;

  // Sample 100 readings, only keep values above threshold (AC peaks)
  for (int i = 0; i < 100; i++) {
    sensorValue1 = analogRead(ZMPT101B_PIN);
    if (analogRead(ZMPT101B_PIN) > 3300) {
      val[i] = (int)sensorValue1;
    } else {
      val[i] = 0;
    }
    delay(1);
  }

  // Find peak
  max_v = 0;
  for (int i = 0; i < 100; i++) {
    if (val[i] > max_v)
      max_v = val[i];
    val[i] = 0; // reset for next call
  }

  if (max_v != 0) {
    VmaxD = max_v;
    VeffD = VmaxD / sqrt(2);
    Veff = ((VeffD / -100.24) * -15) * VOLTAGE_SCALE; // calibrated
  } else {
    Veff = 0; // no AC detected
  }

  return (float)Veff;
}

// ══════════════════════════════════════════════════════════
//  TEMPERATURE & HUMIDITY — DHT11
//  Exact logic from DHT_Sensor.ino
// ══════════════════════════════════════════════════════════
float readTemperature() {
  float t = dht.readTemperature();
  if (isnan(t)) {
    Serial.println(F("[DHT] Failed to read temperature! Using fallback."));
    return 25.0;
  }
  return t;
}

float readHumidity() {
  float h = dht.readHumidity();
  if (isnan(h)) {
    Serial.println(F("[DHT] Failed to read humidity! Using fallback."));
    return 50.0;
  }
  return h;
}

// ══════════════════════════════════════════════════════════
//  MQTT — Connect to HiveMQ Cloud
// ══════════════════════════════════════════════════════════
void connectMQTT() {
  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);

  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting to HiveMQ Cloud...");
    String clientId = "ESP32-SmartGrid-" + String(random(0xffff), HEX);

    if (mqttClient.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD)) {
      Serial.println(" ✅ Connected!");
    } else {
      Serial.print(" ❌ Failed, rc=");
      Serial.print(mqttClient.state());
      Serial.println(" → Retrying in 5s...");
      delay(5000);
    }
  }
}

// ══════════════════════════════════════════════════════════
//  SETUP
// ══════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  Serial.println(F("\n══════════════════════════════════════"));
  Serial.println(F("  AI Smart Grid — ESP32 Node v6 MQTT"));
  Serial.println(F("  Sends data via HiveMQ Cloud"));
  Serial.println(F("══════════════════════════════════════"));

  dht.begin();
  Serial.println(F("[SENSORS] DHT11    on GPIO4"));
  Serial.println(F("[SENSORS] ACS712   on GPIO34"));
  Serial.println(F("[SENSORS] ZMPT101B on GPIO35"));

  // Auto-calibrate current sensor at startup (no load should be connected)
  calibrateCurrentSensor();

  // Connect WiFi
  WiFi.begin(ssid, password);
  Serial.print("[WiFi] Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("[WiFi] Connected! IP: ");
  Serial.println(WiFi.localIP());

  // Setup TLS for HiveMQ Cloud
  espClient.setCACert(root_ca);

  // Connect to MQTT broker
  connectMQTT();
  Serial.println();
}

// ══════════════════════════════════════════════════════════
//  MAIN LOOP
// ══════════════════════════════════════════════════════════
void loop() {
  // Ensure MQTT stays connected (auto-reconnect)
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Connection lost — reconnecting...");
    connectMQTT();
  }
  mqttClient.loop();

  if ((millis() - lastTime) > sendDelay) {
    if (WiFi.status() == WL_CONNECTED) {

      float voltage = readVoltage();
      float current = readCurrent();
      float temperature = readTemperature();
      float humidity = readHumidity();
      float power = voltage * current;

      // Debug print to Serial Monitor
      Serial.print("[SENSOR] V=");
      Serial.print(voltage, 1);
      Serial.print("V  I=");
      Serial.print(current, 2);
      Serial.print("A  T=");
      Serial.print(temperature, 1);
      Serial.print("°C  H=");
      Serial.print(humidity, 1);
      Serial.print("%  P=");
      Serial.print(power, 1);
      Serial.println("W");

      // Build JSON payload
      String json = "{\"voltage\":" + String(voltage, 1) +
                    ",\"current\":" + String(current, 2) +
                    ",\"temperature\":" + String(temperature, 1) +
                    ",\"humidity\":" + String(humidity, 1) +
                    ",\"power\":" + String(power, 2) + "}";

      // Publish to MQTT topic
      if (mqttClient.publish(MQTT_TOPIC, json.c_str())) {
        Serial.print("[MQTT] Published → ");
        Serial.println(json);
      } else {
        Serial.println("[MQTT] ❌ Publish failed!");
      }

    } else {
      Serial.println("[WiFi] Disconnected — reconnecting...");
      WiFi.reconnect();
    }
    lastTime = millis();
  }
}
