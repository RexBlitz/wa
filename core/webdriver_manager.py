"""
Enhanced WebDriver Manager with improved compatibility and error handling
"""

import os
import sys
import platform
import subprocess
import time
import uuid
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService

# Try to import webdriver-manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False
    print("⚠️ webdriver-manager not available. Install with: pip install webdriver-manager")


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
        
        # Create drivers directory
        self.drivers_dir = Path("./drivers")
        self.drivers_dir.mkdir(exist_ok=True)

    async def setup_driver(self) -> Optional[webdriver.Chrome]:
        """Setup WebDriver with multiple fallback options"""
        self.logger.info("🌐 Setting up WebDriver with enhanced compatibility...")
        
        # Try different driver setups in order of preference
        setup_methods = [
            self._setup_chrome_with_webdriver_manager,
            self._setup_chrome_system_binary,
            self._setup_chrome_with_custom_binary,
            self._setup_edge_fallback,
            self._setup_firefox_fallback,
            self._setup_chrome_portable
        ]
        
        for i, method in enumerate(setup_methods, 1):
            try:
                self.logger.info(f"🔄 Attempting WebDriver setup method {i}/{len(setup_methods)}: {method.__name__}")
                driver = await method()
                
                if driver:
                    self.driver = driver
                    self.logger.info(f"✅ WebDriver setup successful with method: {method.__name__}")
                    
                    # Test if driver is actually working
                    if await self._test_driver(driver):
                        return driver
                    else:
                        self.logger.warning("⚠️ Driver test failed, trying next method...")
                        try:
                            driver.quit()
                        except:
                            pass
                        continue
                        
            except Exception as e:
                self.logger.warning(f"⚠️ WebDriver setup method {i} failed: {e}")
                continue
        
        self.logger.error("❌ All WebDriver setup methods failed")
        return None

    async def _test_driver(self, driver) -> bool:
        """Test if driver is working properly"""
        try:
            driver.get("https://www.google.com")
            return "Google" in driver.title
        except Exception as e:
            self.logger.debug(f"Driver test failed: {e}")
            return False

    async def _setup_chrome_with_webdriver_manager(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome using webdriver-manager"""
        if not WEBDRIVER_MANAGER_AVAILABLE:
            return None
        
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Download and setup ChromeDriver
            self.logger.info("📦 Downloading ChromeDriver...")
            driver_path = ChromeDriverManager().install()
            
            # Make driver executable (important for Linux/Mac)
            os.chmod(driver_path, 0o755)
            
            service = Service(driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_webdriver_manager"
            return driver
            
        except Exception as e:
            self.logger.debug(f"WebDriver Manager setup failed: {e}")
        
        return None

    async def _setup_chrome_system_binary(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome using system-installed binaries"""
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Try system chromedriver paths
            system_drivers = [
                "/usr/bin/chromedriver",
                "/usr/local/bin/chromedriver",
                "/opt/google/chrome/chromedriver",
                shutil.which("chromedriver")  # Check PATH
            ]
            
            for driver_path in system_drivers:
                if driver_path and os.path.exists(driver_path):
                    try:
                        service = Service(driver_path)
                        driver = webdriver.Chrome(service=service, options=chrome_options)
                        self.driver_type = "chrome_system"
                        self.logger.info(f"📍 Using system ChromeDriver: {driver_path}")
                        return driver
                    except Exception as e:
                        self.logger.debug(f"Failed with {driver_path}: {e}")
                        continue
            
            # Try without specifying service (use default)
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_default"
            return driver
            
        except Exception as e:
            self.logger.debug(f"System Chrome setup failed: {e}")
        
        return None

    async def _setup_chrome_with_custom_binary(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome with custom binary paths"""
        try:
            chrome_options = self._get_base_chrome_options()
            
            # Find Chrome binary
            chrome_binaries = self._get_chrome_binary_paths()
            chrome_binary = None
            
            for binary_path in chrome_binaries:
                if os.path.exists(binary_path):
                    chrome_binary = binary_path
                    break
            
            if chrome_binary:
                chrome_options.binary_location = chrome_binary
                self.logger.info(f"📍 Using Chrome binary: {chrome_binary}")
            
            # Try to use system chromedriver
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_custom_binary"
            return driver
            
        except Exception as e:
            self.logger.debug(f"Custom Chrome binary setup failed: {e}")
        
        return None

    async def _setup_edge_fallback(self) -> Optional[webdriver.Edge]:
        """Setup Microsoft Edge as fallback"""
        try:
            edge_options = EdgeOptions()
            
            # Basic Edge options
            edge_options.add_argument(f"--user-agent={getattr(self.config.whatsapp, 'user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')}")
            edge_options.add_argument("--no-sandbox")
            edge_options.add_argument("--disable-dev-shm-usage")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            
            # Headless mode
            if getattr(self.config.whatsapp, 'headless', False):
                edge_options.add_argument("--headless=new")
            
            # Session directory
            session_dir = Path(getattr(self.config.whatsapp, 'session_dir', './sessions')) / f"edge_session_{uuid.uuid4().hex[:8]}"
            session_dir.mkdir(parents=True, exist_ok=True)
            edge_options.add_argument(f"--user-data-dir={session_dir}")
            
            # Try with webdriver-manager
            if WEBDRIVER_MANAGER_AVAILABLE:
                try:
                    driver_path = EdgeChromiumDriverManager().install()
                    os.chmod(driver_path, 0o755)
                    service = EdgeService(driver_path)
                except:
                    service = EdgeService()
            else:
                service = EdgeService()
            
            driver = webdriver.Edge(service=service, options=edge_options)
            self.driver_type = "edge"
            self.logger.info("🌐 Using Microsoft Edge WebDriver")
            return driver
            
        except Exception as e:
            self.logger.debug(f"Edge setup failed: {e}")
        
        return None

    async def _setup_firefox_fallback(self) -> Optional[webdriver.Firefox]:
        """Setup Firefox as fallback option"""
        try:
            firefox_options = FirefoxOptions()
            
            # Basic Firefox options
            if getattr(self.config.whatsapp, 'headless', False):
                firefox_options.add_argument("--headless")
            
            firefox_options.add_argument("--no-sandbox")
            firefox_options.add_argument("--disable-dev-shm-usage")
            firefox_options.set_preference("general.useragent.override", 
                                         getattr(self.config.whatsapp, 'user_agent', 
                                                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'))
            
            # Session directory for Firefox
            profile_dir = Path(getattr(self.config.whatsapp, 'session_dir', './sessions')) / "firefox_profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            
            # Try to get GeckoDriver
            if WEBDRIVER_MANAGER_AVAILABLE:
                try:
                    driver_path = GeckoDriverManager().install()
                    os.chmod(driver_path, 0o755)
                    service = FirefoxService(driver_path)
                except:
                    service = FirefoxService()
            else:
                service = FirefoxService()
            
            driver = webdriver.Firefox(service=service, options=firefox_options)
            self.driver_type = "firefox"
            self.logger.info("🦊 Using Firefox WebDriver")
            return driver
            
        except Exception as e:
            self.logger.debug(f"Firefox setup failed: {e}")
        
        return None

    async def _setup_chrome_portable(self) -> Optional[webdriver.Chrome]:
        """Setup Chrome with portable/downloaded version"""
        try:
            chrome_options = self._get_base_chrome_options()
            
            # For environments where Chrome might not be installed
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--disable-default-apps")
            chrome_options.add_argument("--disable-popup-blocking")
            
            # Try minimal service
            service = Service()
            driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver_type = "chrome_portable"
            return driver
            
        except Exception as e:
            self.logger.debug(f"Portable Chrome setup failed: {e}")
        
        return None

    def _get_base_chrome_options(self) -> Options:
        """Get base Chrome options with session management"""
        chrome_options = Options()
        
        # Basic options
        user_agent = getattr(self.config.whatsapp, 'user_agent', 
                           'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument(f"--user-agent={user_agent}")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Headless mode
        if getattr(self.config.whatsapp, 'headless', False):
            chrome_options.add_argument("--headless=new")
        
        # Session directory
        session_base = Path(getattr(self.config.whatsapp, 'session_dir', './sessions'))
        unique_session_dir = session_base / f"chrome_session_{uuid.uuid4().hex[:8]}"
        unique_session_dir.mkdir(parents=True, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={unique_session_dir}")
        
        # Performance options
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")
        chrome_options.add_argument("--disable-css")
        chrome_options.add_argument("--disable-fonts")
        
        # ARM64 specific options
        if self.is_arm:
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-software-rasterizer")
            chrome_options.add_argument("--disable-background-timer-throttling")
            chrome_options.add_argument("--disable-backgrounding-occluded-windows")
            chrome_options.add_argument("--disable-renderer-backgrounding")
        
        # Window size for headless mode
        chrome_options.add_argument("--window-size=1920,1080")
        
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
                "/usr/local/bin/chrome",
                "/usr/local/bin/google-chrome"
            ])
        elif self.system == "darwin":  # macOS
            paths.extend([
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"
            ])
        elif self.system == "windows":
            paths.extend([
                "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                "C:\\Users\\{}\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe".format(os.getenv('USERNAME', 'user'))
            ])
        
        return paths

    def _install_chrome_if_needed(self):
        """Install Chrome if not available (Linux only)"""
        if self.system != "linux":
            return False
        
        try:
            self.logger.info("📦 Installing Chrome...")
            
            # Check if running as root
            if os.geteuid() != 0:
                self.logger.warning("⚠️ Chrome installation requires root privileges")
                return False
            
            # Commands to install Chrome
            commands = [
                "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -",
                "echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' | tee /etc/apt/sources.list.d/google-chrome.list",
                "apt update",
                "apt install -y google-chrome-stable"
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    self.logger.warning(f"⚠️ Command failed: {cmd}")
                    return False
            
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
                "is_arm": self.is_arm,
                "session_id": self.driver.session_id
            }
        except Exception as e:
            return {"status": "error", "driver_type": self.driver_type, "error": str(e)}

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
            session_base = Path(getattr(self.config.whatsapp, 'session_dir', './sessions'))
            for session_dir in session_base.glob("*_session_*"):
                if session_dir.is_dir():
                    shutil.rmtree(session_dir, ignore_errors=True)
        except Exception as e:
            self.logger.debug(f"Error cleaning up session directories: {e}")
        
        self.logger.info("🧹 WebDriver cleanup completed")
