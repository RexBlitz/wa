"""
Message handler for WhatsApp UserBot
Processes incoming messages and routes them to appropriate handlers
"""

import re
import time
from typing import Dict, List, Any, Optional


class MessageHandler:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.bot = None
        self.module_manager = None
        
        # Rate limiting
        self.rate_limit_tracker = {}
        
        # Command parsing
        self.command_prefix = "!"
        self.command_pattern = re.compile(r'^[!./](\w+)(?:\s+(.*))?$')

    async def initialize(self, bot):
        """Initialize message handler"""
        self.bot = bot
        self.module_manager = bot.module_manager
        self.logger.info("💬 Message handler initialized")

    async def handle_message(self, message: Dict[str, Any]):
        """Handle incoming message"""
        try:
            # Skip outgoing messages
            if message.get('is_outgoing', False):
                return
            
            # Rate limiting check
            if not await self._check_rate_limit(message):
                return
            
            # Security checks
            if not await self._security_check(message):
                return
            
            # Save message to database
            await self.bot.db_manager.save_message(message)
            
            # Check if it's a command
            if await self._handle_command(message):
                return
            
            # Pass to modules
            await self.module_manager.handle_message(message)
            
            self.logger.debug(f"📨 Processed message from {message.get('sender', 'Unknown')}")
            
        except Exception as e:
            self.logger.error(f"❌ Error handling message: {e}")

    async def _check_rate_limit(self, message: Dict[str, Any]) -> bool:
        """Check rate limiting"""
        sender = message.get('sender', 'unknown')
        current_time = time.time()
        
        if sender not in self.rate_limit_tracker:
            self.rate_limit_tracker[sender] = []
        
        # Clean old entries
        self.rate_limit_tracker[sender] = [
            timestamp for timestamp in self.rate_limit_tracker[sender]
            if current_time - timestamp < 60  # Last minute
        ]
        
        # Check rate limit
        if len(self.rate_limit_tracker[sender]) >= self.config.security.rate_limit:
            self.logger.warning(f"⚠️ Rate limit exceeded for {sender}")
            return False
        
        # Add current message
        self.rate_limit_tracker[sender].append(current_time)
        return True

    async def _security_check(self, message: Dict[str, Any]) -> bool:
        """Perform security checks"""
        sender = message.get('sender', '')
        
        # Check blacklist
        if sender in self.config.security.blacklist:
            self.logger.warning(f"🚫 Blocked message from blacklisted user: {sender}")
            return False
        
        # Check whitelist (if enabled)
        if (self.config.security.whitelist and 
            sender not in self.config.security.whitelist):
            self.logger.warning(f"🚫 Blocked message from non-whitelisted user: {sender}")
            return False
        
        return True

    async def _handle_command(self, message: Dict[str, Any]) -> bool:
        """Handle command messages"""
        text = message.get('text', '').strip()
        
        if not text:
            return False
        
        # Parse command
        match = self.command_pattern.match(text)
        if not match:
            return False
        
        command = match.group(1).lower()
        args_text = match.group(2) or ""
        args = args_text.split() if args_text else []
        
        self.logger.info(f"🔧 Command received: {command} with args: {args}")
        
        # Check admin-only commands
        if (self.config.security.admin_only_commands and 
            not await self._is_admin_user(message.get('sender'))):
            await self._send_reply(message, "❌ Admin access required for commands")
            return True
        
        # Handle built-in commands
        if await self._handle_builtin_command(command, args, message):
            return True
        
        # Pass to modules
        if await self.module_manager.handle_command(command, args, message):
            self.bot.stats['commands_executed'] += 1
            return True
        
        # Unknown command
        await self._send_reply(message, f"❓ Unknown command: {command}")
        return True

    async def _handle_builtin_command(self, command: str, args: List[str], message: Dict[str, Any]) -> bool:
        """Handle built-in bot commands"""
        if command == "help":
            help_text = await self._get_help_text()
            await self._send_reply(message, help_text)
            return True
        
        elif command == "stats":
            stats = await self.bot.get_stats()
            stats_text = f"""
📊 **Bot Statistics**

⏱ Uptime: {stats['uptime_formatted']}
📨 Messages received: {stats['messages_received']}
📤 Messages sent: {stats['messages_sent']}
🔧 Commands executed: {stats['commands_executed']}
❌ Errors: {stats['errors']}
📦 Loaded modules: {len(self.module_manager.loaded_modules)}
            """.strip()
            await self._send_reply(message, stats_text)
            return True
        
        elif command == "modules":
            modules = self.module_manager.get_loaded_modules()
            if not modules:
                await self._send_reply(message, "📦 No modules loaded")
                return True
            
            modules_text = "📦 **Loaded Modules:**\n\n"
            for name, info in modules.items():
                status = "✅" if info['enabled'] else "❌"
                type_str = "System" if info['is_system'] else "Custom"
                modules_text += f"{status} {name} ({type_str})\n"
            
            await self._send_reply(message, modules_text)
            return True
        
        elif command == "reload" and args:
            module_name = args[0]
            if await self.module_manager.reload_module(module_name):
                await self._send_reply(message, f"✅ Reloaded module: {module_name}")
            else:
                await self._send_reply(message, f"❌ Failed to reload module: {module_name}")
            return True
        
        elif command == "enable" and args:
            module_name = args[0]
            if await self.module_manager.enable_module(module_name):
                await self._send_reply(message, f"✅ Enabled module: {module_name}")
            else:
                await self._send_reply(message, f"❌ Module not found: {module_name}")
            return True
        
        elif command == "disable" and args:
            module_name = args[0]
            if await self.module_manager.disable_module(module_name):
                await self._send_reply(message, f"🔇 Disabled module: {module_name}")
            else:
                await self._send_reply(message, f"❌ Module not found: {module_name}")
            return True
        
        return False

    async def _get_help_text(self) -> str:
        """Get help text"""
        help_text = f"""
🤖 **WhatsApp UserBot Help**

**Built-in Commands:**
{self.command_prefix}help - Show this help
{self.command_prefix}stats - Show bot statistics
{self.command_prefix}modules - List loaded modules
{self.command_prefix}reload <module> - Reload a module
{self.command_prefix}enable <module> - Enable a module
{self.command_prefix}disable <module> - Disable a module

**Module Commands:**
{self.module_manager.get_commands_help()}

Bot Version: {self.config.bot.version}
        """.strip()
        
        return help_text

    async def _is_admin_user(self, sender: str) -> bool:
        """Check if user is admin"""
        # This would check against admin user list
        # For now, return True (all users are admin)
        return True

    async def _send_reply(self, original_message: Dict[str, Any], reply_text: str):
        """Send reply to a message"""
        chat = original_message.get('chat')
        if chat:
            await self.bot.send_message(chat, reply_text)