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
import re # Import re for regex used in message extraction

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
        self.processed_messages = set() # To prevent reprocessing same WhatsApp messages
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
            'messages': '[data-testid="msg-container"]' # General selector for message containers
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

            # Initialize and start Telegram Bridge polling
            if self.telegram_bridge:
                # Start Telegram polling in a background task, passing the new queue
                asyncio.create_task(self.telegram_bridge.start(self.telegram_in_queue))
                self.logger.info("Telegram bridge polling started in background.")

            if not await self._authenticate():
                raise Exception("Authentication failed")
            
            self.running = True
            tasks = [
                asyncio.create_task(self._message_processor()), # Processes WhatsApp messages
                asyncio.create_task(self._monitor_messages()),  # Monitors WhatsApp for new messages
                asyncio.create_task(self._process_telegram_in_queue()) # NEW: Processes incoming Telegram messages (replies)
            ]
            
            self.logger.info("🚀 Bot started successfully, monitoring messages and Telegram replies.")
            await asyncio.gather(*tasks) # Use gather to run all tasks concurrently

        except Exception as e:
            self.logger.error(f"❌ Failed to start bot: {e}")
            await self.shutdown()

    async def _authenticate(self):
        """Authenticate with WhatsApp Web"""
        self.logger.info("🔐 Authenticating with WhatsApp Web...")
        try:
            if self.auth_manager:
                # Attempt to load session first
                if await self.auth_manager._load_session(self.driver):
                    self.logger.info("✅ Re-authenticated using saved session.")
                    return True
                # If session failed or didn't exist, proceed with full authentication
                return await self.auth_manager.authenticate(self.driver)
            raise Exception("AuthenticationManager not initialized")
        except Exception as e:
            self.logger.error(f"❌ Authentication failed: {e}")
            return False

    async def _monitor_messages(self):
        """Monitor messages in the currently open WhatsApp chat."""
        self.logger.info("👂 Starting WhatsApp message monitoring...")
        while self.running:
            try:
                # Find all message containers
                messages = self.driver.find_elements(By.CSS_SELECTOR, self.selectors['messages'])
                
                # Process only the latest messages that haven't been processed yet
                for message_element in messages:
                    message_id = message_element.get_attribute("data-id")
                    if not message_id: # Fallback if data-id is not present (less reliable)
                        # Generate a pseudo-ID if data-id is missing (e.g., from unique element attributes)
                        outer_html = message_element.get_attribute("outerHTML")
                        if outer_html:
                            message_id = str(hash(outer_html))
                        else:
                            continue # Skip if no identifiable data

                    if message_id not in self.processed_messages:
                        message_data = await self._extract_message_data(message_element)
                        if message_data and message_data.get('id'): # Ensure message_id is present
                            await self.message_queue.put(message_data)
                            self.processed_messages.add(message_data['id']) # Use the actual extracted ID for processed set

                            # Forward to Telegram only if it's an incoming message
                            if self.telegram_bridge and not message_data.get('is_outgoing'):
                                await self.telegram_bridge.forward_whatsapp_message(message_data)
                                self.logger.info(f"📤 Forwarded WhatsApp message to Telegram: {message_data.get('text', '')[:50]}...")
                
                await asyncio.sleep(2) # Poll every 2 seconds
            except Exception as e:
                self.logger.error(f"❌ Error monitoring WhatsApp messages: {e}")
                # Add a small delay on error to prevent tight looping
                await asyncio.sleep(5) 

    async def _extract_message_data(self, message_element):
        """Extract message data from a WhatsApp message element."""
        try:
            # WhatsApp Web elements can be tricky. Use robust selectors.
            message_id = message_element.get_attribute("data-id")
            
            # Determine if it's an outgoing or incoming message based on class
            is_outgoing = 'message-out' in message_element.get_attribute('class')
            
            message_text = ""
            # Try various selectors for message text, prioritizing those likely to contain actual content
            text_element_selectors = [
                '[data-testid="conversation-message-text"] > span', # Common for text messages
                '.selectable-text span', # Broader text content
                '.copyable-text span', # Can contain text
            ]
            for selector in text_element_selectors:
                try:
                    text_el = message_element.find_element(By.CSS_SELECTOR, selector)
                    message_text = text_el.text.strip()
                    if message_text:
                        break # Found text, stop searching
                except NoSuchElementException:
                    continue # Try next selector
                except Exception as e:
                    self.logger.debug(f"Error finding text with selector {selector}: {e}")

            sender = "You" if is_outgoing else "Contact" # Default sender
            if not is_outgoing:
                try:
                    # In group chats, sender name might be in data-pre-plain-text or a specific span
                    # Look for sender name (e.g., in group chats or status messages)
                    sender_span = message_element.find_element(By.CSS_SELECTOR, '[data-testid="message-sender-info"] span')
                    sender = sender_span.text.strip()
                except NoSuchElementException:
                    # Fallback for individual chats or if specific sender span is not present
                    pass
                except Exception as e:
                    self.logger.debug(f"Error extracting sender name: {e}")

            # Get current chat name and ID (these methods should be robust)
            current_chat_name = await self._get_current_chat_name()
            current_chat_id = await self._get_current_chat_id()

            return {
                'id': message_id,
                'text': message_text,
                'sender': sender,
                'timestamp': time.time(),
                'is_outgoing': is_outgoing,
                'chat': current_chat_name,
                'chat_id': current_chat_id # WhatsApp's internal chat ID
            }
        except Exception as e:
            self.logger.debug(f"Could not extract message data from element: {e}")
            return None

    async def _get_current_chat_name(self):
        """Get the name of the currently active WhatsApp chat."""
        try:
            # Common selector for chat header title
            header_title = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="conversation-info-header"] [data-testid="conversation-info-header-chat-title"]'))
            )
            return header_title.text.strip()
        except TimeoutException:
            self.logger.warning("Could not find current chat name within timeout.")
            return "Unknown Chat"
        except Exception as e:
            self.logger.error(f"Error getting current chat name: {e}")
            return "Unknown Chat"

    async def _get_current_chat_id(self):
        """Get the unique ID of the currently active WhatsApp chat."""
        try:
            # WhatsApp Web encodes chat ID in the URL for individual/group chats
            current_url = self.driver.current_url
            match = re.search(r'whatsapp.com/chats/(\d+)', current_url)
            if match:
                return match.group(1)
            
            # Fallback: Look for data-id on the active chat element in the chat list
            try:
                active_chat_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="chat-list"] [data-testid="cell-frame-container"][aria-selected="true"]'))
                )
                chat_id = active_chat_element.get_attribute('data-id')
                if chat_id:
                    # Remove any suffix like "_0" if present, to get the base chat ID
                    return chat_id.split('_')[0]
            except TimeoutException:
                pass # Continue to next fallback
            
            self.logger.warning("Could not determine current chat ID from URL or chat list.")
            return "unknown_chat_id"
        except Exception as e:
            self.logger.error(f"Error getting current chat ID: {e}")
            return "unknown_chat_id"


    async def _message_processor(self):
        """Process messages from queue (can be used for bot responses or logging)"""
        self.logger.info("Starting WhatsApp message processor...")
        while self.running:
            try:
                # Get message from queue with a timeout to allow graceful shutdown
                message = await asyncio.wait_for(self.message_queue.get(), timeout=1.0)
                self.stats['messages_received'] += 1
                self.logger.info(f"Processing WhatsApp message: {message.get('text')}")
                
                # Your bot's response logic can go here.
                # Example: If message text is "hello", send "Hi there!" back
                # if message.get('text', '').lower() == "hello" and not message.get('is_outgoing'):
                #     await self.send_message(message.get('chat_id'), "Hi there from your bot!")
                #     self.logger.info("Sent automated reply 'Hi there!'")

            except asyncio.TimeoutError:
                continue # No messages in queue, continue loop
            except Exception as e:
                self.logger.error(f"❌ Error processing message from WhatsApp queue: {e}")
                self.stats['errors'] += 1

    async def _process_telegram_in_queue(self):
        """NEW: Processes incoming messages from Telegram (e.g., replies to forwarded messages)."""
        self.logger.info("Starting Telegram incoming message processor...")
        while self.running:
            try:
                # Get Telegram message from queue with a timeout
                telegram_message: telegram.Message = await asyncio.wait_for(self.telegram_in_queue.get(), timeout=1.0)
                self.logger.info(f"Processing Telegram message (ID: {telegram_message.message_id}) from {telegram_message.from_user.username}: {telegram_message.text[:50] if telegram_message.text else ''}...")

                # Check if this is a reply to a message we forwarded from WhatsApp
                if telegram_message.reply_to_message and self.telegram_bridge:
                    replied_telegram_msg_id = telegram_message.reply_to_message.message_id
                    whatsapp_details = await self.telegram_bridge.get_whatsapp_details_for_telegram_reply(replied_telegram_msg_id)

                    if whatsapp_details:
                        whatsapp_chat_id = whatsapp_details.get('whatsapp_chat_id')
                        reply_text = telegram_message.text or ""
                        sender_name = telegram_message.from_user.full_name or telegram_message.from_user.username or "Telegram User"

                        full_reply_text = f"🗣️ [Telegram Reply from {sender_name}]:\n{reply_text}"

                        self.logger.info(f"Attempting to send Telegram reply to WhatsApp chat ID: {whatsapp_chat_id}")
                        await self.send_message(whatsapp_chat_id, full_reply_text)
                    else:
                        self.logger.info(f"Telegram message is a reply, but no WhatsApp mapping found for Telegram Msg ID: {replied_telegram_msg_id}. Message: {telegram_message.text[:50]}")
                        if self.telegram_bridge:
                            await self.telegram_bridge.send_message_to_group(
                                f"❗️ I received a reply to a Telegram message (ID: `{replied_telegram_msg_id}`) but could not find the original WhatsApp conversation. "
                                f"The message was: `{self._escape_markdown_v2(telegram_message.text)}`",
                                reply_to_message_id=telegram_message.message_id
                            )
                else:
                    self.logger.info(f"Telegram message (ID: {telegram_message.message_id}) is not a reply to a forwarded WhatsApp message. Content: {telegram_message.text[:50] if telegram_message.text else ''}. Ignoring for now, or handling as a direct command.")
                    # Example: Handle direct commands to the bot in Telegram
                    if telegram_message.text and telegram_message.text.lower() == "/status":
                        if self.telegram_bridge:
                            await self.telegram_bridge.send_message_to_group(
                                f"🤖 WhatsApp UserBot is running!\n\n"
                                f"*Status*: ✅ Active\n"
                                f"*Messages Received*: {self.stats['messages_received']}\n"
                                f"*Messages Sent*: {self.stats['messages_sent']}\n"
                                f"*Errors*: {self.stats['errors']}\n"
                                f"*Uptime*: {round((time.time() - self.stats['start_time']) / 3600, 2)} hours",
                                reply_to_message_id=telegram_message.message_id
                            )


            except asyncio.TimeoutError:
                continue # No messages in queue, continue loop
            except Exception as e:
                self.logger.error(f"❌ Error processing incoming Telegram message: {e}")
            finally:
                self.telegram_in_queue.task_done()

    def _escape_markdown_v2(self, text: str) -> str:
        """Helper to escape characters for MarkdownV2 parse mode."""
        # See https://core.telegram.org/bots/api#markdownv2-style
        escape_chars = '_*[]()~`>#+-=|{}.!' # These need to be escaped with a backslash
        return ''.join(['\\' + char if char in escape_chars else char for char in text])


    async def send_message(self, chat_identifier: str, message: str):
        """Send message to a WhatsApp chat using its ID or partial name/number."""
        try:
            # First, try to locate the chat using a more robust selector that includes the chat identifier
            # This is an improvement over just using the title, as chat_identifier might be a number
            chat_element_selector = f'[data-testid="chat-list"] [data-id*="{chat_identifier}"]'
            try:
                chat_element = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, chat_element_selector))
                )
                chat_element.click()
                await asyncio.sleep(1) # Wait for chat to load
            except TimeoutException:
                # If specific ID/partial identifier not found, try using the search box
                self.logger.info(f"Chat element with ID/partial ID '{chat_identifier}' not found directly, trying search box.")
                search_box_selectors = [
                    '[data-testid="chat-list-search"]', # Newer selector
                    'div[contenteditable="true"][role="textbox"][title="Search input"]', # Older search input
                    'div[data-tab="3"]' # Very generic, might need to be refined
                ]
                search_box = None
                for selector in search_box_selectors:
                    try:
                        search_box = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        search_box.click() # Click to activate search input
                        break
                    except TimeoutException:
                        continue
                
                if not search_box:
                    self.logger.error("❌ Could not find WhatsApp search box.")
                    return False

                search_box.clear()
                search_box.send_keys(chat_identifier)
                await asyncio.sleep(3) # Give time for search results to appear

                # After typing, try to select the first matching chat from results
                # This selector needs to be carefully chosen to target the actual chat entry
                try:
                    # Look for chat entries that might contain the identifier in their text or data attributes
                    found_chat_element = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, f'//span[@title="{chat_identifier}"]/ancestor::div[starts-with(@data-testid, "chat-list-row")] | //div[starts-with(@data-testid, "chat-list-row")][.//span[contains(text(), "{chat_identifier}")]]'))
                    )
                    found_chat_element.click()
                    await asyncio.sleep(1)
                except TimeoutException:
                    self.logger.error(f"❌ No chat found in search results for '{chat_identifier}'.")
                    return False

            # Locate the message input box and send the message
            input_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, self.selectors['message_input']))
            )
            input_box.click()
            input_box.send_keys(message)
            input_box.send_keys(Keys.ENTER)
            self.stats['messages_sent'] += 1
            self.logger.info(f"✅ Message sent to {chat_identifier}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to send message to {chat_identifier}: {e}")
            return False

    async def shutdown(self):
        """Shutdown bot"""
        self.logger.info("🛑 Shutting down bot...")
        self.running = False # This will stop all asyncio loops
        if self.telegram_bridge:
            await self.telegram_bridge.shutdown() # Perform Telegram cleanup
        if self.webdriver_manager:
            self.webdriver_manager.cleanup() # Close WebDriver
        self.logger.info("✅ Bot shutdown complete")
