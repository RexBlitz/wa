"""
Configuration management for the WhatsApp UserBot
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class BotConfig:
    name: str = "AdvancedUserBot"
    version: str = "2.0.0"
    debug: bool = True
    auto_start: bool = True
    session_timeout: int = 3600


@dataclass
class WhatsAppConfig:
    auth_method: str = "qr"
    phone_number: str = ""
    session_dir: str = "./sessions"
    headless: bool = False
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    implicit_wait: int = 10
    page_load_timeout: int = 30


@dataclass
class TelegramConfig:
    enabled: bool = True
    bot_token: str = ""
    bridge_group_id: str = ""
    admin_users: List[int] = field(default_factory=list)
    thread_per_user: bool = True
    forward_media: bool = True
    max_message_length: int = 4096


@dataclass
class DatabaseConfig:
    type: str = "mongodb"
    mongodb_connection_string: str = ""
    mongodb_database_name: str = "whatsapp_userbot"
    collections: Dict[str, str] = field(default_factory=lambda: {
        "messages": "messages",
        "users": "users", 
        "sessions": "sessions",
        "modules": "modules"
    })
    local_db_file: str = "./data/userbot.db"


@dataclass
class ModulesConfig:
    auto_load: bool = True
    system_modules_dir: str = "./modules/system"
    custom_modules_dir: str = "./modules/custom"
    enabled_modules: List[str] = field(default_factory=list)


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "./logs/userbot.log"
    max_size: str = "10MB"
    backup_count: int = 5
    console_output: bool = True


@dataclass
class SecurityConfig:
    rate_limit: int = 30
    blacklist: List[str] = field(default_factory=list)
    whitelist: List[str] = field(default_factory=list)
    admin_only_commands: bool = True


class Config:
    def __init__(self, config_file: str = "config.yaml"):
        self.config_file = config_file
        
        # Configuration sections
        self.bot = BotConfig()
        self.whatsapp = WhatsAppConfig()
        self.telegram = TelegramConfig()
        self.database = DatabaseConfig()
        self.modules = ModulesConfig()
        self.logging = LoggingConfig()
        self.security = SecurityConfig()

    async def load(self):
        """Load configuration from file and environment variables"""
        # Load environment variables
        load_dotenv()
        
        # Load config file if exists
        config_path = Path(self.config_file)
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            self._update_from_dict(config_data)
        
        # Override with environment variables
        self._load_from_env()
        
        # Create necessary directories
        self._create_directories()

    def _update_from_dict(self, config_data: Dict[str, Any]):
        """Update configuration from dictionary"""
        if 'bot' in config_data:
            self._update_dataclass(self.bot, config_data['bot'])
        
        if 'whatsapp' in config_data:
            self._update_dataclass(self.whatsapp, config_data['whatsapp'])
        
        if 'telegram' in config_data:
            self._update_dataclass(self.telegram, config_data['telegram'])
        
        if 'database' in config_data:
            self._update_dataclass(self.database, config_data['database'])
            if 'mongodb' in config_data['database']:
                self.database.mongodb_connection_string = config_data['database']['mongodb'].get('connection_string', self.database.mongodb_connection_string)
                self.database.mongodb_database_name = config_data['database']['mongodb'].get('database_name', self.database.mongodb_database_name)
                self.database.collections.update(config_data['database']['mongodb'].get('collections', {}))
        
        if 'modules' in config_data:
            self._update_dataclass(self.modules, config_data['modules'])
        
        if 'logging' in config_data:
            self._update_dataclass(self.logging, config_data['logging'])
        
        if 'security' in config_data:
            self._update_dataclass(self.security, config_data['security'])

    def _update_dataclass(self, obj, data: Dict[str, Any]):
        """Update dataclass object with dictionary data"""
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)

    def _load_from_env(self):
        """Load configuration from environment variables"""
        # WhatsApp
        if os.getenv('WHATSAPP_PHONE_NUMBER'):
            self.whatsapp.phone_number = os.getenv('WHATSAPP_PHONE_NUMBER')
        if os.getenv('WHATSAPP_SESSION_DIR'):
            self.whatsapp.session_dir = os.getenv('WHATSAPP_SESSION_DIR')
        
        # Telegram
        if os.getenv('TELEGRAM_BOT_TOKEN'):
            self.telegram.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if os.getenv('TELEGRAM_BRIDGE_GROUP_ID'):
            self.telegram.bridge_group_id = os.getenv('TELEGRAM_BRIDGE_GROUP_ID')
        if os.getenv('TELEGRAM_ADMIN_USERS'):
            admin_users = os.getenv('TELEGRAM_ADMIN_USERS').split(',')
            self.telegram.admin_users = [int(uid.strip()) for uid in admin_users if uid.strip().isdigit()]
        
        # Database
        if os.getenv('MONGODB_CONNECTION_STRING'):
            self.database.mongodb_connection_string = os.getenv('MONGODB_CONNECTION_STRING')
        if os.getenv('MONGODB_DATABASE_NAME'):
            self.database.mongodb_database_name = os.getenv('MONGODB_DATABASE_NAME')
        
        # Security
        if os.getenv('RATE_LIMIT'):
            self.security.rate_limit = int(os.getenv('RATE_LIMIT'))
        if os.getenv('DEBUG_MODE'):
            self.bot.debug = os.getenv('DEBUG_MODE').lower() == 'true'

    def _create_directories(self):
        """Create necessary directories"""
        directories = [
            self.whatsapp.session_dir,
            self.modules.system_modules_dir,
            self.modules.custom_modules_dir,
            "./logs",
            "./data",
            "./temp"
        ]
        
        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'bot': self.bot.__dict__,
            'whatsapp': self.whatsapp.__dict__,
            'telegram': self.telegram.__dict__,
            'database': self.database.__dict__,
            'modules': self.modules.__dict__,
            'logging': self.logging.__dict__,
            'security': self.security.__dict__
        }

    async def save(self, config_file: str = None):
        """Save configuration to file"""
        config_file = config_file or self.config_file
        
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, indent=2)