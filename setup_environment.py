#!/usr/bin/env python3
"""
Environment setup script for WhatsApp UserBot
Handles system-specific setup and dependency installation
"""

import os
import sys
import platform
import subprocess
import logging
from pathlib import Path


def setup_logging():
    """Setup basic logging for setup script"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    return logging.getLogger(__name__)


def detect_system():
    """Detect system information"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    is_arm = 'arm' in machine or 'aarch64' in machine
    
    return {
        'system': system,
        'machine': machine,
        'is_arm': is_arm,
        'python_version': sys.version_info
    }


def run_command(command, logger, check=True):
    """Run shell command with logging"""
    logger.info(f"🔧 Running: {command}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=check
        )
        
        if result.stdout:
            logger.info(f"✅ Output: {result.stdout.strip()}")
        
        return result.returncode == 0
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Command failed: {e}")
        if e.stderr:
            logger.error(f"Error: {e.stderr}")
        return False


def install_system_dependencies(system_info, logger):
    """Install system-level dependencies"""
    logger.info("📦 Installing system dependencies...")
    
    if system_info['system'] == 'linux':
        # Update package list
        run_command("sudo apt update", logger, check=False)
        
        # Install basic dependencies
        dependencies = [
            "wget", "curl", "unzip", "gnupg2", "software-properties-common",
            "apt-transport-https", "ca-certificates", "python3-pip",
            "python3-dev", "build-essential", "libssl-dev", "libffi-dev"
        ]
        
        for dep in dependencies:
            run_command(f"sudo apt install -y {dep}", logger, check=False)
        
        return True
    
    elif system_info['system'] == 'darwin':  # macOS
        logger.info("🍎 macOS detected - please install dependencies manually:")
        logger.info("  brew install python3 wget curl")
        return True
    
    else:
        logger.warning(f"⚠️ Unsupported system: {system_info['system']}")
        return False


def install_chrome(system_info, logger):
    """Install Chrome browser"""
    logger.info("🌐 Installing Chrome browser...")
    
    if system_info['system'] == 'linux':
        if system_info['is_arm']:
            # ARM64 Chrome installation
            commands = [
                "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -",
                "echo 'deb [arch=arm64] http://dl.google.com/linux/chrome/deb/ stable main' | sudo tee /etc/apt/sources.list.d/google-chrome.list",
                "sudo apt update",
                "sudo apt install -y google-chrome-stable"
            ]
        else:
            # x86_64 Chrome installation
            commands = [
                "wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -",
                "echo 'deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main' | sudo tee /etc/apt/sources.list.d/google-chrome.list",
                "sudo apt update",
                "sudo apt install -y google-chrome-stable"
            ]
        
        for cmd in commands:
            if not run_command(cmd, logger, check=False):
                logger.warning(f"⚠️ Command may have failed: {cmd}")
        
        # Verify installation
        if run_command("google-chrome --version", logger, check=False):
            logger.info("✅ Chrome installed successfully")
            return True
        else:
            logger.error("❌ Chrome installation failed")
            return False
    
    return False


def install_python_dependencies(logger):
    """Install Python dependencies"""
    logger.info("🐍 Installing Python dependencies...")
    
    # Upgrade pip first
    run_command(f"{sys.executable} -m pip install --upgrade pip", logger)
    
    # Install requirements
    if Path("requirements.txt").exists():
        success = run_command(f"{sys.executable} -m pip install -r requirements.txt", logger)
        if success:
            logger.info("✅ Python dependencies installed successfully")
            return True
        else:
            logger.error("❌ Failed to install Python dependencies")
            return False
    else:
        logger.error("❌ requirements.txt not found")
        return False


def create_directories(logger):
    """Create necessary directories"""
    logger.info("📁 Creating directories...")
    
    directories = [
        "sessions",
        "logs", 
        "data",
        "temp",
        "drivers_cache",
        "modules/system",
        "modules/custom"
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Created: {directory}")
    
    return True


def setup_environment_file(logger):
    """Setup environment file"""
    logger.info("⚙️ Setting up environment file...")
    
    env_example = Path(".env.example")
    env_file = Path(".env")
    
    if env_example.exists() and not env_file.exists():
        import shutil
        shutil.copy(env_example, env_file)
        logger.info("✅ Created .env file from .env.example")
        logger.info("📝 Please edit .env file with your configuration")
        return True
    elif env_file.exists():
        logger.info("✅ .env file already exists")
        return True
    else:
        logger.warning("⚠️ .env.example not found")
        return False


def main():
    """Main setup function"""
    logger = setup_logging()
    
    logger.info("🚀 Starting WhatsApp UserBot environment setup...")
    
    # Detect system
    system_info = detect_system()
    logger.info(f"🖥️ System: {system_info['system']} {system_info['machine']}")
    logger.info(f"🐍 Python: {sys.version}")
    logger.info(f"🔧 ARM64: {system_info['is_arm']}")
    
    # Check Python version
    if system_info['python_version'] < (3, 8):
        logger.error("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    success_steps = []
    
    # Install system dependencies
    if install_system_dependencies(system_info, logger):
        success_steps.append("System dependencies")
    
    # Install Chrome
    if install_chrome(system_info, logger):
        success_steps.append("Chrome browser")
    
    # Install Python dependencies
    if install_python_dependencies(logger):
        success_steps.append("Python dependencies")
    
    # Create directories
    if create_directories(logger):
        success_steps.append("Directory structure")
    
    # Setup environment file
    if setup_environment_file(logger):
        success_steps.append("Environment configuration")
    
    # Summary
    logger.info("=" * 50)
    logger.info("🎉 Setup Summary:")
    for step in success_steps:
        logger.info(f"  ✅ {step}")
    
    if len(success_steps) >= 4:
        logger.info("🚀 Setup completed successfully!")
        logger.info("📝 Next steps:")
        logger.info("  1. Edit .env file with your configuration")
        logger.info("  2. Edit config.yaml if needed")
        logger.info("  3. Run: python main.py")
    else:
        logger.warning("⚠️ Setup completed with some issues")
        logger.info("📝 Please check the logs above and resolve any issues")
    
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
