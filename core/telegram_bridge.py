"""
Telegram Bridge for WhatsApp UserBot
Handles message forwarding and replies between WhatsApp and Telegram
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from telegram import Bot, Update, Message
from telegram.ext import Application, MessageHandler, CommandHandler, filters
from telegram.constants import ParseMode


class TelegramBridge:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.bot = None
        self.application = None
        self.running = False
        
        # Thread management for per-user conversations
        self.user_threads = {}  # whatsapp_user -> telegram_thread_id
        self.thread_users = {}  # telegram_thread_id -> whatsapp_user
        
        # Message mapping for replies
        self.message_mapping = {}  # telegram_msg_id -> whatsapp_msg_data

    async def initialize(self):
        """Initialize Telegram bot"""
        if not self.config.telegram.bot_token:
            self.logger.warning("🔸 Telegram bot token not configured, bridge disabled")
            return
        
        try:
            self.logger.info("🤖 Initializing Telegram bridge...")
            
            # Create bot instance
            self.bot = Bot(token=self.config.telegram.bot_token)
            
            # Create application
            self.application = Application.builder().token(self.config.telegram.bot_token).build()
            
            # Add handlers
            self._setup_handlers()
            
            # Test bot connection
            bot_info = await self.bot.get_me()
            self.logger.info(f"✅ Telegram bot connected: @{bot_info.username}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize Telegram bridge: {e}")
            raise

    def _setup_handlers(self):
        """Setup Telegram message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self._handle_start))
        self.application.add_handler(CommandHandler("help", self._handle_help))
        self.application.add_handler(CommandHandler("stats", self._handle_stats))
        self.application.add_handler(CommandHandler("users", self._handle_users))
        
        # Message handler for replies
        self.application.add_handler(MessageHandler(
            filters.TEXT & (~filters.COMMAND), 
            self._handle_telegram_message
        ))

    async def start(self):
        """Start the Telegram bridge"""
        if not self.bot:
            return
        
        try:
            self.logger.info("📡 Starting Telegram bridge...")
            self.running = True
            
            # Start the application
            await self.application.initialize()
            await self.application.start()
            
            # Send startup notification
            await self._send_startup_notification()
            
            self.logger.info("✅ Telegram bridge started successfully")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to start Telegram bridge: {e}")

    async def forward_message(self, whatsapp_message: Dict[str, Any]):
        """Forward WhatsApp message to Telegram"""
        if not self.running or not self.bot:
            return
        
        try:
            # Skip outgoing messages (sent by the bot)
            if whatsapp_message.get('is_outgoing', False):
                return
            
            sender = whatsapp_message.get('sender', 'Unknown')
            text = whatsapp_message.get('text', '')
            chat = whatsapp_message.get('chat', 'Unknown Chat')
            
            # Format message for Telegram
            formatted_message = self._format_whatsapp_message(sender, text, chat)
            
            # Get or create thread for this user
            thread_id = await self._get_or_create_thread(sender, chat)
            
            # Send to Telegram
            if self.config.telegram.thread_per_user and thread_id:
                # Send in specific thread
                telegram_msg = await self.bot.send_message(
                    chat_id=self.config.telegram.bridge_group_id,
                    text=formatted_message,
                    message_thread_id=thread_id,
                    parse_mode=ParseMode.HTML
                )
            else:
                # Send in main group
                telegram_msg = await self.bot.send_message(
                    chat_id=self.config.telegram.bridge_group_id,
                    text=formatted_message,
                    parse_mode=ParseMode.HTML
                )
            
            # Store message mapping for replies
            self.message_mapping[telegram_msg.message_id] = whatsapp_message
            
            self.logger.debug(f"📤 Forwarded message from {sender} to Telegram")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to forward message to Telegram: {e}")

    async def _get_or_create_thread(self, sender: str, chat: str) -> Optional[int]:
        """Get existing thread or create new one for user"""
        user_key = f"{sender}_{chat}"
        
        if user_key in self.user_threads:
            return self.user_threads[user_key]
        
        try:
            # Create new forum topic/thread for this user
            topic_name = f"💬 {sender} ({chat})"
            
            # Note: This requires the Telegram group to be a forum/supergroup
            # For regular groups, we'll just use the main chat
            if self.config.telegram.thread_per_user:
                # This would create a forum topic if supported
                # For now, we'll simulate with a thread ID
                thread_id = hash(user_key) % 1000000  # Simple thread ID generation
                self.user_threads[user_key] = thread_id
                self.thread_users[thread_id] = user_key
                
                return thread_id
            
        except Exception as e:
            self.logger.debug(f"Could not create thread for {sender}: {e}")
        
        return None

    def _format_whatsapp_message(self, sender: str, text: str, chat: str) -> str:
        """Format WhatsApp message for Telegram"""
        # Escape HTML special characters
        text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        
        # Truncate if too long
        if len(text) > self.config.telegram.max_message_length - 200:
            text = text[:self.config.telegram.max_message_length - 200] + "..."
        
        return f"<b>📱 {sender}</b> <i>({chat})</i>\n\n{text}"

    async def _handle_start(self, update: Update, context):
        """Handle /start command"""
        if not self._is_admin_user(update.effective_user.id):
            return
        
        welcome_text = """
🤖 <b>WhatsApp UserBot Bridge</b>

This bot bridges messages between WhatsApp and Telegram.

<b>Commands:</b>
/help - Show this help message
/stats - Show bot statistics
/users - List active WhatsApp users

<b>How to reply:</b>
Reply to any forwarded WhatsApp message to send a response back to WhatsApp.
        """
        
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

    async def _handle_help(self, update: Update, context):
        """Handle /help command"""
        await self._handle_start(update, context)

    async def _handle_stats(self, update: Update, context):
        """Handle /stats command"""
        if not self._is_admin_user(update.effective_user.id):
            return
        
        # This would get stats from the main bot
        stats_text = """
📊 <b>Bot Statistics</b>

🔄 Active threads: {thread_count}
👥 Active users: {user_count}
📨 Messages forwarded: N/A
⏱ Uptime: N/A
        """.format(
            thread_count=len(self.user_threads),
            user_count=len(set(self.user_threads.keys()))
        )
        
        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

    async def _handle_users(self, update: Update, context):
        """Handle /users command"""
        if not self._is_admin_user(update.effective_user.id):
            return
        
        if not self.user_threads:
            await update.message.reply_text("No active WhatsApp users")
            return
        
        users_text = "<b>👥 Active WhatsApp Users:</b>\n\n"
        for user_key in self.user_threads.keys():
            sender, chat = user_key.split('_', 1)
            users_text += f"• {sender} ({chat})\n"
        
        await update.message.reply_text(users_text, parse_mode=ParseMode.HTML)

    async def _handle_telegram_message(self, update: Update, context):
        """Handle incoming Telegram messages (replies)"""
        if not self._is_admin_user(update.effective_user.id):
            return
        
        message = update.message
        
        # Check if this is a reply to a forwarded WhatsApp message
        if message.reply_to_message:
            replied_msg_id = message.reply_to_message.message_id
            
            if replied_msg_id in self.message_mapping:
                # Get original WhatsApp message data
                whatsapp_msg = self.message_mapping[replied_msg_id]
                sender = whatsapp_msg.get('sender')
                chat = whatsapp_msg.get('chat')
                
                # Send reply back to WhatsApp
                reply_success = await self._send_whatsapp_reply(
                    chat, sender, message.text
                )
                
                if reply_success:
                    await message.reply_text("✅ Reply sent to WhatsApp")
                else:
                    await message.reply_text("❌ Failed to send reply to WhatsApp")
                
                return
        
        # Check if message is in a user thread
        thread_id = message.message_thread_id
        if thread_id and thread_id in self.thread_users:
            user_key = self.thread_users[thread_id]
            sender, chat = user_key.split('_', 1)
            
            # Send message to specific WhatsApp user
            reply_success = await self._send_whatsapp_reply(
                chat, sender, message.text
            )
            
            if reply_success:
                await message.reply_text("✅ Message sent to WhatsApp")
            else:
                await message.reply_text("❌ Failed to send message to WhatsApp")

    async def _send_whatsapp_reply(self, chat: str, recipient: str, message: str) -> bool:
        """Send reply back to WhatsApp"""
        try:
            # This would integrate with the main bot to send WhatsApp messages
            # For now, just log it
            self.logger.info(f"📤 Sending reply to {recipient} in {chat}: {message}")
            
            # TODO: Integrate with main bot's send_message method
            # await self.main_bot.send_message(chat, message)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to send WhatsApp reply: {e}")
            return False

    def _is_admin_user(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.config.telegram.admin_users

    async def _send_startup_notification(self):
        """Send startup notification to Telegram"""
        try:
            await self.bot.send_message(
                chat_id=self.config.telegram.bridge_group_id,
                text="🚀 <b>WhatsApp UserBot Bridge Started</b>\n\nBot is now online and ready to forward messages!",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            self.logger.debug(f"Could not send startup notification: {e}")

    async def shutdown(self):
        """Shutdown Telegram bridge"""
        if self.application:
            self.logger.info("🛑 Shutting down Telegram bridge...")
            await self.application.stop()
            await self.application.shutdown()
        
        self.running = False
        self.logger.info("✅ Telegram bridge shutdown complete")