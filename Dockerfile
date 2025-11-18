FROM python:3.9-slim

# Install Chrome from direct download (more reliable)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    unzip \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# Use webdriver-manager to automatically handle ChromeDriver version
RUN pip install webdriver-manager

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files (including the required model files: random_forest_model.joblib, scaler.joblib, feature_names.txt)
COPY . .

# Expose port
EXPOSE $PORT

# Start command
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 2 --timeout 120
