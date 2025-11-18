FROM python:3.9-slim

# Install dependencies needed for key management, wget, unzip, curl, and xvfb
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    xvfb \
    lsb-release \
    xdg-utils \
    fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 libgcc1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome and dependencies using the modern key/repository method
RUN set -ex; \
    # Create the directory for keyrings if it doesn't exist
    mkdir -p /etc/apt/keyrings; \
    # Download the Google signing key and save it directly to the keyrings directory
    wget -q -O /etc/apt/keyrings/google-chrome.gpg https://dl.google.com/linux/linux_signing_key.pub; \
    # Add the Chrome repository list file, referencing the GPG key location
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list; \
    # Install Chrome and clean up
    apt-get update; \
    apt-get install -y google-chrome-stable; \
    rm -rf /var/lib/apt/lists/*

# Install ChromeDriver matching Chrome version
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '[0-9]+\.[0-9]+\.[0-9]+' | head -1) \
    && MAJOR_VERSION=$(echo $CHROME_VERSION | cut -d. -f1) \
    && CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$MAJOR_VERSION") \
    && wget -q "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip" \
    && unzip chromedriver_linux64.zip -d /usr/local/bin/ \
    && rm chromedriver_linux64.zip \
    && chmod +x /usr/local/bin/chromedriver

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300
