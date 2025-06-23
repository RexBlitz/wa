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

import telegram # Import the telegram library for message objects

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
        # Initialize TelegramBridge with config and logger
        self.telegram_bridge = TelegramBridge(config, logger) if TelegramBridge and hasattr(config, 'telegram') and config.telegram.enabled else None
        self.auth_manager = AuthenticationManager(config, logger, self.telegram_bridge) if AuthenticationManager else None
        self.webdriver_manager = WebDriverManager(config, logger)
        self.message_queue = asyncio.Queue() # For incoming WhatsApp messages
        self.telegram_in_queue = asyncio.Queue() # NEW: For incoming Telegram messages (replies)
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
            self.driver.implicitly_wait(self.config.whatsapp.implicit_wait) # Use config value
            self.driver.set_page_load_timeout(self.config.whatsapp.page_load_timeout) # Use config value

            # Initialize and start Telegram Bridge
            if self.telegram_bridge:
                # Start Telegram polling in a background task, passing the new queue
                asyncio.create_task(self.telegram_bridge.start(self.telegram_in_queue))

            if not await self._authenticate():
                raise Exception("Authentication failed")
            
            self.running = True
            tasks = [
                asyncio.create_task(self._message_processor()), # Processes WhatsApp messages
                asyncio.create_task(self._monitor_messages()),  # Monitors WhatsApp for new messages
                asyncio.create_task(self._process_telegram_in_queue()) # NEW: Processes incoming Telegram messages
            ]
            
            self.logger.info("🚀 Bot started successfully")
            await asyncio.gather(*tasks) # Use gather to run all tasks concurrently

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
                # Find all message containers
                messages = self.driver.find_elements(By.CSS_SELECTOR, self.selectors['messages'])
                
                # Process only the latest messages to avoid re-processing old ones
                for message_element in messages[-5:]: # Check last 5 messages
                    message_id = message_element.get_attribute("data-id")
                    if not message_id: # Fallback if data-id is not present
                        message_id = str(hash(message_element.get_attribute("outerHTML")))

                    if message_id not in self.processed_messages:
                        message_data = await self._extract_message_data(message_element)
                        if message_data:
                            await self.message_queue.put(message_data)
                            self.processed_messages.add(message_id)

                            # Forward to Telegram
                            if self.telegram_bridge and not message_data.get('is_outgoing'): # Only forward incoming
                                await self.telegram_bridge.forward_whatsapp_message(message_data)
                                self.logger.info(f"📤 Forwarded WhatsApp message to Telegram: {message_data.get('text')[:50]}...")
                
                await asyncio.sleep(2) # Poll every 2 seconds
            except Exception as e:
                self.logger.error(f"❌ Error monitoring messages: {e}")
                await asyncio.sleep(10) # Longer wait on error

    async def _extract_message_data(self, message_element):
        """Extract message data"""
        try:
            # Attempt to find common text elements
            text_element_selectors = [
                '.selectable-text', # General selectable text
                'span.selectable-text',
                'div.message-text'
            ]
            message_text = ""
            for selector in text_element_selectors:
                try:
                    text_el = message_element.find_element(By.CSS_SELECTOR, selector)
                    message_text = text_el.text.strip()
                    if message_text:
                        break
                except NoSuchElementException:
                    continue # Try next selector

            is_outgoing = 'message-out' in message_element.get_attribute('class')
            
            # Attempt to get sender name for incoming messages
            sender = "You" if is_outgoing else "Contact" # Default
            if not is_outgoing:
                try:
                    # Look for sender name (e.g., in group chats)
                    sender_element = message_element.find_element(By.CSS_SELECTOR, '.copyable-text[data-pre-plain-text]')
                    # Extract name from data-pre-plain-text attribute
                    pre_text = sender_element.get_attribute('data-pre-plain-text')
                    if pre_text:
                        # Example: "[14:30, 01/01/2024] John Doe:" -> "John Doe"
                        sender_match = re.search(r'\]\s*([^:]+):', pre_text)
                        if sender_match:
                            sender = sender_match.group(1).strip()
                except NoSuchElementException:
                    pass # Not a group message, or sender name not found in this way
                except Exception as e:
                    self.logger.debug(f"Error extracting sender name: {e}")

            return {
                'id': message_element.get_attribute("data-id"),
                'text': message_text,
                'sender': sender,
                'timestamp': time.time(),
                'is_outgoing': is_outgoing,
                'chat': await self._get_current_chat(),
                'chat_id': await self._get_current_chat_id() # Add chat_id for mapping
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

    async def _get_current_chat_id(self):
        """Get current chat's unique ID from URL or element attribute"""
        try:
            # WhatsApp Web typically encodes chat ID in the URL or a data attribute
            current_url = self.driver.current_url
            match = re.search(r'whatsapp.com/chats/(\d+)', current_url)
            if match:
                return match.group(1)
            
            # Fallback to data attribute on the conversation panel
            conversation_panel = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="conversation-panel"]')
            chat_id = conversation_panel.get_attribute('data-chatid')
            if chat_id:
                return chat_id
            
            # Or from chat list element if selected
            active_chat_element = self.driver.find_element(By.CSS_SELECTOR, '[data-testid="chat-list"] .selected [data-testid="cell-frame-container"]')
            chat_id = active_chat_element.get_attribute('data-id')
            if chat_id:
                return chat_id

            return "unknown_chat_id"
        except Exception as e:
            self.logger.debug(f"Could not get current chat ID: {e}")
            return "unknown_chat_id"


    async def _message_processor(self):
        """Process messages from queue (can be used for bot responses or logging)"""
        while self.running:
            try:
                # Get message from queue with a timeout
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                self.stats['messages_received'] += 1
                self.logger.info(f"Received WhatsApp message: {message.get('text')}")
                
                # Your bot's response logic can go here
                # Example: If message text is "hello", send "Hi there!" back
                # if message.get('text', '').lower() == "hello" and not message.get('is_outgoing'):
                #     await self.send_message(message.get('chat'), "Hi there!")
                #     self.logger.info("Sent automated reply 'Hi there!'")

            except asyncio.TimeoutError:
                continue # No messages in queue, continue loop
            except Exception as e:
                self.logger.error(f"❌ Error processing message from queue: {e}")
                self.stats['errors'] += 1

    async def _process_telegram_in_queue(self):
        """NEW: Processes incoming messages from Telegram (e.g., replies to forwarded messages)."""
        while self.running:
            try:
                telegram_message: telegram.Message = await self.telegram_in_queue.get()
                self.logger.info(f"Processing Telegram message (ID: {telegram_message.message_id}) from {telegram_message.from_user.username}: {telegram_message.text[:50]}...")

                # Check if this is a reply to a message we forwarded from WhatsApp
                if telegram_message.reply_to_message and self.telegram_bridge:
                    replied_telegram_msg_id = telegram_message.reply_to_message.message_id
                    whatsapp_details = await self.telegram_bridge.get_whatsapp_details_for_telegram_reply(replied_telegram_msg_id)

                    if whatsapp_details:
                        whatsapp_chat_id = whatsapp_details.get('whatsapp_chat_id')
                        reply_text = telegram_message.text
                        sender_name = telegram_message.from_user.username or telegram_message.from_user.first_name

                        full_reply_text = f"[Telegram Reply from {sender_name}]: {reply_text}"

                        self.logger.info(f"Attempting to send Telegram reply to WhatsApp chat: {whatsapp_chat_id}")
                        await self.send_message(whatsapp_chat_id, full_reply_text)
                    else:
                        self.logger.info(f"Telegram message is a reply, but no WhatsApp mapping found for ID: {replied_telegram_msg_id}")
                        if self.telegram_bridge:
                            await self.telegram_bridge.send_message_to_group(
                                f"I received a reply to a Telegram message (ID: {replied_telegram_msg_id}) but could not find the original WhatsApp conversation. "
                                f"The message was: `{self._escape_markdown_v2(telegram_message.text)}`",
                                reply_to_message_id=telegram_message.message_id
                            )
                else:
                    self.logger.info("Telegram message is not a reply or no mapping. Ignoring for now.")
                    # Example: Handle direct commands to the bot in Telegram
                    if telegram_message.text and telegram_message.text.lower() == "/status":
                        if self.telegram_bridge:
                            await self.telegram_bridge.send_message_to_group(
                                f"WhatsApp UserBot is running!\n\n"
                                f"Status: ✅ Active\n"
                                f"Messages Received: {self.stats['messages_received']}\n"
                                f"Messages Sent: {self.stats['messages_sent']}\n"
                                f"Errors: {self.stats['errors']}\n"
                                f"Uptime: {round((time.time() - self.stats['start_time']) / 3600, 2)} hours"
                            )


            except Exception as e:
                self.logger.error(f"❌ Error processing incoming Telegram message: {e}")
            finally:
                self.telegram_in_queue.task_done()

    def _escape_markdown_v2(self, text: str) -> str:
        """Helper to escape characters for MarkdownV2 parse mode."""
        # See https://core.telegram.org/bots/api#markdownv2-style
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join(['\\' + char if char in escape_chars else char for char in text])


    async def send_message(self, chat: str, message: str):
        """Send message to a WhatsApp chat"""
        try:
            # Locate the search box and type the chat name
            search_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="chat-list-search"]'))
            )
            search_box.click()
            search_box.clear()
            search_box.send_keys(chat)
            await asyncio.sleep(2) # Give time for search results to appear
            
            # Select the chat from the list (first result)
            chat_element_selector = f'[data-testid="chat-list"] [title="{chat}"]' # More specific selector
            chat_element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, chat_element_selector))
            )
            chat_element.click()
            await asyncio.sleep(1) # Wait for chat to load

            # Locate the message input box and send the message
            input_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="conversation-compose-box-input"]'))
            )
            input_box.click()
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)
            self.stats['messages_sent'] += 1
            self.logger.info(f"✅ Message sent to {chat}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to send message to {chat}: {e}")
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

# Re-import `re` as it's used in `_extract_message_data` and `_get_current_chat_id`
import re
