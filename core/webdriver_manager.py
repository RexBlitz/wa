"""
WebDriver Manager for WhatsApp UserBot
Handles WebDriver setup and cleanup
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging


class WebDriverManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.logger.info("🌐 WebDriverManager initialized")

    async def setup_driver(self):
        """Setup Chrome WebDriver with headless mode"""
        try:
            self.logger.info("🌐 Setting up WebDriver...")
            options = Options()
            options.binary_location = self.config.webdriver.chrome_binary
            options.add_argument('--headless=new')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument(f'user-agent={self.config.whatsapp.user_agent}')
            
            service = Service(self.config.webdriver.driver_path)
            self.driver = webdriver.Chrome(service=service, options=options)
            self.logger.info("✅ WebDriver setup complete")
            return self.driver
        except Exception as e:
            self.logger.error(f"❌ Failed to setup WebDriver: {e}", exc_info=True)
            return None

    def get_driver_info(self):
        """Get WebDriver information"""
        try:
            if self.driver:
                return {
                    'version': self.driver.capabilities['browserVersion'],
                    'capabilities': self.driver.capabilities
                }
            return {}
        except Exception as e:
            self.logger.error(f"❌ Failed to get driver info: {e}")
            return {}

    def cleanup(self):
        """Cleanup WebDriver"""
        try:
            if self.driver:
                self.driver.quit()
                self.logger.info("🧹 WebDriver cleaned up")
        except Exception as e:
            self.logger.error(f"❌ Failed to cleanup WebDriver: {e}")
        self.driver = None
