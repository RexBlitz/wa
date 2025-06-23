#!/usr/bin/env python3
"""
Advanced WhatsApp Userbot
A sophisticated WhatsApp automation bot with Telegram bridge and modular architecture
"""

import asyncio
import sys
import signal
import logging
from pathlib import Path

from core.bot import WhatsAppUserBot
from core.config import Config
from core.logger import setup_logger
from utils.banner import print_banner


class UserBotManager:
    def __init__(self):
        self.bot = None
        self.config = None
        self.logger = None
        self.running = False

    async def initialize(self):
        """Initialize the userbot with configuration and logging"""
        try:
            # Print welcome banner
            print_banner()
            
            # Load configuration
            self.config = Config()
            await self.config.load()
            
            # Setup logging
            self.logger = setup_logger(self.config)
            self.logger.info("🚀 Initializing Advanced WhatsApp UserBot...")
            
            # Initialize bot
            self.bot = WhatsAppUserBot(self.config, self.logger)
            await self.bot.initialize()
            
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Failed to initialize: {e}")
            else:
                print(f"❌ Failed to initialize: {e}")
            return False

    async def start(self):
        """Start the userbot"""
        if not await self.initialize():
            return False
            
        try:
            self.logger.info("🔥 Starting WhatsApp UserBot...")
            self.running = True
            
            # Setup signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            
            # Start the bot
            await self.bot.start()
            
            # Keep the bot running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"❌ Error running bot: {e}")
            return False
        finally:
            await self.shutdown()

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"📝 Received signal {signum}, shutting down gracefully...")
        self.running = False

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        if self.bot:
            self.logger.info("🛑 Shutting down bot...")
            await self.bot.shutdown()
        
        self.logger.info("👋 UserBot shutdown complete!")


async def main():
    """Main entry point"""
    manager = UserBotManager()
    
    try:
        success = await manager.start()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Ensure we're using the right event loop policy on Windows
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # Run the bot
    asyncio.run(main())