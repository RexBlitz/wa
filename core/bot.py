"""
Fixed WhatsApp UserBot class with improved error handling and compatibility
"""

import asyncio
import time
import os
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    WebDriverException,
    SessionNotCreatedException
)

# Import your other modules
try:
    from .telegram_bridge import TelegramBridge
except ImportError:
    TelegramBridge = None
    
try:
    from .database import DatabaseManager
except ImportError:
    DatabaseManager = None
    
try:
    from .module_manager import ModuleManager
except ImportError:
    ModuleManager = None
    
try:
    from .message_handler import MessageHandler
except ImportError:
    MessageHandler = None
    
try:
    from .auth import AuthenticationManager
except ImportError:
    AuthenticationManager = None

from .webdriver_manager import WebDriverManager

# Simple QR code generator if utils module doesn't exist
def generate_qr_code(data, path):
    """Simple QR code generation placeholder"""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        return path
    except ImportError:
        print(f"QR Code data available (install 'qrcode' library to save): {data[:50]}...")
        return None


class WhatsAppUserBot:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.running = False
        
        # Initialize components with error handling
        self.db_manager = DatabaseManager(config, logger) if DatabaseManager else None
        self.telegram_bridge = TelegramBridge(config, logger) if TelegramBridge and hasattr(config, 'telegram') and config.telegram.enabled else None
        self.module_manager = ModuleManager(config, logger) if ModuleManager else None
        self.message_handler = MessageHandler(config, logger) if MessageHandler else None
        self.auth_manager = AuthenticationManager(config, logger, self.telegram_bridge) if AuthenticationManager else None
        self.webdriver_manager = WebDriverManager(config, logger)
        
        # Message queue and processing
        self.message_queue = asyncio.Queue()
        self.processed_messages = set()
        self.last_message_time = 0
        
        # Bot statistics
        self.stats = {
            'start_time': time.time(),
            'messages_sent': 0,
            'messages_received': 0,
            'commands_executed': 0,
            'errors': 0
        }
        
        # WhatsApp Web selectors (updated for 2025)
        self.selectors = {
            'qr_code': '[data-testid="qrcode"], canvas[aria-label="Scan me!"], canvas',
            'chat_list': '[data-testid="chat-list"], [role="grid"]',
            'search_box': '[data-testid="chat-list-search"], [placeholder*="Search"]',
            'message_input': '[data-testid="conversation-compose-box-input"], [contenteditable="true"][data-tab="10"]',
            'send_button': '[data-testid="send"], [data-icon="send"]',
            'messages': '[data-testid="msg-container"], [role="row"]',
            'message_text': '.selectable-text, [data-testid="conversation-text"]'
        }

    # Rest of the bot.py remains unchanged
    async def initialize(self):
        """Initialize all bot components with better error handling"""
        self.logger.info("🔧 Initializing bot components...")
        
        try:
            os.makedirs("./temp", exist_ok=True)
            os.makedirs("./sessions", exist_ok=True)
            
            if self.db_manager:
                await self.db_manager.initialize()
            
            if self.telegram_bridge:
                await self.telegram_bridge.initialize()
            
            if self.module_manager:
                await self.module_manager.load_all_modules()
            
            if self.message_handler:
                await self.message_handler.initialize(self)
            
            self.logger.info("✅ All available components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize components: {e}")
            self.logger.warning("⚠️ Continuing with limited functionality")

    async def start(self):
        """Start the WhatsApp bot with improved error handling"""
        try:
            self.logger.info("🚀 Starting WhatsApp UserBot...")
            
            self.driver = await self.webdriver_manager.setup_driver()
            
            if not self.driver:
                raise Exception("Failed to setup WebDriver with all available methods")
            
            driver_info = self.webdriver_manager.get_driver_info()
            self.logger.info(f"🌐 WebDriver Info: {driver_info}")
            
            implicit_wait = getattr(self.config.whatsapp, 'implicit_wait', 10)
            page_load_timeout = getattr(self.config.whatsapp, 'page_load_timeout', 30)
            
            self.driver.implicitly_wait(implicit_wait)
            self.driver.set_page_load_timeout(page_load_timeout)
            
            if not await self._authenticate():
                raise Exception("Authentication failed")
            
            self.running = True
            
            tasks = []
            tasks.append(asyncio.create_task(self._message_processor()))
            tasks.append(asyncio.create_task(self._monitor_messages()))
            
            if self.telegram_bridge:
                tasks.append(asyncio.create_task(self.telegram_bridge.start()))
            
            self.logger.info("🚀 Bot started successfully!")
            
            try:
                while self.running:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                self.logger.info("🛑 Received shutdown signal")
                await self.shutdown()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            await self.shutdown()
            raise

    async def _authenticate(self):
        """Authenticate with WhatsApp Web using AuthenticationManager"""
        self.logger.info("🔐 Authenticating with WhatsApp Web...")
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.logger.info(f"📱 Loading WhatsApp Web (attempt {retry_count + 1}/{max_retries})...")
                if self.auth_manager:
                    if await self.auth_manager.authenticate(self.driver):
                        self.logger.info("✅ Authentication successful!")
                        return True
                else:
                    raise Exception("AuthenticationManager not initialized")
                
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.warning(f"⚠️ Authentication attempt {retry_count} failed, retrying...")
                    await asyncio.sleep(10)
            
            except Exception as e:
                self.logger.error(f"❌ Authentication attempt {retry_count + 1} failed: {e}")
                retry_count += 1
                if retry_count < max_retries:
                    await asyncio.sleep(10)
        
        self.logger.error("❌ All authentication attempts failed")
        return False

    async def _monitor_messages(self):
        """Enhanced message monitoring with better selectors"""
        self.logger.info("👂 Starting message monitoring...")
        
        while self.running:
            try:
                await asyncio.sleep(2)
                
                messages = []
                for selector in ['[data-testid="msg-container"]', '[role="row"]', '.message-in, .message-out']:
                    try:
                        elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if elements:
                            messages = elements
                            break
                    except:
                        continue
                
                if not messages:
                    continue
                
                for message in messages[-5:]:
                    try:
                        message_id = message.get_attribute("data-id") or str(hash(message.get_attribute("outerHTML")))
                        
                        if message_id and message_id not in self.processed_messages:
                            message_data = await self._extract_message_data(message)
                            
                            if message_data:
                                await self.message_queue.put(message_data)
                                self.processed_messages.add(message_id)
                                
                                if len(self.processed_messages) > 1000:
                                    self.processed_messages = set(list(self.processed_messages)[-500:])
                    except Exception as e:
                        self.logger.debug(f"Error processing message: {e}")
                        continue
                
            except Exception as e:
                self.logger.error(f"❌ Error monitoring messages: {e}")
                
                try:
                    self.driver.current_url
                except:
                    self.logger.info("🔄 WebDriver session lost, attempting recovery...")
                    if await self.webdriver_manager.restart_driver():
                        self.driver = self.webdriver_manager.driver
                        await self._authenticate()
                
                await asyncio.sleep(10)

    async def _extract_message_data(self, message_element):
        """Enhanced message data extraction"""
        try:
            message_text = ""
            text_selectors = [
                '.selectable-text',
                '[data-testid="conversation-text"]',
                '.copyable-text',
                'span'
            ]
            
            for selector in text_selectors:
                try:
                    text_element = message_element.find_element(By.CSS_SELECTOR, selector)
                    if text_element and text_element.text.strip():
                        message_text = text_element.text.strip()
                        break
                except:
                    continue
            
            if not message_text:
                return None
            
            is_outgoing = 'message-out' in message_element.get_attribute('class') or False
            sender = "You" if is_outgoing else "Contact"
            timestamp = time.time()
            
            return {
                'id': message_element.get_attribute("data-id") or str(hash(message_text)),
                'text': message_text,
                'sender': sender,
                'timestamp': timestamp,
                'is_outgoing': is_outgoing,
                'chat': await self._get_current_chat()
            }
            
        except Exception as e:
            self.logger.debug(f"Could not extract message data: {e}")
            return None

    async def _get_current_chat(self):
        """Get current active chat information"""
        try:
            header_selectors = [
                '[data-testid="conversation-info-header-chat-title"]',
                'header span[title]',
                '.chat-title'
            ]
            
            for selector in header_selectors:
                try:
                    element = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if element and element.text.strip():
                        return element.text.strip()
                except:
                    continue
            
            return "Unknown Chat"
        except:
            return "Unknown Chat"

    async def _message_processor(self):
        """Process messages from the queue with error handling"""
        while self.running:
            try:
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                
                if self.message_handler:
                    await self.message_handler.handle_message(message)
                else:
                    self.logger.info(f"📨 Received: {message['text'][:100]}...")
                
                self.stats['messages_received'] += 1
                
                if self.telegram_bridge:
                    await self.telegram_bridge.forward_message(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"❌ Error processing message: {e}")
                self.stats['errors'] += 1

    async def send_message(self, chat: str, message: str):
        """Enhanced message sending with better selectors"""
        try:
            self.logger.info(f"📤 Sending message to {chat}: {message[:50]}...")
            
            if not await self._select_chat(chat):
                self.logger.error(f"❌ Could not find chat: {chat}")
                return False
            
            input_box = None
            input_selectors = [
                '[data-testid="conversation-compose-box-input"]',
                '[contenteditable="true"][data-tab="10"]',
                '.selectable-text[contenteditable="true"]',
                'div[contenteditable="true"]'
            ]
            
            for selector in input_selectors:
                try:
                    input_box = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue
            
            if not input_box:
                self.logger.error("❌ Could not find message input box")
                return False
            
            input_box.click()
            await asyncio.sleep(0.5)
            input_box.send_keys(message)
            await asyncio.sleep(0.5)
            
            send_selectors = [
                '[data-testid="send"]',
                '[data-icon="send"]',
                'button[data-testid="send"]'
            ]
            
            for selector in send_selectors:
                try:
                    send_button = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if send_button.is_enabled():
                        send_button.click()
                        break
                except:
                    continue
            else:
                input_box.send_keys(Keys.ENTER)
            
            await asyncio.sleep(1)
            
            self.stats['messages_sent'] += 1
            
            self.logger.info(f"✅ Message sent successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send message: {e}")
            return False

    async def _select_chat(self, chat_name: str):
        """Select a chat by name"""
        try:
            search_selectors = [
                '[data-testid="chat-list-search"]',
                '[placeholder*="Search"]',
                'input[title="Search input textbox"]'
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.driver.find_element(By.CSS_SELECTOR, selector)
                    break
                except:
                    continue
            
            if search_box:
                search_box.click()
                search_box.clear()
                search_box.send_keys(chat_name)
                await asyncio.sleep(2)
                
                chat_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-testid="chat-list"] > div')
                if chat_elements:
                    chat_elements[0].click()
                    await asyncio.sleep(1)
                    return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Error selecting chat: {e}")
            return False

    async def get_stats(self):
        """Get bot statistics"""
        current_time = time.time()
        uptime = current_time - self.stats['start_time']
        
        driver_info = self.webdriver_manager.get_driver_info()
        
        return {
            **self.stats,
            'uptime': uptime,
            'uptime_formatted': f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
            'driver_info': driver_info,
            'queue_size': self.message_queue.qsize(),
            'processed_messages_count': len(self.processed_messages)
        }

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        self.logger.info("🛑 Shutting down bot...")
        
        self.running = False
        
        await asyncio.sleep(2)
        
        if self.webdriver_manager:
            self.webdriver_manager.cleanup()
        
        if self.telegram_bridge:
            try:
                await self.telegram_bridge.shutdown()
            except:
                pass
        
        if self.db_manager:
            try:
                await self.db_manager.close()
            except:
                pass
        
        self.logger.info("✅ Bot shutdown complete")
