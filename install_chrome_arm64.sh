#!/bin/bash

# Chrome installation script for ARM64 systems
# This script installs Chrome and ChromeDriver for ARM64 architecture

echo "🚀 Installing Chrome for ARM64 systems..."

# Detect system architecture
ARCH=$(uname -m)
echo "📋 Detected architecture: $ARCH"

if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
    echo "✅ ARM64 architecture detected, proceeding with installation..."
    
    # Update package list
    echo "📦 Updating package list..."
    sudo apt update
    
    # Install dependencies
    echo "📦 Installing dependencies..."
    sudo apt install -y wget curl gnupg2 software-properties-common apt-transport-https ca-certificates
    
    # Add Google Chrome repository
    echo "🔑 Adding Google Chrome repository..."
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
    echo "deb [arch=arm64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
    
    # Update package list again
    sudo apt update
    
    # Install Google Chrome
    echo "🌐 Installing Google Chrome..."
    sudo apt install -y google-chrome-stable
    
    # Install ChromeDriver
    echo "🔧 Installing ChromeDriver..."
    
    # Get Chrome version
    CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+')
    echo "📋 Chrome version: $CHROME_VERSION"
    
    # Download ChromeDriver for ARM64
    CHROMEDRIVER_VERSION=$(curl -s "https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION")
    echo "📋 ChromeDriver version: $CHROMEDRIVER_VERSION"
    
    # Create drivers directory
    sudo mkdir -p /opt/chromedriver
    
    # Download and install ChromeDriver
    wget -O /tmp/chromedriver.zip "https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip"
    sudo unzip /tmp/chromedriver.zip -d /opt/chromedriver/
    sudo chmod +x /opt/chromedriver/chromedriver
    sudo ln -sf /opt/chromedriver/chromedriver /usr/local/bin/chromedriver
    
    # Clean up
    rm /tmp/chromedriver.zip
    
    # Verify installation
    echo "✅ Verifying installation..."
    google-chrome --version
    chromedriver --version
    
    echo "🎉 Chrome and ChromeDriver installation completed successfully!"
    
elif [[ "$ARCH" == "x86_64" ]]; then
    echo "📋 x86_64 architecture detected, using standard installation..."
    
    # Standard Chrome installation for x86_64
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | sudo tee /etc/apt/sources.list.d/google-chrome.list
    sudo apt update
    sudo apt install -y google-chrome-stable
    
    echo "✅ Chrome installation completed!"
    
else
    echo "❌ Unsupported architecture: $ARCH"
    echo "This script supports ARM64 (aarch64) and x86_64 architectures only."
    exit 1
fi

# Install additional dependencies for Selenium
echo "📦 Installing additional Python dependencies..."
pip3 install --upgrade selenium webdriver-manager

echo "🎉 All installations completed successfully!"
echo ""
echo "📋 Installation Summary:"
echo "  - Chrome: $(google-chrome --version 2>/dev/null || echo 'Not installed')"
echo "  - ChromeDriver: $(chromedriver --version 2>/dev/null || echo 'Not installed')"
echo "  - Architecture: $ARCH"
echo ""
echo "🚀 You can now run the WhatsApp UserBot!"
