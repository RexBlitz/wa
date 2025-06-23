"""
Auto Reply module - Automated responses to specific keywords
"""

import re
import asyncio
from typing import Dict, List
from core.module_manager import BaseModule


class AutoReplyModule(BaseModule):
    def __init__(self, name: str, config: dict = None):
        super().__init__(name, config)
        self.description = "Automated replies to specific keywords or patterns"
        
        # Default auto-reply rules
        self.reply_rules = {
            r'hello|hi|hey': [
                "Hello! 👋 How can I help you?",
                "Hi there! 😊",
                "Hey! What's up?"
            ],
            r'how are you|how r u': [
                "I'm doing great! Thanks for asking 😊",
                "All good here! How about you?",
                "I'm fantastic! 🚀"
            ],
            r'thank you|thanks': [
                "You're welcome! 😊",
                "No problem!",
                "Happy to help! 👍"
            ],
            r'bye|goodbye|see you': [
                "Goodbye! 👋",
                "See you later! 😊",
                "Take care! 🌟"
            ],
            r'help|support': [
                "I'm here to help! What do you need assistance with?",
                "How can I assist you today?",
                "Let me know what you need help with! 💪"
            ]
        }
        
        # Load custom rules from config
        if config and 'rules' in config:
            self.reply_rules.update(config['rules'])

    async def initialize(self, bot, logger):
        await super().initialize(bot, logger)
        self.logger.info(f"🤖 {self.name} module initialized with {len(self.reply_rules)} reply rules")

    async def on_message(self, message: dict) -> bool:
        """Handle incoming messages and check for auto-reply triggers"""
        # Skip outgoing messages
        if message.get('is_outgoing', False):
            return False
        
        text = message.get('text', '').strip().lower()
        
        if not text:
            return False
        
        # Check each rule
        for pattern, replies in self.reply_rules.items():
            if re.search(pattern, text, re.IGNORECASE):
                # Choose a random reply
                import random
                reply = random.choice(replies)
                
                # Add a small delay to make it more natural
                await asyncio.sleep(1)
                
                # Send the reply
                await self.bot.send_message(message.get('chat'), reply)
                
                self.logger.info(f"🤖 Auto-replied to '{text[:30]}...' with '{reply[:30]}...'")
                return True
        
        return False

    async def on_command(self, command: str, args: list, message: dict) -> bool:
        """Handle commands"""
        if command == "autoreply":
            if not args:
                # Show current rules
                rules_text = "🤖 **Auto-Reply Rules:**\n\n"
                for pattern, replies in self.reply_rules.items():
                    rules_text += f"Pattern: `{pattern}`\n"
                    rules_text += f"Replies: {len(replies)} variations\n\n"
                
                await self.bot.send_message(message.get('chat'), rules_text)
                return True
            
            elif args[0] == "add" and len(args) >= 3:
                # Add new rule: !autoreply add "pattern" "reply"
                pattern = args[1]
                reply = " ".join(args[2:])
                
                if pattern not in self.reply_rules:
                    self.reply_rules[pattern] = []
                
                self.reply_rules[pattern].append(reply)
                
                await self.bot.send_message(
                    message.get('chat'),
                    f"✅ Added auto-reply rule:\nPattern: `{pattern}`\nReply: `{reply}`"
                )
                return True
            
            elif args[0] == "remove" and len(args) >= 2:
                # Remove rule: !autoreply remove "pattern"
                pattern = args[1]
                
                if pattern in self.reply_rules:
                    del self.reply_rules[pattern]
                    await self.bot.send_message(
                        message.get('chat'),
                        f"✅ Removed auto-reply rule: `{pattern}`"
                    )
                else:
                    await self.bot.send_message(
                        message.get('chat'),
                        f"❌ Rule not found: `{pattern}`"
                    )
                return True
            
            else:
                help_text = """
🤖 **Auto-Reply Commands:**

`!autoreply` - Show current rules
`!autoreply add <pattern> <reply>` - Add new rule
`!autoreply remove <pattern>` - Remove rule

**Examples:**
`!autoreply add "good morning" "Good morning! Have a great day!"`
`!autoreply remove "hello"`
                """.strip()
                
                await self.bot.send_message(message.get('chat'), help_text)
                return True
        
        return False

    def get_commands(self) -> list:
        return ["autoreply"]

    def get_help(self) -> str:
        return "Auto-Reply module - Automatically responds to specific keywords and patterns"

    async def shutdown(self):
        """Save rules when shutting down"""
        # This could save rules to database or config file
        self.logger.info(f"🤖 {self.name} module shutting down...")