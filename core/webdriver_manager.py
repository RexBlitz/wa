"""
Enhanced WebDriver Manager with ARM64 support and multiple fallback options
Handles different architectures and provides robust WebDriver setup
"""

import os
import sys
import platform
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService

try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False


class WebDriverManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.driver_type = None
        
        # System information
        self.system = platform.system().lower()
        self.machine = platform.machine().lower()
        self.is_arm = 'arm' in self.machine or 'aarch64' in self.machine
        
        self.logger.info(f"🖥️ System: {self.system}, Architecture: {self.machine}, ARM: {self.is_arm}")

    async def setup_driver(self) -> Optional[webdriver.Chrome]:
        """Setup WebDriver with multiple fallback options"""
        self.logger.info("🌐 Setting up WebDriver with enhanced compatibility...")
        
        # Try different driver setups in order of preference
        setup_methods = [
            self._setup_chrome_with_custom_path,
            self._setup_chrome_with_webdriver_manager,
            self._setup_firefox_fallback,
            self._setup_chrome_system_binary,
            self._setup_headless_chrome_docker_style
        ]
        
        for i, method in enumerate(setup_methods, 1):
            try:
                self.logger.info(f"🔄 Attempting WebDriver setup method {i}/{len(setup_methods)}: {method.__name__}")
                driver = await method()
                
                if driver:
                    self.driver = driver
                    self.logger.info(f"✅ WebDriver setup successful with method: {method.__name__}")
                    return driver
                    
            except Exception as e:
                self.logger.warning(f"⚠️ WebDriver setup method {i} failed: {e}")
                continue
        
        self.logger.error("❌ All WebDriver setup methods failed")
        return None

    async def _setup_chrome_with_custom_path(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome with custom binary and driver paths for ARM64"""
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Custom Chrome binary paths for different systems
            chrome_binaries = self._get_chrome_binary_paths()
            chrome_binary = None
            
            for binary_path in chrome_binaries:
                if os.path.exists(binary_path):
                    chrome_binary = binary_path
                    break
            
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
                self.logger.info(f"📍 Using Chrome binary: {chrome_binary}")
            
            # Try to find ChromeDriver
            driver_path = self._find_chromedriver()
            
            if driver_path:
                service = Service(driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                self.driver_type = "chrome_custom"
                return driver
            
        except Exception as e:
            self.logger.debug(f"Custom Chrome setup failed: {e}")
        
        return None

    async def _setup_chrome_with_webdriver_manager(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome using webdriver-manager with ARM64 support"""
        if not WEBDRIVER_MANAGER_AVAILABLE:
            return None
        
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Use webdriver-manager with custom cache
            cache_dir = Path("./drivers_cache")
            cache_dir.mkdir(exist_ok=True)
            
            # For ARM64, try to download compatible driver
            if self.is_arm:
                # Set custom download URL for ARM64 if needed
                os.environ['WDM_CHROME_DRIVER_URL'] = self._get_arm64_chromedriver_url()
            
            driver_path = ChromeDriverManager(cache_valid_range=7).install()
            
            # Make driver executable
            os.chmod(driver_path, 0o755)
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_webdriver_manager"
            return driver
            
        except Exception as e:
            self.logger.debug(f"WebDriver Manager setup failed: {e}")
        
        return None

    async def _setup_firefox_fallback(self) -> Optional[webdriver.Firefox]:
        """Setup Firefox as fallback option"""
        try:
            firefox_options = FirefoxOptions()
            
            # Basic Firefox options
            if self.config.whatsapp.headless:
                firefox_options.add_argument("--headless")
            
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.set_preference("general.useragent.override", self.config.whatsapp.user_agent)
            
            # Session directory for Firefox
            profile_dir = Path(self.config.whatsapp.session_dir) / "firefox_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            
            # Try to get GeckoDriver
            if WEBDRIVER_MANAGER_AVAILABLE:
                driver_path = GeckoDriverManager().install()
                os.chmod(driver_path, 0o755)
                service = FirefoxService(driver_path)
            else:
                service = FirefoxService()  # Use system geckodriver
            
            driver = webdriver.Firefox(service=service, options=firefox_options)
            self.driver_type = "firefox"
            self.logger.info("🦊 Using Firefox WebDriver")
            return driver
            
        except Exception as e:
            self.logger.debug(f"Firefox setup failed: {e}")
        
        return None

    async def _setup_chrome_system_binary(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome using system-installed binaries"""
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Try system chromedriver
            system_drivers = [
                "/usr/bin/chromedriver",
                "/usr/local/bin/chromedriver",
                "/opt/google/chrome/chromedriver",
                "chromedriver"  # In PATH
            ]
            
            for driver_path in system_drivers:
                try:
                    if driver_path == "chromedriver" or os.path.exists(driver_path):
                        service = Service(driver_path if driver_path != "chromedriver" else None)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        self.driver_type = "chrome_system"
                        self.logger.info(f"📍 Using system ChromeDriver: {driver_path}")
                        return driver
                except:
                    continue
            
        except Exception as e:
            self.logger.debug(f"System Chrome setup failed: {e}")
        
        return None

    async def _setup_headless_chrome_docker_style(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome with Docker-style headless configuration"""
        try:
            chrome_options = Options()
            
            # Docker-style Chrome options
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-web-security")
            chrome_options.add_argument("--disable-features=VizDisplayCompositor")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-plugins")
            chrome_options.add_argument("--disable-images")
            chrome_options.add_argument("--disable-javascript")
            chrome_options.add_argument("--virtual-time-budget=5000")
            chrome_options.add_argument(f"--user-agent={self.config.whatsapp.user_agent}")
            
            # Unique user data directory
            unique_session_dir = Path(self.config.whatsapp.session_dir) / f"chrome_session_{uuid.uuid4().hex[:8]}"
            unique_session_dir.mkdir(parents=True, exist_ok=True)
            chrome_options.add_argument(f"--user-data-dir={unique_session_dir}")
            
            # Try with system Chrome
            service = Service()  # Use default service
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_docker_style"
            self.logger.info("🐳 Using Docker-style headless Chrome")
            return driver
            
        except Exception as e:
            self.logger.debug(f"Docker-style Chrome setup failed: {e}")
        
        return None

    def _get_base_chrome_options(self) -> Options:
        """Get base Chrome options with session management"""
        chrome_options = Options()
        
        # Basic options
        chrome_options.add_argument(f"--user-agent={self.config.whatsapp.user_agent}")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Headless mode
        if self.config.whatsapp.headless:
            chrome_options.add_argument("--headless=new")
        
        # Unique session directory to avoid conflicts
        unique_session_dir = Path(self.config.whatsapp.session_dir) / f"chrome_session_{uuid.uuid4().hex[:8]}"
        unique_session_dir.mkdir(parents=True, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={unique_session_dir}")
        
        # ARM64 specific options
        if self.is_arm:
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
        
        return chrome_options

    def _get_chrome_binary_paths(self) -> list:
        """Get possible Chrome binary paths for different systems"""
        paths = []
        
        if self.system == "linux":
            paths.extend([
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
                "/snap/bin/chromium",
                "/opt/google/chrome/chrome",
                "/usr/local/bin/chrome"
            ])
        elif self.system == "darwin":  # macOS
            paths.extend([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"
            ])
        elif self.system == "windows":
            paths.extend([
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            ])
        
        return paths

    def _find_chromedriver(self) -> Optional[str]:
        """Find ChromeDriver in various locations"""
        possible_paths = [
            "/usr/bin/chromedriver",
            "/usr/local/bin/chromedriver",
            "/opt/google/chrome/chromedriver",
            "./chromedriver",
            "./drivers/chromedriver"
        ]
        
        # Check if chromedriver is in PATH
        try:
            result = subprocess.run(["which", "chromedriver"], capture_output=True, text=True)
            if result.returncode == 0:
                possible_paths.insert(0, result.stdout.strip())
        except:
            pass
        
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path
        
        return None

    def _get_arm64_chromedriver_url(self) -> str:
        """Get ARM64 ChromeDriver download URL"""
        # This would return a custom URL for ARM64 ChromeDriver
        # For now, return empty string to use default
        return ""

    async def install_chrome_arm64(self):
        """Install Chrome for ARM64 systems"""
        if not self.is_arm or self.system != "linux":
            return False
        
        try:
            self.logger.info("📦 Installing Chrome for ARM64...")
            
            # Commands to install Chrome on ARM64 Linux
            commands = [
                "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -",
                "echo 'deb [arch=arm64] http://dl.google.com/linux/chrome/deb/ stable main' | sudo tee /etc/apt/sources.list.d/google-chrome.list",
                "sudo apt update",
                "sudo apt install -y google-chrome-stable"
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    self.logger.warning(f"⚠️ Command failed: {cmd}")
                    self.logger.warning(f"Error: {result.stderr}")
            
            self.logger.info("✅ Chrome installation completed")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to install Chrome: {e}")
            return False

    def get_driver_info(self) -> Dict[str, Any]:
        """Get information about the current driver"""
        if not self.driver:
            return {"status": "not_initialized"}
        
        try:
            capabilities = self.driver.capabilities
            return {
                "status": "active",
                "driver_type": self.driver_type,
                "browser_name": capabilities.get("browserName"),
                "browser_version": capabilities.get("browserVersion"),
                "platform": capabilities.get("platformName"),
                "system": self.system,
                "architecture": self.machine,
                "is_arm": self.is_arm
            }
        except:
            return {"status": "error", "driver_type": self.driver_type}

    async def restart_driver(self):
        """Restart the WebDriver"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        
        self.driver = await self.setup_driver()
        return self.driver is not None

    def cleanup(self):
        """Cleanup WebDriver resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
        
        # Clean up temporary session directories
        try:
            session_base = Path(self.config.whatsapp.session_dir)
            for session_dir in session_base.glob("chrome_session_*"):
                if session_dir.is_dir():
                    import shutil
                    shutil.rmtree(session_dir, ignore_errors=True)
        except:
            pass
