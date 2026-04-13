# Windows Installation Guide for AI Smart Grid

This guide provides simple, step-by-step instructions to get the AI Smart Grid project running on a Windows machine.

## Prerequisites

1. **Python 3.8 to 3.11** installed. Download from [python.org](https://www.python.org/downloads/).
   - *Important: During installation, make sure to check the box that says **"Add Python to PATH"**.*
2. **Arduino IDE** (only if you will be uploading code to the physical ESP32 board).

---

## Setup Steps

### 1. Open Terminal and Navigate to Project

Open **Command Prompt** (CMD) or **PowerShell**. Navigate to the folder where you have saved or extracted the project.

```cmd
cd path\to\smart_energy_project_clean
```

### 2. Create a Virtual Environment

A virtual environment keeps the project dependencies isolated from the rest of your system.

```cmd
python -m venv .venv
```

### 3. Activate the Virtual Environment

Activate the environment so that we can install the necessary packages.

- If using **Command Prompt** (cmd):

  ```cmd
  .venv\Scripts\activate.bat
  ```

- If using **PowerShell**:

  ```powershell
  .venv\Scripts\Activate.ps1
  ```

*(You will know it was successful if you see `(.venv)` appear at the start of your command line).*

### 4. Install Dependencies

Ensure you install all the required Python libraries needed to run the AI and Web Server:

```cmd
pip install -r requirements.txt
pip install flask-cors tensorflow
```

### 5. Start the Backend Server

Start the Flask application that handles the AI prediction and the web dashboard:

```cmd
python app.py
```

Wait a few seconds for the server to spin up. Then, open your web browser and go to: **<http://127.0.0.1:5050>**

### 6. Start the Hardware Simulator

If you are testing the demand-response logic without the physical ESP32 board connected, you can run the provided simulator.
Open a **new** Command Prompt window, navigate to the folder, activate the environment, and run the file:

```cmd
cd path\to\smart_energy_project_clean
.venv\Scripts\activate.bat
python test_esp32_sim.py
```

---

## Troubleshooting

- **`Execution of scripts is disabled on this system` (PowerShell error)**: Before step 3, run `Set-ExecutionPolicy Unrestricted -Scope CurrentUser` as Administrator, or just use Command Prompt instead of PowerShell.
- **`python is not recognized`**: You forgot to check "Add Python to PATH" when installing Python. Re-run the Python installer and modify the installation.
- **TensorFlow installation errors**: Make sure you are using Python version 3.11 or lower, as TensorFlow may not yet support the very latest Python versions properly on Windows.
