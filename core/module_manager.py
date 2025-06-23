"""
Module management system for WhatsApp UserBot
Handles loading, unloading, and management of system and custom modules
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import Dict, List, Any, Optional
import asyncio


class BaseModule:
    """Base class for all bot modules"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.enabled = True
        self.bot = None
        self.logger = None

    async def initialize(self, bot, logger):
        """Initialize the module"""
        self.bot = bot
        self.logger = logger

    async def on_message(self, message: Dict[str, Any]) -> bool:
        """Handle incoming message. Return True if message was handled."""
        return False

    async def on_command(self, command: str, args: List[str], message: Dict[str, Any]) -> bool:
        """Handle command. Return True if command was handled."""
        return False

    async def shutdown(self):
        """Cleanup when module is being unloaded"""
        pass

    def get_commands(self) -> List[str]:
        """Return list of commands this module handles"""
        return []

    def get_help(self) -> str:
        """Return help text for this module"""
        return f"Module: {self.name}"


class ModuleManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.loaded_modules = {}
        self.command_handlers = {}
        self.bot = None

    async def initialize(self, bot):
        """Initialize module manager"""
        self.bot = bot
        self.logger.info("🔧 Initializing module manager...")

    async def load_all_modules(self):
        """Load all modules from system and custom directories"""
        if not self.config.modules.auto_load:
            self.logger.info("📦 Module auto-loading disabled")
            return

        self.logger.info("📦 Loading modules...")

        # Load system modules
        await self._load_modules_from_directory(
            self.config.modules.system_modules_dir,
            is_system=True
        )

        # Load custom modules
        await self._load_modules_from_directory(
            self.config.modules.custom_modules_dir,
            is_system=False
        )

        self.logger.info(f"✅ Loaded {len(self.loaded_modules)} modules")

    async def _load_modules_from_directory(self, directory: str, is_system: bool = False):
        """Load modules from a directory"""
        module_dir = Path(directory)
        
        if not module_dir.exists():
            module_dir.mkdir(parents=True, exist_ok=True)
            return

        # Look for Python files
        for module_file in module_dir.glob("*.py"):
            if module_file.name.startswith("_"):
                continue  # Skip private modules
            
            module_name = module_file.stem
            
            # Skip if not in enabled list (if specified)
            if (self.config.modules.enabled_modules and 
                module_name not in self.config.modules.enabled_modules):
                continue

            try:
                await self._load_module(module_file, module_name, is_system)
            except Exception as e:
                self.logger.error(f"❌ Failed to load module {module_name}: {e}")

    async def _load_module(self, module_file: Path, module_name: str, is_system: bool):
        """Load a single module"""
        try:
            self.logger.debug(f"📥 Loading module: {module_name}")

            # Load module spec
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if not spec or not spec.loader:
                raise ImportError(f"Could not load spec for {module_name}")

            # Create and execute module
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find module class (should inherit from BaseModule)
            module_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseModule) and 
                    attr != BaseModule):
                    module_class = attr
                    break

            if not module_class:
                raise ImportError(f"No BaseModule subclass found in {module_name}")

            # Create module instance
            module_instance = module_class(module_name)
            
            # Initialize module
            await module_instance.initialize(self.bot, self.logger)

            # Store module
            self.loaded_modules[module_name] = {
                'instance': module_instance,
                'file': str(module_file),
                'is_system': is_system,
                'enabled': True
            }

            # Register command handlers
            for command in module_instance.get_commands():
                self.command_handlers[command] = module_instance

            self.logger.info(f"✅ Loaded {'system' if is_system else 'custom'} module: {module_name}")

        except Exception as e:
            self.logger.error(f"❌ Failed to load module {module_name}: {e}")
            raise

    async def unload_module(self, module_name: str) -> bool:
        """Unload a module"""
        if module_name not in self.loaded_modules:
            return False

        try:
            module_info = self.loaded_modules[module_name]
            module_instance = module_info['instance']

            # Call shutdown method
            await module_instance.shutdown()

            # Remove command handlers
            commands_to_remove = []
            for command, handler in self.command_handlers.items():
                if handler == module_instance:
                    commands_to_remove.append(command)
            
            for command in commands_to_remove:
                del self.command_handlers[command]

            # Remove from loaded modules
            del self.loaded_modules[module_name]

            self.logger.info(f"🗑️ Unloaded module: {module_name}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to unload module {module_name}: {e}")
            return False

    async def reload_module(self, module_name: str) -> bool:
        """Reload a module"""
        if module_name not in self.loaded_modules:
            return False

        try:
            module_info = self.loaded_modules[module_name]
            module_file = Path(module_info['file'])
            is_system = module_info['is_system']

            # Unload module
            await self.unload_module(module_name)

            # Reload module
            await self._load_module(module_file, module_name, is_system)

            self.logger.info(f"🔄 Reloaded module: {module_name}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to reload module {module_name}: {e}")
            return False

    async def handle_message(self, message: Dict[str, Any]) -> bool:
        """Pass message to all loaded modules"""
        handled = False
        
        for module_name, module_info in self.loaded_modules.items():
            if not module_info['enabled']:
                continue
            
            try:
                module_instance = module_info['instance']
                if await module_instance.on_message(message):
                    handled = True
                    
            except Exception as e:
                self.logger.error(f"❌ Error in module {module_name}: {e}")

        return handled

    async def handle_command(self, command: str, args: List[str], message: Dict[str, Any]) -> bool:
        """Handle a command"""
        if command in self.command_handlers:
            try:
                handler = self.command_handlers[command]
                return await handler.on_command(command, args, message)
            except Exception as e:
                self.logger.error(f"❌ Error handling command {command}: {e}")
                return False
        
        return False

    def get_loaded_modules(self) -> Dict[str, Dict]:
        """Get list of loaded modules"""
        return self.loaded_modules.copy()

    def get_module(self, module_name: str) -> Optional[BaseModule]:
        """Get a specific module instance"""
        if module_name in self.loaded_modules:
            return self.loaded_modules[module_name]['instance']
        return None

    async def enable_module(self, module_name: str) -> bool:
        """Enable a module"""
        if module_name in self.loaded_modules:
            self.loaded_modules[module_name]['enabled'] = True
            self.logger.info(f"✅ Enabled module: {module_name}")
            return True
        return False

    async def disable_module(self, module_name: str) -> bool:
        """Disable a module"""
        if module_name in self.loaded_modules:
            self.loaded_modules[module_name]['enabled'] = False
            self.logger.info(f"🔇 Disabled module: {module_name}")
            return True
        return False

    def get_commands_help(self) -> str:
        """Get help text for all commands"""
        help_text = "📋 **Available Commands:**\n\n"
        
        for module_name, module_info in self.loaded_modules.items():
            if not module_info['enabled']:
                continue
            
            module_instance = module_info['instance']
            commands = module_instance.get_commands()
            
            if commands:
                help_text += f"**{module_name}:**\n"
                help_text += f"{module_instance.get_help()}\n"
                help_text += f"Commands: {', '.join(commands)}\n\n"
        
        return help_text

    async def shutdown(self):
        """Shutdown all modules"""
        self.logger.info("🛑 Shutting down modules...")
        
        for module_name in list(self.loaded_modules.keys()):
            await self.unload_module(module_name)
        
        self.logger.info("✅ All modules shutdown complete")