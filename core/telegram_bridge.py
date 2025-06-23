import telegram
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
import json
import logging # Import logging module

# Configure logging for this module
logger = logging.getLogger(__name__)
# Basic configuration, you might want to integrate this with your main bot's logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class TelegramBridge:
    def __init__(self, config, logger_instance):
        self.config = config
        self.logger = logger_instance # Use the logger instance passed from the bot
        self.bot = None
        self.group_chat_id = None
        self.enabled = False
        # Mapping Telegram message_id to WhatsApp details for replies
        self.message_map: Dict[int, Dict[str, Any]] = {} # Telegram message_id -> {'whatsapp_chat_id': ..., 'whatsapp_message_id': ...}
        # Mapping WhatsApp chat/message to Telegram details for threading/tracking
        self.whatsapp_to_telegram_map: Dict[str, Dict[str, Any]] = {} # whatsapp_chat_id -> {'telegram_chat_id': ..., 'telegram_thread_id': ...}
        self.map_file = Path("./temp/telegram_message_map.json") # Persistent mapping file

        # Ensure the temp directory exists for the map file
        Path("./temp").mkdir(exist_ok=True)


    async def initialize(self):
        """Initializes the Telegram bot client."""
        if hasattr(self.config, 'telegram') and self.config.telegram.enabled:
            token = self.config.telegram.bot_token
            group_chat_id = self.config.telegram.bridge_group_id # Use bridge_group_id from config
            
            if not token or not group_chat_id:
                self.logger.warning("⚠️ Telegram bot_token or bridge_group_id not configured. Telegram bridge will be disabled.")
                self.enabled = False
                return

            try:
                self.bot = telegram.Bot(token=token)
                self.group_chat_id = int(group_chat_id) # Ensure chat_id is integer
                self.enabled = True
                self.logger.info("📡 Telegram Bridge initialized successfully.")
                
                # Load existing message map
                await self._load_message_map()

                # Optional: Send a startup message
                # This message might interfere with the initial QR code sending if sent too early.
                # Consider sending it after successful WhatsApp login.
                # await self.send_message_to_group("WhatsApp UserBot started and Telegram bridge is active! Waiting for messages...")
                
            except Exception as e:
                self.logger.error(f"❌ Failed to initialize Telegram bot: {e}")
                self.enabled = False
        else:
            self.logger.info("Telegram bridge is disabled in configuration.")
            self.enabled = False

    async def _load_message_map(self):
        """Loads the message map from a file."""
        if self.map_file.exists():
            try:
                with open(self.map_file, 'r') as f:
                    data = json.load(f)
                    # Convert keys back to int for message_map if they were saved as strings
                    self.message_map = {int(k): v for k, v in data.get('message_map', {}).items()}
                    self.whatsapp_to_telegram_map = data.get('whatsapp_to_telegram_map', {})
                self.logger.info(f"Loaded {len(self.message_map)} message mappings from {self.map_file}")
            except Exception as e:
                self.logger.error(f"❌ Failed to load message map: {e}")

    async def _save_message_map(self):
        """Saves the message map to a file."""
        try:
            with open(self.map_file, 'w') as f:
                json.dump({
                    'message_map': self.message_map,
                    'whatsapp_to_telegram_map': self.whatsapp_to_telegram_map
                }, f, indent=2)
            self.logger.debug(f"Saved message map to {self.map_file}")
        except Exception as e:
            self.logger.error(f"❌ Failed to save message map: {e}")

    async def start(self, update_queue: asyncio.Queue):
        """Starts the Telegram bot for polling updates and pushes them to update_queue."""
        if not self.enabled:
            self.logger.info("Telegram bridge not enabled, skipping bot polling.")
            return

        self.logger.info("🚀 Starting Telegram bot polling...")
        
        offset = 0
        while self.enabled:
            try:
                updates = await self.bot.get_updates(offset=offset, timeout=10)
                for update in updates:
                    offset = update.update_id + 1
                    if update.message:
                        await update_queue.put(update.message) # Push incoming message to a queue
                        self.logger.info(f"Received Telegram message (ID: {update.message.message_id}) from {update.message.from_user.username}")
                await asyncio.sleep(1) # Short delay to avoid hammering API
            except telegram.error.TimedOut:
                pass
            except telegram.error.NetworkError as e:
                self.logger.error(f"❌ Telegram Network Error: {e}. Retrying in 5 seconds...")
                await asyncio.sleep(5)
            except Exception as e:
                self.logger.error(f"❌ Unhandled error during Telegram polling: {e}")
                await asyncio.sleep(5)

    async def send_message_to_group(self, text: str, reply_to_message_id: int = None, thread_id: int = None):
        """Sends a text message to the configured Telegram group."""
        if self.enabled and self.bot and self.group_chat_id:
            try:
                # Telegram API limits message length to 4096 characters for MarkdownV2
                if len(text) > 4096:
                    self.logger.warning(f"Message too long ({len(text)} chars). Truncating for Telegram.")
                    text = text[:4090] + "..." # Truncate and add ellipsis

                message = await self.bot.send_message(
                    chat_id=self.group_chat_id,
                    text=text,
                    reply_to_message_id=reply_to_message_id,
                    message_thread_id=thread_id, # For topics/threads in supergroups
                    parse_mode=telegram.ParseMode.MARKDOWN_V2 # For rich formatting
                )
                self.logger.debug(f"Sent Telegram message to group: {text[:50]}...")
                return message.message_id
            except Exception as e:
                self.logger.error(f"❌ Failed to send Telegram message to group (Chat ID: {self.group_chat_id}): {e}")
        elif not self.enabled:
            self.logger.debug("Telegram bridge not enabled, skipping message send.")
        return None

    async def forward_qr_code(self, qr_image_path: str):
        """Sends the QR code image to the configured Telegram group."""
        if self.enabled and self.bot and self.group_chat_id:
            try:
                qr_file = Path(qr_image_path)
                if qr_file.exists():
                    with open(qr_file, 'rb') as f:
                        await self.bot.send_photo(chat_id=self.group_chat_id, photo=f, caption="WhatsApp QR Code for login")
                    self.logger.info(f"✅ QR code image sent to Telegram: {qr_image_path}")
                    return True # Indicate success
                else:
                    self.logger.error(f"❌ QR code image file not found: {qr_image_path}")
                    return False
            except Exception as e:
                self.logger.error(f"❌ Failed to send QR code image to Telegram: {e}")
                return False
        elif not self.enabled:
            self.logger.debug("Telegram bridge not enabled, skipping QR code send.")
        return False

    async def forward_whatsapp_message(self, message_data: Dict[str, Any]):
        """Forwards a WhatsApp message to Telegram, attempting to use threads/replies."""
        if not self.enabled:
            self.logger.debug("Telegram bridge not enabled, skipping WhatsApp message forward.")
            return

        try:
            chat_name = message_data.get('chat', 'Unknown Chat')
            sender = message_data.get('sender', 'Unknown Sender')
            text = message_data.get('text', 'No text')
            whatsapp_chat_id = message_data.get('chat_id') # WhatsApp chat ID (unique per chat)
            whatsapp_message_id = message_data.get('id') # WhatsApp message ID (unique per message within a chat)
            
            # Use WhatsApp chat ID as key for Telegram threading/topic
            telegram_thread_id = None
            if self.config.telegram.thread_per_user:
                # Check if we already have a Telegram thread/topic for this WhatsApp chat
                if whatsapp_chat_id in self.whatsapp_to_telegram_map:
                    telegram_thread_id = self.whatsapp_to_telegram_map[whatsapp_chat_id].get('telegram_thread_id')
                # If not, for the first message, we send it to the main group, and if a topic is created,
                # we'd ideally get its ID from the Telegram API response (send_message creates topic if message_thread_id is absent in a supergroup).
                # However, Telegram's API for `send_message` doesn't return the new topic ID directly when it creates one implicitly.
                # For explicit topic creation and getting its ID, you'd need `createForumTopic`.
                # For simplicity here, we'll rely on `reply_to_message_id` for subsequent messages in the same thread.
                # If `telegram_thread_id` is None, it will post to the main group or create a new topic if `thread_per_user` is true and this is the first message.
            
            # Formulate the message to send to Telegram (MarkdownV2)
            formatted_message = (
                f"💬 *New WhatsApp Message*\n"
                f"\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\n"
                f"*Chat*: `{self._escape_markdown_v2(chat_name)}`\n"
                f"*From*: `{self._escape_markdown_v2(sender)}`\n"
                f"*Message*: {self._escape_markdown_v2(text)}\n"
                f"\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_"
            )
            
            # Send to Telegram and get the message ID
            telegram_message_id = await self.send_message_to_group(
                formatted_message,
                thread_id=telegram_thread_id
            )

            if telegram_message_id:
                # Store the mapping for replies
                self.message_map[telegram_message_id] = {
                    'whatsapp_chat_id': whatsapp_chat_id,
                    'whatsapp_message_id': whatsapp_message_id # Can be None if not needed for replies
                }
                # Store mapping for threading (if a thread was created/used)
                if whatsapp_chat_id not in self.whatsapp_to_telegram_map:
                    self.whatsapp_to_telegram_map[whatsapp_chat_id] = {
                        'telegram_chat_id': self.group_chat_id,
                        'telegram_thread_id': telegram_thread_id # Will be None if not using explicit topics, or if it's the main group
                    }
                await self._save_message_map()
                self.logger.info(f"WhatsApp message forwarded to Telegram (Msg ID: {telegram_message_id}).")
            else:
                self.logger.error("Failed to get Telegram message ID after forwarding WhatsApp message.")

        except Exception as e:
            self.logger.error(f"❌ Error forwarding WhatsApp message to Telegram: {e}")

    def _escape_markdown_v2(self, text: str) -> str:
        """Helper to escape characters for MarkdownV2 parse mode."""
        # See https://core.telegram.org/bots/api#markdownv2-style
        # Escapes characters that have special meaning in MarkdownV2.
        # This list includes all characters from the documentation that need escaping.
        escape_chars = '_*[]()~`>#+-=|{}.!' # These need to be escaped with a backslash
        return ''.join(['\\' + char if char in escape_chars else char for char in text])

    async def get_whatsapp_details_for_telegram_reply(self, telegram_message_id: int):
        """Retrieves WhatsApp details corresponding to a Telegram message ID."""
        return self.message_map.get(telegram_message_id)

    async def shutdown(self):
        """Performs cleanup for the Telegram bridge."""
        if self.enabled:
            self.logger.info("🛑 Shutting down Telegram Bridge.")
            await self._save_message_map()
            self.enabled = False # Stop the polling loop
