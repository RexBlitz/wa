# 🚀 Advanced WhatsApp UserBot with Telegram Bridge

A sophisticated WhatsApp automation bot built in Python with advanced features, modular architecture, and Telegram integration.

## ✨ Features

### 🔥 Core Features
- **Advanced WhatsApp automation** with QR code and phone number login
- **Independent core functionality** that works without modules
- **Selenium-based** WhatsApp Web integration
- **Asynchronous architecture** for optimal performance
- **Comprehensive logging** with rotation and colored output
- **Session management** with automatic restoration

### 🔗 Telegram Bridge
- **Bidirectional message forwarding** between WhatsApp and Telegram
- **Thread-based conversations** - separate thread per WhatsApp user
- **Reply from Telegram** - respond to WhatsApp messages via Telegram
- **Admin controls** with user management
- **Media forwarding support**

### 📦 Modular Architecture
- **System modules** - Core bot functionality
- **Custom modules** - User-created extensions
- **Hot reloading** - Reload modules without restarting
- **Module management** - Enable/disable modules on the fly
- **Command system** - Extensible command framework

### 🗄️ Database Support
- **MongoDB** - Cloud or local MongoDB support
- **SQLite** - Local database fallback
- **Automatic migrations** and indexing
- **Session storage** and user management
- **Message archiving** and search

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- Chrome/Chromium browser
- MongoDB (optional, SQLite used as fallback)

### Quick Setup

1. **Clone and setup:**
```bash
git clone <your-repo>
cd whatsapp-userbot
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Configure bot settings:**
```bash
# Edit config.yaml with your preferences
nano config.yaml
```

4. **Run the bot:**
```bash
python main.py
```

## ⚙️ Configuration

### Basic Configuration (`config.yaml`)

```yaml
# WhatsApp Settings
whatsapp:
  auth_method: "qr"  # or "phone"
  headless: false    # Set true for headless mode
  session_dir: "./sessions"

# Telegram Bridge
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN"
  bridge_group_id: "YOUR_GROUP_ID"
  admin_users: [123456789]

# Database
database:
  type: "mongodb"  # or "local"
  mongodb:
    connection_string: "mongodb://localhost:27017/"
```

### Environment Variables (`.env`)

```bash
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_BRIDGE_GROUP_ID=-1001234567890
TELEGRAM_ADMIN_USERS=123456789,987654321

# MongoDB Configuration  
MONGODB_CONNECTION_STRING=mongodb://localhost:27017/
MONGODB_DATABASE_NAME=whatsapp_userbot
```

## 🚀 Usage

### Starting the Bot

1. **QR Code Authentication:**
   - Run `python main.py`
   - Scan the displayed QR code with WhatsApp mobile app
   - Bot will start automatically after authentication

2. **Phone Number Authentication:**
   - Set `auth_method: "phone"` in config
   - Provide phone number in configuration
   - Follow authentication prompts

### Built-in Commands

```bash
!help          # Show help information
!stats         # Display bot statistics  
!modules       # List loaded modules
!reload <name> # Reload a specific module
!enable <name> # Enable a module
!disable <name># Disable a module
```

### System Modules

#### 🔊 Echo Module
- **Commands:** `!echo <message>`
- **Function:** Echoes back your messages
- **Usage:** `!echo Hello World` → `🔊 Echo: Hello World`

#### 🤖 Auto-Reply Module
- **Function:** Automatic responses to keywords
- **Commands:** 
  - `!autoreply` - Show current rules
  - `!autoreply add <pattern> <reply>` - Add new rule
  - `!autoreply remove <pattern>` - Remove rule

#### 📅 Scheduler Module
- **Function:** Schedule messages and tasks
- **Commands:**
  - `!schedule <time> <message>` - Schedule one-time message
  - `!schedule <time> repeat:daily <message>` - Repeating message
  - `!tasks` - List scheduled tasks
  - `!cancel <task_id>` - Cancel a task

## 🔧 Creating Custom Modules

### Module Template

```python
from core.module_manager import BaseModule

class MyCustomModule(BaseModule):
    def __init__(self, name: str, config: dict = None):
        super().__init__(name, config)
        self.description = "My custom module"

    async def initialize(self, bot, logger):
        await super().initialize(bot, logger)
        self.logger.info(f"🔧 {self.name} module initialized")

    async def on_message(self, message: dict) -> bool:
        """Handle incoming messages"""
        text = message.get('text', '').strip()
        
        if text.lower() == "hello module":
            await self.bot.send_message(
                message.get('chat'), 
                "Hello from custom module!"
            )
            return True
        
        return False

    async def on_command(self, command: str, args: list, message: dict) -> bool:
        """Handle commands"""
        if command == "mycommand":
            await self.bot.send_message(
                message.get('chat'),
                "Custom command executed!"
            )
            return True
        
        return False

    def get_commands(self) -> list:
        return ["mycommand"]

    def get_help(self) -> str:
        return "My custom module - Does custom things"
