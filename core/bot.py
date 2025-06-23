"""
WhatsApp UserBot with improved error handling and compatibility
"""

import asyncio
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)

try:
    from .telegram_bridge import TelegramBridge
except ImportError:
    TelegramBridge = None

try:
    from .auth import AuthenticationManager
except ImportError:
    AuthenticationManager = None

from .webdriver_manager import WebDriverManager


class WhatsAppUserBot:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.running = False
        self.telegram_bridge = TelegramBridge(config, logger) if TelegramBridge and hasattr(config, 'telegram') and config.telegram.enabled else None
        self.auth_manager = AuthenticationManager(config, logger, self.telegram_bridge) if AuthenticationManager else None
        self.webdriver_manager = WebDriverManager(config, logger)
        self.message_queue = asyncio.Queue()
        self.processed_messages = set()
        self.stats = {
            'start_time': time.time(),
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0
        }
        self.selectors = {
            'qr_code': '[data-testid="qrcode"]',
            'chat_list': '[data-testid="chat-list"]',
            'message_input': '[data-testid="conversation-compose-box-input"]',
            'messages': '[data-testid="msg-container"]'
        }
        self.logger.info("🤖 WhatsAppUserBot initialized")

    async def initialize(self):
        """Initialize bot components"""
        self.logger.info("🔧 Initializing bot components...")
        try:
            os.makedirs("./temp", exist_ok=True)
            os.makedirs("./sessions", exist_ok=True)
            if self.telegram_bridge:
                self.logger.debug("📡 Initializing Telegram bridge")
                await self.telegram_bridge.initialize()
            self.logger.info("✅ Components initialized")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize components: {e}")

    async def start(self):
        """Start the WhatsApp bot"""
        self.logger.info("🚀 Starting WhatsApp UserBot...")
        try:
            self.driver = await self.webdriver_manager.setup_driver()
            if not self.driver:
                raise Exception("Failed to setup WebDriver")
            self.driver.implicitly_wait(10)
            self.driver.set_page_load_timeout(30)
            if not await self._authenticate():
                raise Exception("Authentication failed")
            self.running = True
            tasks = [
                asyncio.create_task(self._message_processor()),
                asyncio.create_task(self._monitor_messages())
            ]
            if self.telegram_bridge:
                tasks.append(asyncio.create_task(self.telegram_bridge.start()))
            self.logger.info("🚀 Bot started successfully")
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            await self.shutdown()

    async def _authenticate(self):
        """Authenticate with WhatsApp Web"""
        self.logger.info("🔐 Authenticating with WhatsApp Web...")
        try:
            if self.auth_manager:
                return await self.auth_manager.authenticate(self.driver)
            raise Exception("AuthenticationManager not initialized")
        except Exception as e:
            self.logger.error(f"❌ Authentication failed: {e}")
            return False

    async def _monitor_messages(self):
        """Monitor messages"""
        self.logger.info("👂 Starting message monitoring...")
        while self.running:
            try:
                messages = self.driver.find_elements(By.CSS_SELECTOR, self.selectors['messages'])
                for message in messages[-5:]:
                    message_id = message.get_attribute("data-id") or str(hash(message.get_attribute("outerHTML")))
                    if message_id not in self.processed_messages:
                        message_data = await self._extract_message_data(message)
                        if message_data:
                            await self.message_queue.put(message_data)
                            self.processed_messages.add(message_id)
                await asyncio.sleep(2)
            except Exception as e:
                self.logger.error(f"❌ Error monitoring messages: {e}")
                await asyncio.sleep(10)

    async def _extract_message_data(self, message_element):
        """Extract message data"""
        try:
            text_element = message_element.find_element(By.CSS_SELECTOR, '.selectable-text')
            message_text = text_element.text.strip()
            is_outgoing = 'message-out' in message_element.get_attribute('class')
            return {
                'id': message_element.get_attribute("data-id"),
                'text': message_text,
                'sender': "You" if is_outgoing else "Contact",
                'timestamp': time.time(),
                'is_outgoing': is_outgoing,
                'chat': await self._get_current_chat()
            }
        except Exception as e:
            self.logger.debug(f"Could not extract message data: {e}")
            return None

    async def _get_current_chat(self):
        """Get current chat name"""
        try:
            header = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="conversation-info-header-chat-title"]')
            return header.text.strip()
        except:
            return "Unknown Chat"

    async def _message_processor(self):
        """Process messages from queue"""
        while self.running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                self.stats['messages_received'] += 1
                if self.telegram_bridge:
                    await self.telegram_bridge.forward_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"❌ Error processing message: {e}")
                self.stats['errors'] += 1

    async def send_message(self, chat: str, message: str):
        """Send message"""
        try:
            search_box = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list-search"]')
            search_box.click()
            search_box.clear()
            search_box.send_keys(chat)
            await asyncio.sleep(2)
            chat_element = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list"] > div')
            chat_element.click()
            await asyncio.sleep(1)
            input_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="conversation-compose-box-input"]'))
            )
            input_box.click()
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)
            self.stats['messages_sent'] += 1
            self.logger.info("✅ Message sent")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to send message: {e}")
            return False

    async def shutdown(self):
        """Shutdown bot"""
        self.logger.info("🛑 Shutting down bot...")
        self.running = False
        if self.telegram_bridge:
            await self.telegram_bridge.shutdown()
        if self.webdriver_manager:
            self.webdriver_manager.cleanup()
        self.logger.info("✅ Bot shutdown complete")
