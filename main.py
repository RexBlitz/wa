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
    def __init__(self, debug_mode=False):
        self.bot = None
        self.config = None
        self.logger = None
        self.running = False
        self.debug_mode = debug_mode

    async def initialize(self):
        """Initialize the userbot with configuration and logging"""
        try:
            print_banner()
            self.config = Config()
            await self.config.load()
            self.logger = setup_logger(self.config)
            self.logger.info("🚀 Initializing Advanced WhatsApp UserBot...")
            self.logger.debug(f"Config loaded: {self.config.__dict__}")
            self.bot = WhatsAppUserBot(self.config, self.logger)
            await self.bot.initialize()
            self.logger.info("✅ Initialization complete")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ Failed to initialize: {e}", exc_info=True)
            else:
                print(f"❌ Failed to initialize: {e}")
            return False

    async def start(self):
        """Start the userbot"""
        if not await self.initialize():
            if self.debug_mode:
                self.logger.info("🔍 Running in debug mode, attempting minimal test")
                await self._run_debug_test()
            return False
            
        try:
            self.logger.info("🔥 Starting WhatsApp UserBot...")
            self.running = True
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
            await self.bot.start()
            while self.running:
                await asyncio.sleep(1)
        except Exception as e:
            self.logger.error(f"❌ Error running bot: {e}", exc_info=True)
            return False
        finally:
            await self.shutdown()

    async def _run_debug_test(self):
        """Run a minimal test to diagnose issues"""
        self.logger.info("🔍 Starting debug test...")
        try:
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=1, border=0, error_correction=qrcode.constants.ERROR_CORRECT_L)
            qr.add_data("test")
            qr.make(fit=True)
            self.logger.info("📱 Test ASCII QR Code:")
            qr.print_ascii(invert=True)
        except Exception as e:
            self.logger.error(f"❌ QR code test failed: {e}")

        try:
            from telegram import Bot
            bot = Bot(token=self.config.telegram.bot_token)
            await bot.send_message(
                chat_id=self.config.telegram.bridge_group_id,
                text="Debug test message from WhatsApp UserBot"
            )
            self.logger.info("✅ Telegram test message sent")
        except Exception as e:
            self.logger.error(f"❌ Telegram test failed: {e}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        if self.logger:
            self.logger.info(f"📝 Received signal {signum}, shutting down...")
        self.running = False

    async def shutdown(self):
        """Gracefully shutdown the bot"""
        if self.bot:
            self.logger.info("🛑 Shutting down bot...")
            await self.bot.shutdown()
        if self.logger:
            self.logger.info("👋 UserBot shutdown complete!")


async def main():
    """Main entry point"""
    debug_mode = "--debug" in sys.argv
    manager = UserBotManager(debug_mode=debug_mode)
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
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