```

### Installing Custom Modules

1. Create your module file in `modules/custom/`
2. Ensure it inherits from `BaseModule`
3. Bot will auto-load it on next restart
4. Or use `!reload <module_name>` to load without restart

## 🔗 Telegram Bridge Setup

### 1. Create Telegram Bot
- Message [@BotFather](https://t.me/botfather) on Telegram
- Create new bot with `/newbot`
- Get your bot token

### 2. Setup Bridge Group
- Create a Telegram group
- Add your bot to the group
- Make bot an admin
- Get group ID (use [@userinfobot](https://t.me/userinfobot))

### 3. Configure Bridge
```yaml
telegram:
  enabled: true
  bot_token: "YOUR_BOT_TOKEN" 
  bridge_group_id: "YOUR_GROUP_ID"
  admin_users: [YOUR_USER_ID]
  thread_per_user: true
```

### 4. Bridge Features
- **Message Forwarding:** WhatsApp → Telegram automatically
- **Reply Support:** Reply to forwarded messages in Telegram
- **Thread Organization:** Each WhatsApp user gets own thread
- **Admin Commands:** Manage bot from Telegram
- **Media Support:** Forward images, documents, etc.

## 📊 Database Schema

### MongoDB Collections

#### Messages Collection
```javascript
{
  _id: ObjectId,
  message_id: String,
  sender: String,
  chat: String, 
  text: String,
  timestamp: Date,
  is_outgoing: Boolean,
  metadata: Object
}
```

#### Users Collection
```javascript
{
  _id: ObjectId,
  phone: String,
  name: String,
  last_seen: Date,
  metadata: Object
}
```

## 🚦 Advanced Features

### Rate Limiting
- Configurable message rate limits
- Per-user tracking
- Automatic throttling

### Security
- Blacklist/whitelist support
- Admin-only commands
- Message filtering

### Session Management
- Automatic session restoration
- Session timeout handling
- Multi-device support

### Error Handling
- Comprehensive error logging
- Automatic recovery
- Graceful degradation

## 🛡️ Security Best Practices

1. **Environment Variables:** Store sensitive data in `.env`
2. **Admin Controls:** Limit admin access appropriately
3. **Rate Limiting:** Configure appropriate limits
4. **Whitelisting:** Use whitelist for production
5. **Logging:** Monitor logs for suspicious activity

## 🔧 Troubleshooting

### Common Issues

#### QR Code Not Appearing
- Ensure Chrome/Chromium is installed
- Check if headless mode is disabled
- Verify display capabilities

#### Authentication Fails
- Clear session directory
- Try different auth method
- Check WhatsApp Web compatibility

#### Telegram Bridge Not Working
- Verify bot token and permissions
- Ensure bot is admin in bridge group
- Check network connectivity

#### Module Loading Errors
- Check Python syntax in modules
- Verify module inherits from BaseModule
- Check logs for specific errors

### Debug Mode
```yaml
bot:
  debug: true
  
logging:
  level: "DEBUG"
```

## 📈 Performance Optimization

### For High Volume
- Use MongoDB for better performance
- Enable headless mode
- Increase rate limits carefully
- Monitor resource usage

### For Low Resources
- Use SQLite database
- Disable unnecessary modules
- Reduce logging level
- Limit message history

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This bot is for educational and personal use only. Users are responsible for compliance with WhatsApp's Terms of Service and local laws. Use at your own risk.

## 🆘 Support

- **Issues:** [GitHub Issues](https://github.com/your-repo/issues)
- **Discussions:** [GitHub Discussions](https://github.com/your-repo/discussions)
- **Documentation:** [Wiki](https://github.com/your-repo/wiki)

---

## 🏆 Why This Bot is Advanced

### Beyond GitHub Alternatives

1. **Architecture Excellence**
   - True async/await implementation
   - Modular plugin system
   - Clean separation of concerns
   - Production-ready error handling

2. **Telegram Integration**
   - Bidirectional bridge functionality
   - Thread-based organization
   - Admin control system
   - Media forwarding support

3. **Database Flexibility**
   - Multiple database backends
   - Automatic migrations
   - Efficient indexing
   - Data persistence

4. **Enterprise Features**
   - Comprehensive logging
   - Session management
   - Security controls
   - Performance monitoring

5. **Developer Experience**
   - Hot module reloading
   - Extensive documentation
   - Template system
   - Debug capabilities

This bot represents a significant advancement over typical GitHub WhatsApp bots, offering enterprise-grade features with user-friendly operation.