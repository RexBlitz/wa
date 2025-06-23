"""
Logging configuration for WhatsApp UserBot
"""

import logging
import logging.handlers
from pathlib import Path
import colorlog


def setup_logger(config):
    """Setup logging configuration"""
    
    # Create logs directory
    log_file = Path(config.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger('WhatsAppUserBot')
    logger.setLevel(getattr(logging, config.logging.level))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=_parse_size(config.logging.max_size),
        backupCount=config.logging.backup_count,
        encoding='utf-8'
    )
    
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler with colors
    if config.logging.console_output:
        console_handler = colorlog.StreamHandler()
        console_formatter = colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(levelname)s - %(message)s%(reset)s',
            datefmt='%H:%M:%S',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            }
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger


def _parse_size(size_str: str) -> int:
    """Parse size string like '10MB' to bytes"""
    if size_str.upper().endswith('MB'):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.upper().endswith('KB'):
        return int(size_str[:-2]) * 1024
    elif size_str.upper().endswith('GB'):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        return int(size_str)