"""
Authentication manager for WhatsApp UserBot
Handles login, session management, and authentication with improved popup handling
"""

import time
import json
import base64
from pathlib import Path
from typing import Dict, Any, Optional
import qrcode
import re
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException, InvalidSelectorException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains


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
            # Attempt to load existing session
            if await self._load_session(driver):
                self.logger.info("✅ Loaded valid session")
                self.authenticated = True
                return True

            # Clear browser cookies
            driver.delete_all_cookies()
            self.logger.info("🍪 Cleared browser cookies")

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
            for attempt in range(max_attempts):
                self.logger.info(f"🔄 QR authentication attempt {attempt + 1}/{max_attempts}")
                driver.get("https://web.whatsapp.com")
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
                )
                time.sleep(3)  # Buffer for page stability

                # Look for QR code with multiple selectors
                selectors = [
                    '[data-testid="qrcode"]',
                    'canvas[aria-label="Scan me!"]',
                    'canvas',
                    'div[data-testid="qr"] canvas'
                ]
                qr_element = None
                for selector in selectors:
                    try:
                        qr_element = driver.find_element(By.CSS_SELECTOR, selector)
                        self.logger.debug(f"Found QR element with selector: {selector}")
                        break
                    except NoSuchElementException:
                        continue

                if not qr_element:
                    self.logger.warning("⚠️ No QR code element found, refreshing...")
                    driver.refresh()
                    time.sleep(3)
                    continue

                # Get QR code data
                qr_data_ref = qr_element.get_attribute("data-ref")
                qr_data_url = None
                if qr_element.tag_name == 'canvas':
                    try:
                        qr_data_url = driver.execute_script(
                            "return arguments[0].toDataURL();", qr_element
                        )
                    except Exception as e:
                        self.logger.debug(f"Failed to get canvas data URL: {e}")

                qr_data_to_encode = qr_data_ref if qr_data_ref else qr_data_url
                if not qr_data_to_encode:
                    self.logger.warning("⚠️ No QR code data retrieved, refreshing...")
                    driver.refresh()
                    time.sleep(3)
                    continue

                self.logger.info(f"📱 QR code data retrieved (length: {len(qr_data_to_encode)})")

                # Save QR code as image
                qr_path = await self._save_qr_code(qr_data_to_encode, qr_data_ref is not None)
                if "could not be saved" in qr_path:
                    self.logger.warning("⚠️ QR code not saved, retrying...")
                    continue
                self.logger.info(f"📱 QR Code saved to: {qr_path}")

                # Generate ASCII QR code for reference
                try:
                    qr_ascii = qrcode.QRCode(
                        version=1,
                        box_size=1,
                        border=0,
                        error_correction=qrcode.constants.ERROR_CORRECT_L
                    )
                    qr_ascii.add_data(qr_data_to_encode[:100])
                    qr_ascii.make(fit=True)
                    self.logger.info("📱 Compact ASCII QR Code (reference only):")
                    qr_ascii.print_ascii(invert=True)
                except Exception as e:
                    self.logger.debug(f"Failed to generate ASCII QR code: {e}")

                # Send QR code to Telegram
                if self.telegram_bridge:
                    try:
                        if await self.telegram_bridge.forward_qr_code(qr_path):
                            self.logger.info("📤 QR code sent to Telegram")
                        else:
                            self.logger.error("❌ Failed to send QR code to Telegram")
                    except Exception as e:
                        self.logger.error(f"❌ Error sending QR code to Telegram: {e}")

                self.logger.info("📱 Please scan the QR code with your WhatsApp mobile app")

                # Save debug screenshot
                screenshot_path = Path(f"/app/temp/qr_screenshot_{int(time.time())}.png")
                driver.save_screenshot(str(screenshot_path))
                self.logger.info(f"📸 Saved screenshot to {screenshot_path}")

                # Wait for authentication
                if await self._wait_for_authentication(driver, timeout=120):
                    self.logger.info("✅ QR code authentication successful")
                    return True
                else:
                    self.logger.warning("⏰ QR code authentication timed out")

            self.logger.error("❌ QR authentication failed after all attempts")
            return False

        except Exception as e:
            self.logger.error(f"❌ QR authentication error: {e}")
            return False

    async def _authenticate_phone(self, driver) -> bool:
        """Authenticate using phone number (placeholder)"""
        self.logger.info("📞 Phone authentication not implemented, falling back to QR")
        return await self._authenticate_qr(driver)

    async def _wait_for_authentication(self, driver, timeout: int = 120) -> bool:
        """Wait for authentication to complete with improved popup handling"""
        start_time = time.time()
        self.logger.info(f"⏳ Waiting for authentication (timeout: {timeout} seconds)")

        login_indicators = [
            '[data-testid="chat-list"]',
            '[data-testid="chat-list-search"]',
            '[data-testid="wa-web-main-container"]',
            '[data-testid="conversation-panel"]',
            'div[role="main"]',
            '[data-testid="intro-title"]',
            '[data-testid="chat-panel"]',
            'div[role="complementary"]',
            '[data-testid="app-container"]'
        ]
        loading_indicators = [
            '[data-testid="loading-spinner"]',
            'div[role="progressbar"]',
            '[data-testid="wa-connection-error"]',
            'div.loading'
        ]
        # Updated popup selector: Use XPath to find button with "Continue" text
        popup_selector = "//button[contains(text(), 'Continue') or contains(@data-testid, 'continue')]"

        while time.time() - start_time < timeout:
            try:
                # Check page readiness
                page_state = driver.execute_script("return document.readyState;")
                self.logger.debug(f"Page readyState: {page_state}")
                if page_state != "complete":
                    self.logger.debug("Page not fully loaded, waiting...")
                    time.sleep(2)
                    continue

                # Check for and dismiss the Continue popup using XPath
                try:
                    continue_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, popup_selector))
                    )
                    self.logger.info("📣 Found Continue popup, clicking...")
                    ActionChains(driver).move_to_element(continue_button).click().perform()
                    time.sleep(2)  # Wait for page to update after clicking
                    screenshot_path = Path(f"/app/temp/popup_dismissed_{int(time.time())}.png")
                    driver.save_screenshot(str(screenshot_path))
                    self.logger.info(f"📸 Saved popup dismissal screenshot to {screenshot_path}")
                    if self.telegram_bridge:
                        await self.telegram_bridge.forward_qr_code(str(screenshot_path))
                        self.logger.info("📤 Sent popup dismissal screenshot to Telegram")
                except (TimeoutException, NoSuchElementException, InvalidSelectorException) as e:
                    self.logger.debug(f"No Continue popup found or selector invalid: {e}")

                # Check for loading/error states
                for selector in loading_indicators:
                    try:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        self.logger.debug(f"Found {selector}: {element.get_attribute('outerHTML')[:100]}")
                        time.sleep(2)
                        break
                    except NoSuchElementException:
                        pass

                # Check for login indicators
                for selector in login_indicators:
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                        self.logger.info(f"✅ Found {selector}. Authentication successful")
                        screenshot_path = Path(f"/app/temp/auth_success_{int(time.time())}.png")
                        driver.save_screenshot(str(screenshot_path))
                        self.logger.info(f"📸 Saved success screenshot to {screenshot_path}")
                        if self.telegram_bridge:
                            await self.telegram_bridge.forward_qr_code(str(screenshot_path))
                            self.logger.info("📤 Sent success screenshot to Telegram")
                        return True
                    except TimeoutException:
                        self.logger.debug(f"Selector {selector} not found")

                # Log visible elements for debugging
                visible_elements = driver.execute_script(
                    "return Array.from(document.querySelectorAll('*')).filter(e => e.offsetHeight > 0 && window.getComputedStyle(e).display !== 'none').map(e => ({tag: e.tagName, id: e.id, class: e.className, testid: e.getAttribute('data-testid')}));"
                )
                self.logger.debug(f"Visible elements (top 5): {visible_elements[:5]}")

                # Check for QR code or reload
                qr_elements = driver.find_elements(By.CSS_SELECTOR, "canvas")
                reload_buttons = driver.find_elements(By.CSS_SELECTOR, "[data-testid='qr-reload']")

                if qr_elements:
                    self.logger.debug("QR code canvas still present")
                elif reload_buttons:
                    self.logger.info("🔄 QR code expired, clicking reload")
                    try:
                        reload_buttons[0].click()
                        time.sleep(2)
                        screenshot_path = Path(f"/app/temp/qr_reload_{int(time.time())}.png")
                        driver.save_screenshot(str(screenshot_path))
                        self.logger.info(f"📸 Saved QR reload screenshot to {screenshot_path}")
                        if self.telegram_bridge:
                            await self.telegram_bridge.forward_qr_code(str(screenshot_path))
                            self.logger.info("📤 Sent new QR screenshot to Telegram")
                    except Exception as e:
                        self.logger.warning(f"Failed to click reload button: {e}")
                else:
                    self.logger.debug("No QR canvas or reload button")

                # Save debug artifacts
                screenshot_path = Path(f"/app/temp/auth_debug_{int(time.time())}.png")
                driver.save_screenshot(str(screenshot_path))
                self.logger.info(f"📸 Saved debug screenshot to {screenshot_path}")
                if self.telegram_bridge:
                    await self.telegram_bridge.forward_qr_code(str(screenshot_path))
                    self.logger.info("📤 Sent debug screenshot to Telegram")

                with open(f"/app/temp/auth_page_source_{int(time.time())}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                self.logger.info("📄 Saved page source for debugging")

                time.sleep(1)

            except Exception as e:
                self.logger.error(f"Error during authentication wait: {e}")
                time.sleep(1)

        self.logger.error("❌ Authentication timed out. Check /app/temp for debug artifacts")
        return False

    async def _save_qr_code(self, qr_data: str, is_data_ref: bool) -> str:
        """Save QR code data as image"""
        try:
            temp_dir = Path("./temp")
            temp_dir.mkdir(exist_ok=True)
            qr_path = temp_dir / "whatsapp_qr.png"

            if is_data_ref:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4
                )
                qr.add_data(qr_data)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                img.save(qr_path)
            elif qr_data.startswith("data:image/png;base64,"):
                base64_data = qr_data.split(",")[1]
                with open(qr_path, "wb") as f:
                    f.write(base64.b64decode(base64_data))
            else:
                self.logger.error(f"❌ Unknown QR data format: {qr_data[:50]}...")
                return "QR code could not be saved"

            return str(qr_path)

        except Exception as e:
            self.logger.error(f"❌ Failed to save QR code: {e}")
            return "QR code could not be saved"

    async def _save_session(self, driver):
        """Save session data"""
        try:
            cookies = driver.get_cookies()
            session_data = {
                'cookies': cookies,
                'timestamp': time.time()
            }
            session_file = Path(self.config.whatsapp.session_dir) / "session.json"
            session_file.parent.mkdir(parents=True, exist_ok=True)
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
                self.logger.info("No session file found")
                return False

            with open(session_file, 'r') as f:
                session_data = json.load(f)

            if time.time() - session_data.get('timestamp', 0) > self.config.bot.session_timeout:
                self.logger.info(f"📅 Session expired (older than {self.config.bot.session_timeout} seconds)")
                return False

            driver.get("https://web.whatsapp.com")
            for cookie in session_data.get('cookies', []):
                if 'expiry' in cookie and (cookie['expiry'] is None or not isinstance(cookie['expiry'], (int, float))):
                    cookie.pop('expiry')
                elif 'expiry' in cookie and isinstance(cookie['expiry'], float):
                    cookie['expiry'] = int(cookie['expiry'])
                try:
                    driver.add_cookie(cookie)
                except Exception as e:
                    self.logger.debug(f"Could not load cookie {cookie.get('name')}: {e}")

            driver.refresh()
            time.sleep(3)

            try:
                WebDriverWait(driver, 60).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='chat-list']"))
                )
                self.logger.info("✅ Session loaded and valid")
                self.authenticated = True
                return True
            except TimeoutException:
                self.logger.info("❌ Session loaded but chat list not found")
                return False

        except Exception as e:
            self.logger.error(f"❌ Error loading session: {e}")
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
                self.logger.info("🗑️ Session file deleted")
            driver.delete_all_cookies()
            self.logger.info("🍪 All browser cookies cleared")
            self.authenticated = False
            self.logger.info("🚪 Logged out successfully")
        except Exception as e:
            self.logger.error(f"❌ Logout error: {e}")
