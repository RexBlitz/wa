"""
Database management for WhatsApp UserBot
Supports both MongoDB and local database options
"""

import asyncio
import json
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False


class DatabaseManager:
    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.client = None
        self.db = None
        self.sqlite_conn = None

    async def initialize(self):
        """Initialize database connection"""
        if self.config.database.type == "mongodb" and MONGODB_AVAILABLE:
            await self._init_mongodb()
        else:
            await self._init_sqlite()

    async def _init_mongodb(self):
        """Initialize MongoDB connection"""
        try:
            if not self.config.database.mongodb_connection_string:
                self.logger.warning("📦 MongoDB connection string not configured, using local SQLite")
                await self._init_sqlite()
                return
            
            self.logger.info("📦 Connecting to MongoDB...")
            
            self.client = AsyncIOMotorClient(self.config.database.mongodb_connection_string)
            self.db = self.client[self.config.database.mongodb_database_name]
            
            # Test connection
            await self.client.admin.command('ping')
            
            # Create indexes
            await self._create_mongodb_indexes()
            
            self.logger.info("✅ MongoDB connected successfully")
            
        except Exception as e:
            self.logger.error(f"❌ MongoDB connection failed: {e}")
            self.logger.info("📦 Falling back to local SQLite database")
            await self._init_sqlite()

    async def _init_sqlite(self):
        """Initialize SQLite database"""
        try:
            self.logger.info("📦 Initializing local SQLite database...")
            
            db_path = Path(self.config.database.local_db_file)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self.sqlite_conn.row_factory = sqlite3.Row
            
            # Create tables
            await self._create_sqlite_tables()
            
            self.logger.info("✅ SQLite database initialized")
            
        except Exception as e:
            self.logger.error(f"❌ SQLite initialization failed: {e}")
            raise

    async def _create_mongodb_indexes(self):
        """Create MongoDB indexes"""
        try:
            # Messages collection indexes
            messages_collection = self.db[self.config.database.collections['messages']]
            await messages_collection.create_index([("timestamp", -1)])
            await messages_collection.create_index([("sender", 1), ("chat", 1)])
            await messages_collection.create_index([("message_id", 1)], unique=True)
            
            # Users collection indexes
            users_collection = self.db[self.config.database.collections['users']]
            await users_collection.create_index([("phone", 1)], unique=True)
            await users_collection.create_index([("last_seen", -1)])
            
        except Exception as e:
            self.logger.debug(f"Index creation warning: {e}")

    async def _create_sqlite_tables(self):
        """Create SQLite tables"""
        tables = [
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender TEXT,
                chat TEXT,
                text TEXT,
                timestamp REAL,
                is_outgoing BOOLEAN,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                name TEXT,
                last_seen DATETIME,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_key TEXT UNIQUE,
                data TEXT,
                expires_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                enabled BOOLEAN DEFAULT 1,
                config TEXT,
                last_loaded DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
        
        cursor = self.sqlite_conn.cursor()
        for table_sql in tables:
            cursor.execute(table_sql)
        
        self.sqlite_conn.commit()

    # Message operations
    async def save_message(self, message_data: Dict[str, Any]):
        """Save message to database"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['messages']]
                await collection.insert_one(message_data)
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO messages 
                    (message_id, sender, chat, text, timestamp, is_outgoing, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_data.get('id'),
                    message_data.get('sender'),
                    message_data.get('chat'),
                    message_data.get('text'),
                    message_data.get('timestamp'),
                    message_data.get('is_outgoing', False),
                    json.dumps(message_data.get('metadata', {}))
                ))
                self.sqlite_conn.commit()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to save message: {e}")

    async def get_messages(self, chat: str = None, sender: str = None, limit: int = 100) -> List[Dict]:
        """Get messages from database"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['messages']]
                query = {}
                if chat:
                    query['chat'] = chat
                if sender:
                    query['sender'] = sender
                
                cursor = collection.find(query).sort('timestamp', -1).limit(limit)
                return await cursor.to_list(length=limit)
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                query = "SELECT * FROM messages WHERE 1=1"
                params = []
                
                if chat:
                    query += " AND chat = ?"
                    params.append(chat)
                if sender:
                    query += " AND sender = ?"
                    params.append(sender)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                return [dict(row) for row in rows]
                
        except Exception as e:
            self.logger.error(f"❌ Failed to get messages: {e}")
            return []

    # User operations
    async def save_user(self, user_data: Dict[str, Any]):
        """Save user to database"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['users']]
                await collection.update_one(
                    {'phone': user_data.get('phone')},
                    {'$set': user_data},
                    upsert=True
                )
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO users (phone, name, last_seen, metadata)
                    VALUES (?, ?, ?, ?)
                """, (
                    user_data.get('phone'),
                    user_data.get('name'),
                    user_data.get('last_seen'),
                    json.dumps(user_data.get('metadata', {}))
                ))
                self.sqlite_conn.commit()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to save user: {e}")

    async def get_user(self, phone: str) -> Optional[Dict]:
        """Get user by phone number"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['users']]
                return await collection.find_one({'phone': phone})
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("SELECT * FROM users WHERE phone = ?", (phone,))
                row = cursor.fetchone()
                return dict(row) if row else None
                
        except Exception as e:
            self.logger.error(f"❌ Failed to get user: {e}")
            return None

    # Session operations
    async def save_session(self, session_key: str, data: Dict[str, Any], expires_at: datetime = None):
        """Save session data"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['sessions']]
                await collection.update_one(
                    {'session_key': session_key},
                    {
                        '$set': {
                            'session_key': session_key,
                            'data': data,
                            'expires_at': expires_at,
                            'updated_at': datetime.now()
                        }
                    },
                    upsert=True
                )
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO sessions (session_key, data, expires_at)
                    VALUES (?, ?, ?)
                """, (session_key, json.dumps(data), expires_at))
                self.sqlite_conn.commit()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to save session: {e}")

    async def get_session(self, session_key: str) -> Optional[Dict]:
        """Get session data"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['sessions']]
                return await collection.find_one({'session_key': session_key})
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("SELECT * FROM sessions WHERE session_key = ?", (session_key,))
                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    data['data'] = json.loads(data['data'])
                    return data
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Failed to get session: {e}")
            return None

    # Module operations
    async def save_module_config(self, module_name: str, config: Dict[str, Any], enabled: bool = True):
        """Save module configuration"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['modules']]
                await collection.update_one(
                    {'name': module_name},
                    {
                        '$set': {
                            'name': module_name,
                            'config': config,
                            'enabled': enabled,
                            'last_loaded': datetime.now()
                        }
                    },
                    upsert=True
                )
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO modules (name, enabled, config, last_loaded)
                    VALUES (?, ?, ?, ?)
                """, (module_name, enabled, json.dumps(config), datetime.now()))
                self.sqlite_conn.commit()
                
        except Exception as e:
            self.logger.error(f"❌ Failed to save module config: {e}")

    async def get_module_config(self, module_name: str) -> Optional[Dict]:
        """Get module configuration"""
        try:
            if self.db:  # MongoDB
                collection = self.db[self.config.database.collections['modules']]
                return await collection.find_one({'name': module_name})
            else:  # SQLite
                cursor = self.sqlite_conn.cursor()
                cursor.execute("SELECT * FROM modules WHERE name = ?", (module_name,))
                row = cursor.fetchone()
                if row:
                    data = dict(row)
                    data['config'] = json.loads(data['config'])
                    return data
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Failed to get module config: {e}")
            return None

    async def close(self):
        """Close database connections"""
        if self.client:
            self.client.close()
        if self.sqlite_conn:
            self.sqlite_conn.close()
        
        self.logger.info("📦 Database connections closed")