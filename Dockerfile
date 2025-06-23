# Use a recent Ubuntu LTS base image
FROM ubuntu:22.04

# Set non-interactive mode for apt (prevents prompts during apt install)
ENV DEBIAN_FRONTEND=noninteractive

# Update apt and install system dependencies:
# - python3 and python3-pip for Python environment
# - chromium-browser and chromium-chromedriver for Selenium automation on ARM64
# - Essential libraries for headless browser operation (common dependencies)
RUN apt update && apt install -y --no-install-recommends \
    python3 \
    python3-pip \
    chromium-browser \
    chromium-chromedriver \
    fontconfig \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm-dev \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm-dev \
    libexpat1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libpci-dev \
    libxkbcommon0 \
    libxshmfence-dev \
    libssl-dev \
    libxtst6 \
    libva-drm2 \
    libva-x11-2 \
    libva2 \
    mesa-va-drivers \
    mesa-vdpau-drivers \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# (Optional but recommended) Symlink python to python3 for convenience
# If you always use 'python3' in your scripts/commands, this is not strictly necessary.
# However, many common Python tools might default to 'python'.
RUN ln -s /usr/bin/python3 /usr/bin/python

# Set the working directory inside the container
WORKDIR /app

# Copy only requirements.txt first to take advantage of Docker layer caching.
# If requirements.txt doesn't change, this layer (and subsequent ones) can be reused.
COPY requirements.txt .

# Install Python dependencies.
# --no-cache-dir reduces image size.
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Set the entrypoint command to run your main application file
# Using ["python3", "main.py"] ensures python3 is explicitly called
CMD ["python3", "main.py"]
