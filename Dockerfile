# Use a lightweight base image with Python
FROM python:3.9-slim

# Install system dependencies for Chromium and headless browsing
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    libxi6 \
    libgconf-2-4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file first to leverage caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app

# Create directories for temp and sessions
RUN mkdir -p /app/temp /app/sessions && \
    chmod -R 777 /app/temp /app/sessions

# Set environment variables for headless browsing
ENV DISPLAY=:99
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

# Run the bot with Xvfb for headless browsing
CMD ["sh", "-c", "Xvfb :99 -screen 0 1024x768x24 & python main.py"]
