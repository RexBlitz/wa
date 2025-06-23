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

# Import your other modules (make sure these files exist)
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
        # If qrcode not available, just log the message
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
        self.auth_manager = AuthenticationManager(config, logger) if AuthenticationManager else None
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
        
        # WhatsApp Web selectors (updated for 2024)
        self.selectors = {
            'qr_code': 'canvas[aria-label="Scan me!"], canvas',
            'chat_list': '[data-testid="chat-list"], [role="grid"]',
            'search_box': '[data-testid="chat-list-search"], [placeholder*="Search"]',
            'message_input': '[data-testid="conversation-compose-box-input"], [contenteditable="true"][data-tab="10"]',
            'send_button': '[data-testid="send"], [data-icon="send"]',
            'messages': '[data-testid="msg-container"], [role="row"]',
            'message_text': '.selectable-text, [data-testid="conversation-text"]'
        }

    async def initialize(self):
        """Initialize all bot components with better error handling"""
        self.logger.info("🔧 Initializing bot components...")
        
        try:
            # Create necessary directories
            os.makedirs("./temp", exist_ok=True)
            os.makedirs("./sessions", exist_ok=True)
            
            # Initialize database if available
            if self.db_manager:
                await self.db_manager.initialize()
            
            # Initialize Telegram bridge if available
            if self.telegram_bridge:
                await self.telegram_bridge.initialize()
            
            # Load modules if available
            if self.module_manager:
                await self.module_manager.load_all_modules()
            
            # Initialize message handler if available
            if self.message_handler:
                await self.message_handler.initialize(self)
            
            self.logger.info("✅ All available components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize components: {e}")
            # Don't raise here, allow bot to continue with limited functionality
            self.logger.warning("⚠️ Continuing with limited functionality")

    async def start(self):
        """Start the WhatsApp bot with improved error handling"""
        try:
            self.logger.info("🚀 Starting WhatsApp UserBot...")
            
            # Setup WebDriver with enhanced compatibility
            self.driver = await self.webdriver_manager.setup_driver()
            
            if not self.driver:
                raise Exception("Failed to setup WebDriver with all available methods")
            
            # Log driver information
            driver_info = self.webdriver_manager.get_driver_info()
            self.logger.info(f"🌐 WebDriver Info: {driver_info}")
            
            # Set timeouts with fallback values
            implicit_wait = getattr(self.config.whatsapp, 'implicit_wait', 10)
            page_load_timeout = getattr(self.config.whatsapp, 'page_load_timeout', 30)
            
            self.driver.implicitly_wait(implicit_wait)
            self.driver.set_page_load_timeout(page_load_timeout)
            
            # Authenticate with WhatsApp
            if not await self._authenticate():
                raise Exception("Authentication failed")
            
            # Start message processing
            self.running = True
            
            # Create background tasks
            tasks = []
            tasks.append(asyncio.create_task(self._message_processor()))
            tasks.append(asyncio.create_task(self._monitor_messages()))
            
            # Start Telegram bridge if enabled
            if self.telegram_bridge:
                tasks.append(asyncio.create_task(self.telegram_bridge.start()))
            
            self.logger.info("🚀 Bot started successfully!")
            
            # Keep running until stopped
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
        """Enhanced authentication with WhatsApp Web"""
        self.logger.info("🔐 Authenticating with WhatsApp Web...")
        
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Navigate to WhatsApp Web
                self.logger.info(f"📱 Loading WhatsApp Web (attempt {retry_count + 1}/{max_retries})...")
                self.driver.get("https://web.whatsapp.com")
                
                # Wait for page to load
                await asyncio.sleep(5)
                
                # Check if already logged in
                if await self._is_logged_in():
                    self.logger.info("✅ Already authenticated!")
                    return True
                
                # Handle authentication based on method
                auth_method = getattr(self.config.whatsapp, 'auth_method', 'qr')
                
                if auth_method == "qr":
                    if await self._authenticate_with_qr():
                        return True
                elif auth_method == "phone":
                    if await self._authenticate_with_phone():
                        return True
                else:
                    raise ValueError(f"Unsupported auth method: {auth_method}")
                    
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

    async def _authenticate_with_qr(self):
        """Improved QR code authentication"""
        self.logger.info("📱 Waiting for QR code...")
        
        try:
            # Wait for QR code with multiple selectors
            qr_element = None
            for selector in ['canvas[aria-label="Scan me!"]', 'canvas', '[data-testid="qr-code"]']:
                try:
                    qr_element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except TimeoutException:
                    continue
            
            if not qr_element:
                self.logger.error("❌ QR code element not found")
                return False
            
            self.logger.info("📱 QR code found, processing...")
            
            # Try to get QR code data
            try:
                qr_data = self.driver.execute_script("""
                    var canvas = arguments[0];
                    return canvas.toDataURL();
                """, qr_element)
                
                # Generate and display QR code
                qr_path = generate_qr_code(qr_data, "./temp/qr_code.png")
                if qr_path:
                    self.logger.info(f"📱 QR Code saved to: {qr_path}")
                self.logger.info("📱 Scan the QR code with your WhatsApp mobile app")
                
            except Exception as e:
                self.logger.warning(f"⚠️ Could not extract QR code: {e}")
                self.logger.info("📱 Please scan the QR code displayed in the browser")
            
            # Wait for authentication with extended timeout
            self.logger.info("⏳ Waiting for QR code scan...")
            
            # Check multiple indicators of successful login
            success_selectors = [
                '[data-testid="chat-list"]',
                '[role="grid"]',
                '.two',  # Main WhatsApp interface
                '[data-testid="chats-list"]'
            ]
            
            for attempt in range(120):  # 2 minutes timeout
                for selector in success_selectors:
                    try:
                        if self.driver.find_elements(By.CSS_SELECTOR, selector):
                            self.logger.info("✅ QR Code authentication successful!")
                            return True
                    except:
                        continue
                
                await asyncio.sleep(1)
            
            self.logger.error("❌ QR authentication timeout")
            return False
            
        except TimeoutException:
            self.logger.error("❌ QR code authentication timed out")
            return False
        except Exception as e:
            self.logger.error(f"❌ QR authentication failed: {e}")
            return False

    async def _authenticate_with_phone(self):
        """Phone number authentication (placeholder)"""
        self.logger.warning("📞 Phone authentication not implemented, falling back to QR code")
        return await self._authenticate_with_qr()

    async def _is_logged_in(self):
        """Check if already logged in to WhatsApp Web"""
        try:
            await asyncio.sleep(3)
            
            # Check for various indicators of being logged in
            login_indicators = [
                '[data-testid="chat-list"]',
                '[role="grid"]',
                '.app-wrapper-web',
                '[data-testid="chats-list"]'
            ]
            
            for selector in login_indicators:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    return True
            
            return False
        except Exception as e:
            self.logger.debug(f"Error checking login status: {e}")
            return False

    async def _monitor_messages(self):
        """Enhanced message monitoring with better selectors"""
        self.logger.info("👂 Starting message monitoring...")
        
        while self.running:
            try:
                # Wait a bit to avoid overwhelming the page
                await asyncio.sleep(2)
                
                # Get all message elements with multiple selectors
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
                
                # Process recent messages
                for message in messages[-5:]:  # Check last 5 messages
                    try:
                        message_id = message.get_attribute("data-id") or str(hash(message.get_attribute("outerHTML")))
                        
                        if message_id and message_id not in self.processed_messages:
                            # Extract message data
                            message_data = await self._extract_message_data(message)
                            
                            if message_data:
                                # Add to queue for processing
                                await self.message_queue.put(message_data)
                                self.processed_messages.add(message_id)
                                
                                # Keep only recent message IDs in memory
                                if len(self.processed_messages) > 1000:
                                    self.processed_messages = set(list(self.processed_messages)[-500:])
                    except Exception as e:
                        self.logger.debug(f"Error processing message: {e}")
                        continue
                
            except Exception as e:
                self.logger.error(f"❌ Error monitoring messages: {e}")
                
                # Try to recover by checking if driver is still alive
                try:
                    self.driver.current_url
                except:
                    self.logger.info("🔄 WebDriver session lost, attempting recovery...")
                    if await self.webdriver_manager.restart_driver():
                        self.driver = self.webdriver_manager.driver
                        await self._authenticate()
                
                await asyncio.sleep(10)  # Wait longer on error

    async def _extract_message_data(self, message_element):
        """Enhanced message data extraction"""
        try:
            # Try multiple selectors for message text
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
            
            # Determine if message is outgoing
            is_outgoing = 'message-out' in message_element.get_attribute('class') or False
            
            # Get sender info (simplified)
            sender = "You" if is_outgoing else "Contact"
            
            # Get timestamp
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
            # Try to get chat name from header
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
                # Get message from queue
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                
                # Process the message if handler is available
                if self.message_handler:
                    await self.message_handler.handle_message(message)
                else:
                    self.logger.info(f"📨 Received: {message['text'][:100]}...")
                
                # Update statistics
                self.stats['messages_received'] += 1
                
                # Forward to Telegram if enabled
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
            
            # First, find and click on the chat
            if not await self._select_chat(chat):
                self.logger.error(f"❌ Could not find chat: {chat}")
                return False
            
            # Find message input box
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
            
            # Click and type message
            input_box.click()
            await asyncio.sleep(0.5)
            input_box.send_keys(message)
            await asyncio.sleep(0.5)
            
            # Send message
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
                # Fallback: use Enter key
                input_box.send_keys(Keys.ENTER)
            
            await asyncio.sleep(1)
            
            # Update statistics
            self.stats['messages_sent'] += 1
            
            self.logger.info(f"✅ Message sent successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send message: {e}")
            return False

    async def _select_chat(self, chat_name: str):
        """Select a chat by name"""
        try:
            # Use search to find the chat
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
                
                # Click on first result
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
        
        # Give tasks time to finish
        await asyncio.sleep(2)
        
        # Close WebDriver
        if self.webdriver_manager:
            self.webdriver_manager.cleanup()
        
        # Shutdown components
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
