import pandas as pd  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from sklearn.preprocessing import MinMaxScaler  # type: ignore[import-untyped]
from tensorflow.keras.models import Sequential  # type: ignore[import-untyped]
from tensorflow.keras.layers import LSTM, Dense, Dropout  # type: ignore[import-untyped]
import pickle


def train_model() -> None:
    """Train an LSTM model on sensor data for load forecasting."""
    print("Loading data...")
    df = pd.read_csv('sensor_data_large.csv')

    # We want to predict current from voltage, humidity, temperature
    features = ['voltage', 'humidity', 'temperature']
    target = 'current'

    data = df[features + [target]].values

    print("Scaling data...")
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)

    # Save the scaler for inference later
    with open('scaler.pkl', 'wb') as f:
        pickle.dump(scaler, f)

    # Prepare sequence data
    seq_length = 12  # 1 hour of past data (12 * 5 mins)
    X, y = [], []
    for i in range(len(scaled_data) - seq_length):
        X.append(scaled_data[i:i + seq_length, :-1])  # Features
        y.append(scaled_data[i + seq_length, -1])      # Target (current)

    X = np.array(X)
    y = np.array(y)

    # Split train and test
    split = int(0.8 * len(X))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    print(f"Training shape: {X_train.shape}")

    print("Building LSTM model...")
    model = Sequential([
        LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])),
        Dropout(0.2),
        LSTM(units=50, return_sequences=False),
        Dropout(0.2),
        Dense(units=1)
    ])

    model.compile(optimizer='adam', loss='mean_squared_error')

    print("Training the model (this will take a few moments)...")
    model.fit(X_train, y_train, epochs=10, batch_size=32,
              validation_data=(X_test, y_test), verbose=1)

    print("Saving model to 'lstm_model.keras'...")
    model.save('lstm_model.keras')
    print("Model Training Complete!")


if __name__ == '__main__':
    train_model()
