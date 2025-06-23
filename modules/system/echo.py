"""
Echo module - Simple example system module
Echoes back messages with a prefix
"""

import asyncio
from core.module_manager import BaseModule


class EchoModule(BaseModule):
    def __init__(self, name: str, config: dict = None):
        super().__init__(name, config)
        self.description = "Echo back messages with a prefix"

    async def initialize(self, bot, logger):
        await super().initialize(bot, logger)
        self.logger.info(f"🔊 {self.name} module initialized")

    async def on_message(self, message: dict) -> bool:
        """Handle incoming messages"""
        text = message.get('text', '').strip()
        
        # Only respond to messages that start with "echo"
        if text.lower().startswith('echo '):
            echo_text = text[5:]  # Remove "echo " prefix
            
            if echo_text:
                response = f"🔊 Echo: {echo_text}"
                await self.bot.send_message(message.get('chat'), response)
                
                self.logger.info(f"🔊 Echoed message: {echo_text}")
                return True
        
        return False

    async def on_command(self, command: str, args: list, message: dict) -> bool:
        """Handle commands"""
        if command == "echo":
            if args:
                echo_text = " ".join(args)
                response = f"🔊 Echo: {echo_text}"
                await self.bot.send_message(message.get('chat'), response)
                return True
            else:
                await self.bot.send_message(
                    message.get('chat'), 
                    "Usage: !echo <message>"
                )
                return True
        
        return False

    def get_commands(self) -> list:
        return ["echo"]

    def get_help(self) -> str:
        return "Echo module - Repeats your messages back to you"