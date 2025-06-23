"""
Authentication manager for WhatsApp UserBot
Handles login, session management, and authentication methods
"""

import time
import json
import base64
from pathlib import Path
from typing import Dict, aAny, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class AuthenticationManager:
    def __init__(self, config, logger, telegram_bridge=None):
        self.config = config
        self.logger = logger
        self.session_data = {}
        self.authenticated = False
        self.telegram_bridge = telegram_bridge
        self.logger.info("🔐 AuthenticationManager initialized")

    async def authenticate(self, driver) -> bool:
        """Main authentication method"""
        self.logger.info("🔐 Starting authentication process...")
        try:
            if self.config.whatsapp.auth_method == "qr":
                success = await self._authenticate_qr(driver)
            elif self.config.whatsapp.auth_method == "phone":
                success = await self._authenticate_phone(driver)
            else:
                raise ValueError(f"Unsupported auth method: {self.config.whatsapp.auth_method}")
            if success:
                await self._save_session(driver)
                self.authenticated = True
            return success
        except Exception as e:
            self.logger.error(f"❌ Authentication failed: {e}", exc_info=True)
            return False

    async def _authenticate_qr(self, driver) -> bool:
        """Authenticate using QR code"""
        self.logger.info("📱 Authenticating with QR code...")
        try:
            max_attempts = 3
            driver.get("https://web.whatsapp.com")
            self.logger.debug("🌐 Loaded WhatsApp Web")
            time.sleep(5)
            
            for attempt in range(max_attempts):
                self.logger.info(f"🔄 QR authentication attempt {attempt + 1}/{max_attempts}")
                qr_element = None
                selectors = [
                    '[data-testid="qrcode"]',
                    'canvas[aria-label="Scan me!"]',
                    'div[data-testid="qr"] canvas'
                ]
                for selector in selectors:
                    try:
                        qr_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        self.logger.debug(f"Found QR element with selector: {selector}")
                        break
                    except:
                        self.logger.debug(f"No QR element found with selector: {selector}")
                
                if not qr_element:
                    self.logger.warning("⚠️ No QR code found, retrying...")
                    driver.refresh()
                    time.sleep(3)
                    continue
                
                qr_data = qr_element.get_attribute("data-ref")
                if not qr_data:
                    self.logger.warning("⚠️ No data-ref, falling back to toDataURL")
                    qr_data = driver.execute_script("return arguments[0].toDataURL('image/png');", qr_element)
                
                self.logger.debug(f"📱 QR data length: {len(qr_data)}")
                
                try:
                    import qrcode
                    qr = qrcode.QRCode(
                        version=1,
                        box_size=1,
                        border=0,
                        error_correction=qrcode.constants.ERROR_CORRECT_L
                    )
                    qr.add_data(qr_data[:500])
                    qr.make(fit=True)
                    self.logger.info("📱 Compact ASCII QR Code (scan this with WhatsApp):")
                    qr.print_ascii(invert=True)
                except Exception as e:
                    self.logger.error(f"❌ Failed to generate ASCII QR code: {e}")
                    try:
                        qr = qrcode.QRCode(
                            version=1,
                            box_size=1,
                            border=0,
                            error_correction=qrcode.constants.ERROR_CORRECT_L
                        )
                        qr.add_data("test-auth-fallback")
                        qr.make(fit=True)
                        self.logger.info("📱 Fallback ASCII QR Code:")
                        qr.print_ascii(invert=True)
                    except Exception as e:
                        self.logger.error(f"❌ Failed to generate fallback ASCII QR code: {e}")
                
                qr_path = await self._save_qr_code(qr_data)
                if qr_path:
                    self.logger.info(f"📱 QR Code saved to: {qr_path}")
                    if self.telegram_bridge:
                        try:
                            self.logger.debug("📤 Sending QR code to Telegram")
                            await self.telegram_bridge.forward_qr_code(qr_path)
                            self.logger.info("📤 QR code sent to Telegram bot successfully")
                        except Exception as e:
                            self.logger.error(f"❌ Failed to send QR code to Telegram: {e}")
                
                self.logger.info("📱 Please scan the ASCII QR code above, the saved image, or check your Telegram bot")
                driver.save_screenshot("/app/temp/screenshot.png")
                self.logger.info("📸 Saved screenshot to /app/temp/screenshot.png")
                
                authenticated = await self._wait_for_authentication(driver, timeout=60)
                if authenticated:
                    self.logger.info("✅ QR code authentication successful!")
                    return True
                self.logger.warning("⏰ QR code authentication timed out")
            
            self.logger.error("❌ QR authentication failed after all attempts")
            return False
        except Exception as e:
            self.logger.error(f"❌ QR authentication error: {e}", exc_info=True)
            return False

    async def _authenticate_phone(self, driver) -> bool:
        """Authenticate using phone number"""
        self.logger.info("📞 Phone number authentication not implemented")
        return await self._authenticate_qr(driver)

    async def _wait_for_authentication(self, driver, timeout: int = 60) -> bool:
        """Wait for authentication to complete"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                chats = driver.find_elements(By.CSS_SELECTOR, "[data-testid='chat-list']")
                if chats:
                    return True
                qr_elements = driver.find_elements(By.CSS_SELECTOR, "[data-testid='qrcode']")
                if not qr_elements:
                    reload_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-testid='qr-reload']")
                    if reload_buttons:
                        self.logger.info("🔄 QR code expired, clicking reload...")
                        reload_buttons[0].click()
                        time.sleep(2)
                time.sleep(1)
            except Exception as e:
                self.logger.debug(f"Waiting error: {e}")
                time.sleep(1)
        return False

    async def _save_qr_code(self, qr_data: str) -> str:
        """Save QR code data as image"""
        try:
            temp_dir = Path("/app/temp")
            temp_dir.mkdir(exist_ok=True)
            qr_path = temp_dir / "qr.png"
            if qr_data.startswith("data:image/png;base64,"):
                base64_data = qr_data.split(",", 1)[1]
                with open(qr_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
            self.logger.debug(f"📱 Saved QR code to {qr_path}")
            return str(qr_path)
        except Exception as e:
            self.logger.error(f"❌ Failed to save QR code: {e}")
            return ""

    async def _save_session(self, driver):
        """Save session data"""
        try:
            cookies = driver.get_cookies()
            session_data = {
                'cookies': cookies,
                'timestamp': time.time(),
                'user_agent': self.config.whatsapp.user_agent
            }
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            session_file.parent.mkdir(exist_ok=True)
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            self.logger.info("💾 Session saved successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to save session: {e}")

    async def _load_session(self, driver):
        """Load existing session"""
        try:
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            if not session_file.exists():
                return False
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            if time.time() - session_data.get('timestamp', 0) > 86400:
                self.logger.info("📅 Session expired")
                return False
            driver.get("https://web.whatsapp.com")
            for cookie in session_data.get('cookies', []):
                driver.add_cookie(cookie)
            driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            self.logger.debug(f"Could not load session: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return self.authenticated

    async def logout(self, driver):
        """Logout and clear session"""
        try:
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            if session_file.exists():
                session_file.unlink()
            driver.delete_all_cookies()
            self.authenticated = False
            self.logger.info("🚪 Logged out successfully")
        except Exception as e:
            self.logger.error(f"❌ Logout error: {e}")
