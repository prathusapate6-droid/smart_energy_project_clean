# Gunicorn configuration for Render deployment
# Prevents worker timeout during TensorFlow model loading

# Worker timeout: 120 seconds (TF model load can take 60s on free tier)
timeout = 120

# Keep-alive: longer connection for MQTT data flow
keepalive = 5

# Single worker to maintain one MQTT connection
workers = 1

# 2 threads for handling HTTP + MQTT simultaneously
threads = 2

# Log to stdout
accesslog = "-"
errorlog = "-"
loglevel = "info"
