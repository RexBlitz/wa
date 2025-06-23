"""
Authentication manager for WhatsApp UserBot
Handles login, session management, and authentication methods
"""

import time
import json
import qrcode
from pathlib import Path
from typing import Dict, Any, Optional


class AuthenticationManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.session_data = {}
        self.authenticated = False

    async def authenticate(self, driver) -> bool:
        """Main authentication method"""
        self.logger.info("🔐 Starting authentication process...")
        
        try:
            # Check if already authenticated
            if await self._check_existing_session(driver):
                self.authenticated = True
                return True
            
            # Perform authentication based on method
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

    async def _check_existing_session(self, driver) -> bool:
        """Check if there's an existing valid session"""
        try:
            # Navigate to WhatsApp Web
            driver.get("https://web.whatsapp.com")
            
            # Wait a bit for page to load
            time.sleep(3)
            
            # Check if we're already logged in
            # Look for the main chat interface
            chats = driver.find_elements("css selector", "[data-testid='chat-list']")
            if chats:
                self.logger.info("✅ Found existing valid session")
                return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"No existing session found: {e}")
            return False

    async def _authenticate_qr(self, driver) -> bool:
        """Authenticate using QR code"""
        self.logger.info("📱 Authenticating with QR code...")
        
        try:
            max_attempts = 3
            
            for attempt in range(max_attempts):
                self.logger.info(f"🔄 QR authentication attempt {attempt + 1}/{max_attempts}")
                
                # Look for QR code
                qr_elements = driver.find_elements("css selector", "canvas")
                
                if not qr_elements:
                    self.logger.warning("⚠️ No QR code found, retrying...")
                    time.sleep(5)
                    driver.refresh()
                    time.sleep(3)
                    continue
                
                # Get QR code data
                qr_element = qr_elements[0]
                qr_data = driver.execute_script("""
                    var canvas = arguments[0];
                    return canvas.toDataURL();
                """, qr_element)
                
                # Save QR code as image
                qr_path = await self._save_qr_code(qr_data)
                
                self.logger.info(f"📱 QR Code generated: {qr_path}")
                self.logger.info("📱 Please scan the QR code with your WhatsApp mobile app")
                
                # Wait for authentication (up to 60 seconds)
                authenticated = await self._wait_for_authentication(driver, timeout=60)
                
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
                # Check for main chat interface
                chats = driver.find_elements("css selector", "[data-testid='chat-list']")
                if chats:
                    return True
                
                # Check if QR code expired and needs refresh
                qr_elements = driver.find_elements("css selector", "canvas")
                if not qr_elements:
                    # QR might have disappeared, check for reload button
                    reload_buttons = driver.find_elements("css selector", "[data-testid='qr-reload']")
                    if reload_buttons:
                        self.logger.info("🔄 QR code expired, clicking reload...")
                        reload_buttons[0].click()
                        time.sleep(2)
                
                time.sleep(2)
                
            except Exception as e:
                self.logger.debug(f"Waiting for auth: {e}")
                time.sleep(2)
        
        return False

    async def _save_qr_code(self, qr_data: str) -> str:
        """Save QR code data as image"""
        try:
            # Create temp directory
            temp_dir = Path("./temp")
            temp_dir.mkdir(exist_ok=True)
            
            # Save as file
            qr_path = temp_dir / "whatsapp_qr.png"
            
            # Extract base64 data
            if qr_data.startswith("data:image/png;base64,"):
                import base64
                base64_data = qr_data.split(",")[1]
                with open(qr_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
            
            return str(qr_path)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save QR code: {e}")
            return "QR code could not be saved"

    async def _save_session(self, driver):
        """Save session data for future use"""
        try:
            # Get session cookies and local storage
            cookies = driver.get_cookies()
            
            session_data = {
                'cookies': cookies,
                'timestamp': time.time(),
                'user_agent': self.config.whatsapp.user_agent
            }
            
            # Save to file
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            self.logger.info("💾 Session saved successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save session: {e}")

    async def _load_session(self, driver) -> bool:
        """Load existing session"""
        try:
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            
            if not session_file.exists():
                return False
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            # Check if session is not too old (24 hours)
            if time.time() - session_data.get('timestamp', 0) > 86400:
                self.logger.info("📅 Session expired, need fresh authentication")
                return False
            
            # Restore cookies
            driver.get("https://web.whatsapp.com")
            
            for cookie in session_data.get('cookies', []):
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    self.logger.debug(f"Could not add cookie: {e}")
            
            # Refresh to apply cookies
            driver.refresh()
            time.sleep(3)
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Could not load session: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.authenticated

    async def logout(self, driver):
        """Logout and clear session"""
        try:
            # Clear session file
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            if session_file.exists():
                session_file.unlink()
            
            # Clear browser data
            driver.delete_all_cookies()
            
            self.authenticated = False
            self.logger.info("🚪 Logged out successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Logout error: {e}")