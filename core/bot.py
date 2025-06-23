"""
Main WhatsApp UserBot class
Handles WhatsApp automation, message processing, and module management
"""

import asyncio
import time
import os
from typing import Dict, List, Optional, Any
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .telegram_bridge import TelegramBridge
from .database import DatabaseManager
from .module_manager import ModuleManager
from .message_handler import MessageHandler
from .auth import AuthenticationManager
from .webdriver_manager import WebDriverManager
from utils.qr_generator import generate_qr_code


class WhatsAppUserBot:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.driver = None
        self.running = False
        
        # Initialize components
        self.db_manager = DatabaseManager(config, logger)
        self.telegram_bridge = TelegramBridge(config, logger) if config.telegram.enabled else None
        self.module_manager = ModuleManager(config, logger)
        self.message_handler = MessageHandler(config, logger)
        self.auth_manager = AuthenticationManager(config, logger)
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

    async def initialize(self):
        """Initialize all bot components"""
        self.logger.info("🔧 Initializing bot components...")
        
        try:
            # Initialize database
            await self.db_manager.initialize()
            
            # Initialize Telegram bridge if enabled
            if self.telegram_bridge:
                await self.telegram_bridge.initialize()
            
            # Load modules
            await self.module_manager.load_all_modules()
            
            # Initialize message handler
            await self.message_handler.initialize(self)
            
            self.logger.info("✅ All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize components: {e}")
            raise

    async def start(self):
        """Start the WhatsApp bot"""
        try:
            # Setup WebDriver with enhanced compatibility
            self.driver = await self.webdriver_manager.setup_driver()
            
            if not self.driver:
                raise Exception("Failed to setup WebDriver with all available methods")
            
            # Log driver information
            driver_info = self.webdriver_manager.get_driver_info()
            self.logger.info(f"🌐 WebDriver Info: {driver_info}")
            
            # Set timeouts
            self.driver.implicitly_wait(self.config.whatsapp.implicit_wait)
            self.driver.set_page_load_timeout(self.config.whatsapp.page_load_timeout)
            
            # Authenticate with WhatsApp
            if not await self._authenticate():
                raise Exception("Authentication failed")
            
            # Start message processing
            self.running = True
            asyncio.create_task(self._message_processor())
            asyncio.create_task(self._monitor_messages())
            
            # Start Telegram bridge if enabled
            if self.telegram_bridge:
                asyncio.create_task(self.telegram_bridge.start())
            
            self.logger.info("🚀 Bot started successfully!")
            
            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            raise

    async def _authenticate(self):
        """Authenticate with WhatsApp Web"""
        self.logger.info("🔐 Authenticating with WhatsApp Web...")
        
        try:
            # Navigate to WhatsApp Web
            self.driver.get("https://web.whatsapp.com")
            
            # Check if already logged in
            if await self._is_logged_in():
                self.logger.info("✅ Already authenticated!")
                return True
            
            # Handle authentication based on method
            if self.config.whatsapp.auth_method == "qr":
                return await self._authenticate_with_qr()
            elif self.config.whatsapp.auth_method == "phone":
                return await self._authenticate_with_phone()
            else:
                raise ValueError(f"Unsupported auth method: {self.config.whatsapp.auth_method}")
                
        except Exception as e:
            self.logger.error(f"❌ Authentication failed: {e}")
            return False

    async def _authenticate_with_qr(self):
        """Authenticate using QR code"""
        self.logger.info("📱 Waiting for QR code...")
        
        try:
            # Wait for QR code element with longer timeout
            qr_element = WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "canvas"))
            )
            
            # Get QR code data
            qr_data = self.driver.execute_script("""
                var canvas = arguments[0];
                return canvas.toDataURL();
            """, qr_element)
            
            # Generate and display QR code
            qr_path = generate_qr_code(qr_data, "./temp/qr_code.png")
            self.logger.info(f"📱 QR Code saved to: {qr_path}")
            self.logger.info("📱 Scan the QR code with your WhatsApp mobile app")
            
            # Wait for authentication with extended timeout
            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='chat-list']"))
            )
            
            self.logger.info("✅ QR Code authentication successful!")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ QR authentication failed: {e}")
            
            # Try to restart driver and retry once
            self.logger.info("🔄 Attempting to restart WebDriver and retry...")
            if await self.webdriver_manager.restart_driver():
                self.driver = self.webdriver_manager.driver
                return await self._authenticate_with_qr()
            
            return False

    async def _authenticate_with_phone(self):
        """Authenticate using phone number"""
        # This would implement phone number authentication
        # For now, fallback to QR code
        self.logger.warning("📞 Phone authentication not fully implemented, using QR code")
        return await self._authenticate_with_qr()

    async def _is_logged_in(self):
        """Check if already logged in to WhatsApp Web"""
        try:
            await asyncio.sleep(3)
            chat_list = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='chat-list']")
            return len(chat_list) > 0
        except:
            return False

    async def _monitor_messages(self):
        """Monitor for new messages"""
        self.logger.info("👂 Starting message monitoring...")
        
        while self.running:
            try:
                # Get all message elements
                messages = self.driver.find_elements(By.CSS_SELECTOR, "[data-testid='msg-container']")
                
                for message in messages[-10:]:  # Check last 10 messages
                    message_id = message.get_attribute("data-id")
                    
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
                
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                self.logger.error(f"❌ Error monitoring messages: {e}")
                
                # Try to recover by restarting driver
                if "no such window" in str(e).lower() or "session deleted" in str(e).lower():
                    self.logger.info("🔄 Attempting to recover WebDriver session...")
                    if await self.webdriver_manager.restart_driver():
                        self.driver = self.webdriver_manager.driver
                        await self._authenticate()
                
                await asyncio.sleep(5)

    async def _extract_message_data(self, message_element):
        """Extract message data from DOM element"""
        try:
            # This is a simplified extraction - would need more sophisticated parsing
            text_element = message_element.find_element(By.CSS_SELECTOR, ".selectable-text")
            message_text = text_element.text if text_element else ""
            
            # Get sender info (simplified)
            sender = "Unknown"
            
            # Get timestamp
            timestamp = time.time()
            
            return {
                'id': message_element.get_attribute("data-id"),
                'text': message_text,
                'sender': sender,
                'timestamp': timestamp,
                'is_outgoing': 'message-out' in message_element.get_attribute('class'),
                'chat': self._get_current_chat()
            }
            
        except Exception as e:
            self.logger.debug(f"Could not extract message data: {e}")
            return None

    def _get_current_chat(self):
        """Get current active chat information"""
        try:
            # This would extract current chat info
            return "Unknown Chat"
        except:
            return "Unknown Chat"

    async def _message_processor(self):
        """Process messages from the queue"""
        while self.running:
            try:
                # Get message from queue
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                
                # Process the message
                await self.message_handler.handle_message(message)
                
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
        """Send a message to a WhatsApp chat"""
        try:
            # This would implement message sending logic
            # For now, just log it
            self.logger.info(f"📤 Sending message to {chat}: {message}")
            
            # Update statistics
            self.stats['messages_sent'] += 1
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send message: {e}")
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
            'driver_info': driver_info
        }

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        self.logger.info("🛑 Shutting down bot...")
        
        self.running = False
        
        # Close WebDriver
        self.webdriver_manager.cleanup()
        
        # Shutdown components
        if self.telegram_bridge:
            await self.telegram_bridge.shutdown()
        
        await self.db_manager.close()
        
        self.logger.info("✅ Bot shutdown complete")
