FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/temp /app/sessions /app/logs /app/data /app/modules/system /app/modules/custom && \
    chmod -R 777 /app/temp /app/sessions /app/logs /app/data /app/modules && \
    ln -sf /usr/bin/chromium /usr/bin/chromium-browser && \
    ln -sf /usr/bin/chromium-driver /usr/bin/chromedriver

RUN rm -f /tmp/.X*-lock

CMD ["python", "main.py", "--debug"]
