"""
Authentication manager for WhatsApp UserBot
Handles login, session management, and authentication methods
"""

import time
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional
import qrcode # Import qrcode library

class AuthenticationManager:
    def __init__(self, config, logger, telegram_bridge=None):
        self.config = config
        self.logger = logger
        self.session_data = {}
        self.authenticated = False
        self.telegram_bridge = telegram_bridge

    async def authenticate(self, driver) -> bool:
        """Main authentication method"""
        self.logger.info("🔐 Starting authentication process...")
        
        try:
            # Force QR code authentication
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
            self.logger.error(f"❌ Authentication failed: {e}")
            return False

    async def _authenticate_qr(self, driver) -> bool:
        """Authenticate using QR code"""
        self.logger.info("📱 Authenticating with QR code...")
        
        try:
            max_attempts = 3
            driver.get("https://web.whatsapp.com")
            time.sleep(5)  # Wait for page to load
            
            for attempt in range(max_attempts):
                self.logger.info(f"🔄 QR authentication attempt {attempt + 1}/{max_attempts}")
                
                # Look for QR code with multiple selectors
                selectors = [
                    '[data-testid="qrcode"]',
                    'canvas[aria-label="Scan me!"]',
                    'canvas',
                    'div[data-testid="qr"] canvas'
                ]
                qr_element = None
                for selector in selectors:
                    self.logger.debug(f"Trying QR selector: {selector}")
                    qr_elements = driver.find_elements("css selector", selector)
                    self.logger.debug(f"Found {len(qr_elements)} elements with selector {selector}")
                    if qr_elements:
                        qr_element = qr_elements[0]
                        break
                
                if not qr_element:
                    self.logger.warning("⚠️ No QR code element found, retrying...")
                    driver.refresh()
                    time.sleep(3)
                    continue
                
                # Get QR code data (prioritize data-ref, then toDataURL)
                qr_data_ref = qr_element.get_attribute("data-ref")
                qr_data_url = None
                try:
                    qr_data_url = driver.execute_script("""
                        var canvas = arguments[0];
                        if (canvas && typeof canvas.toDataURL === 'function') {
                            return canvas.toDataURL();
                        }
                        return null;
                    """, qr_element)
                except Exception as e:
                    self.logger.debug(f"Failed to get QR data from canvas.toDataURL(): {e}")

                qr_data_to_encode = qr_data_ref if qr_data_ref else qr_data_url

                if not qr_data_to_encode:
                    self.logger.warning("⚠️ No QR code data retrieved (data-ref or toDataURL), retrying...")
                    driver.refresh()
                    time.sleep(3)
                    continue
                
                # Log QR code data type and length
                self.logger.info(f"📱 QR code data retrieved. Type: {'data-ref' if qr_data_ref else 'toDataURL'}, Length: {len(qr_data_to_encode)}")

                # Save QR code as image
                qr_path = await self._save_qr_code(qr_data_to_encode, qr_data_ref is not None)
                self.logger.info(f"📱 QR Code saved to: {qr_path}")
                
                # Generate and log compact ASCII QR code (for terminal viewing, not scanning)
                try:
                    # Use a short portion for ASCII to keep it compact
                    ascii_data = qr_data_ref if qr_data_ref else qr_data_to_encode[:100]
                    qr_ascii = qrcode.QRCode(
                        version=1,
                        box_size=1,
                        border=0,
                        error_correction=qrcode.constants.ERROR_CORRECT_L
                    )
                    qr_ascii.add_data(ascii_data)
                    qr_ascii.make(fit=True)
                    self.logger.info("📱 Compact ASCII QR Code (for reference, may not be scannable):")
                    qr_ascii.print_ascii(invert=True)
                except Exception as e:
                    self.logger.error(f"❌ Failed to generate ASCII QR code: {e}")

                # Send QR code image to Telegram via TelegramBridge
                if self.telegram_bridge and qr_path != "QR code could not be saved":
                    try:
                        await self.telegram_bridge.forward_qr_code(qr_path)
                        self.logger.info("📤 QR code image sent to Telegram bot successfully")
                    except Exception as e:
                        self.logger.error(f"❌ Failed to send QR code image to Telegram: {e}")
                
                self.logger.info("📱 Please scan the generated QR code image (either from file or Telegram) with your WhatsApp mobile app")
                
                # Save screenshot for debugging
                screenshot_path = Path("/app/temp/screenshot.png")
                driver.save_screenshot(str(screenshot_path))
                self.logger.info(f"📸 Saved screenshot to {screenshot_path}")
                
                # Wait for authentication
                authenticated = await self._wait_for_authentication(driver, timeout=90) # Increased timeout
                
                if authenticated:
                    self.logger.info("✅ QR code authentication successful!")
                    return True
                else:
                    self.logger.warning("⏰ QR code authentication timed out")
            
            self.logger.error("❌ QR authentication failed after all attempts")
            return False
            
        except Exception as e:
            self.logger.error(f"❌ QR authentication error: {e}")
            return False

    async def _authenticate_phone(self, driver) -> bool:
        """Authenticate using phone number"""
        self.logger.info("📞 Phone number authentication not fully implemented")
        self.logger.info("📞 Falling back to QR code authentication")
        return await self._authenticate_qr(driver)

    async def _wait_for_authentication(self, driver, timeout: int = 60) -> bool:
        """Wait for authentication to complete"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check for elements indicating successful login (e.g., chat list)
                chats = driver.find_elements("css selector", "[data-testid='chat-list']")
                if chats:
                    self.logger.info("✅ Chat list found, authentication likely successful.")
                    return True
                
                # Check for QR code expiration/reload
                qr_elements = driver.find_elements("css selector", "canvas")
                if not qr_elements:
                    # If canvas is gone, it might be authenticated or an error
                    self.logger.debug("QR canvas not found, checking for reload button or chat list.")
                    reload_buttons = driver.find_elements("css selector", "[data-testid='qr-reload']")
                    if reload_buttons:
                        self.logger.info("🔄 QR code expired, clicking reload...")
                        reload_buttons[0].click()
                        time.sleep(2) # Give some time for new QR to load
                
                time.sleep(1) # Short delay to avoid busy-waiting
                
            except Exception as e:
                self.logger.debug(f"Waiting for auth: {e}")
                time.sleep(1)
        
        return False

    async def _save_qr_code(self, qr_data: str, is_data_ref: bool) -> str:
        """Save QR code data as image"""
        try:
            temp_dir = Path("./temp")
            temp_dir.mkdir(exist_ok=True)
            
            qr_path = temp_dir / "whatsapp_qr.png"
            
            if is_data_ref:
                # If it's a data-ref string, use qrcode library to generate image
                self.logger.debug(f"Saving QR code from data-ref: {qr_data}")
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10, # Standard size for good scannability
                    border=4,
                )
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                img.save(qr_path)
            elif qr_data.startswith("data:image/png;base64,"):
                # If it's a base64 data URL, decode and save
                self.logger.debug("Saving QR code from base64 data URL.")
                base64_data = qr_data.split(",")[1]
                with open(qr_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
            else:
                self.logger.error(f"❌ Unknown QR data format: {qr_data[:50]}")
                return "QR code could not be saved due to unknown format"
            
            return str(qr_path)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save QR code: {e}")
            return "QR code could not be saved"

    async def _save_session(self, driver):
        """Save session data for future use"""
        try:
            cookies = driver.get_cookies()
            
            session_data = {
                'cookies': cookies,
                'timestamp': time.time(),
                'user_agent': self.config.whatsapp.user_agent
            }
            
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
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
            
            if time.time() - session_data.get('timestamp', 0) > 86400: # Session valid for 24 hours
                self.logger.info("📅 Session expired, need fresh authentication")
                return False
            
            driver.get("https://web.whatsapp.com")
            
            for cookie in session_data.get('cookies', []):
                # Ensure the cookie domain is correct for WhatsApp Web
                # Selenium might add cookies incorrectly if domain is not exact
                if 'domain' in cookie and 'whatsapp.com' in cookie['domain']:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as e:
                        self.logger.debug(f"Could not add cookie: {e}")
            
            driver.refresh()
            time.sleep(3)
            
            # Verify if session loaded successfully by checking for chat list
            if driver.find_elements("css selector", "[data-testid='chat-list']"):
                self.logger.info("✅ Session loaded and appears valid.")
                return True
            else:
                self.logger.info("❌ Session loaded but chat list not found, likely expired or invalid.")
                return False
            
        except Exception as e:
            self.logger.debug(f"Could not load session: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
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
