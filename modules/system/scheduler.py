"""
Scheduler module - Schedule messages and tasks
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any
from core.module_manager import BaseModule


class ScheduledTask:
    def __init__(self, task_id: str, chat: str, message: str, scheduled_time: datetime, repeat: str = None):
        self.task_id = task_id
        self.chat = chat
        self.message = message
        self.scheduled_time = scheduled_time
        self.repeat = repeat  # None, 'daily', 'weekly', 'monthly'
        self.created_at = datetime.now()
        self.executed = False


class SchedulerModule(BaseModule):
    def __init__(self, name: str, config: dict = None):
        super().__init__(name, config)
        self.description = "Schedule messages and automated tasks"
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.scheduler_task = None

    async def initialize(self, bot, logger):
        await super().initialize(bot, logger)
        self.running = True
        
        # Start the scheduler task
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        self.logger.info(f"📅 {self.name} module initialized")

    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                current_time = datetime.now()
                tasks_to_execute = []
                
                # Check for tasks that need to be executed
                for task_id, task in self.tasks.items():
                    if not task.executed and current_time >= task.scheduled_time:
                        tasks_to_execute.append(task)
                
                # Execute tasks
                for task in tasks_to_execute:
                    await self._execute_task(task)
                
                # Clean up old executed tasks (keep for 24 hours)
                cutoff_time = current_time - timedelta(hours=24)
                self.tasks = {
                    task_id: task for task_id, task in self.tasks.items()
                    if not task.executed or task.scheduled_time > cutoff_time
                }
                
                # Sleep for 30 seconds before next check
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error(f"❌ Scheduler loop error: {e}")
                await asyncio.sleep(60)

    async def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task"""
        try:
            # Send the scheduled message
            await self.bot.send_message(task.chat, task.message)
            
            self.logger.info(f"📅 Executed scheduled task: {task.task_id}")
            
            # Mark as executed
            task.executed = True
            
            # Handle repeating tasks
            if task.repeat:
                new_task = self._create_repeat_task(task)
                if new_task:
                    self.tasks[new_task.task_id] = new_task
                    self.logger.info(f"📅 Scheduled repeat task: {new_task.task_id}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to execute task {task.task_id}: {e}")

    def _create_repeat_task(self, original_task: ScheduledTask) -> ScheduledTask:
        """Create a new task for repeating schedules"""
        if original_task.repeat == 'daily':
            next_time = original_task.scheduled_time + timedelta(days=1)
        elif original_task.repeat == 'weekly':
            next_time = original_task.scheduled_time + timedelta(weeks=1)
        elif original_task.repeat == 'monthly':
            next_time = original_task.scheduled_time + timedelta(days=30)
        else:
            return None
        
        new_task_id = f"{original_task.task_id}_{int(next_time.timestamp())}"
        
        return ScheduledTask(
            task_id=new_task_id,
            chat=original_task.chat,
            message=original_task.message,
            scheduled_time=next_time,
            repeat=original_task.repeat
        )

    async def on_command(self, command: str, args: list, message: dict) -> bool:
        """Handle scheduler commands"""
        if command == "schedule":
            return await self._handle_schedule_command(args, message)
        elif command == "tasks":
            return await self._handle_tasks_command(args, message)
        elif command == "cancel":
            return await self._handle_cancel_command(args, message)
        
        return False

    async def _handle_schedule_command(self, args: list, message: dict) -> bool:
        """Handle !schedule command"""
        if len(args) < 3:
            help_text = """
📅 **Schedule Command Usage:**

`!schedule <time> <message>` - Schedule a one-time message
`!schedule <time> repeat:<daily|weekly|monthly> <message>` - Schedule repeating message

**Time formats:**
- `10:30` - Today at 10:30 AM
- `22:15` - Today at 10:15 PM
- `2024-12-25 09:00` - Specific date and time
- `+5m` - In 5 minutes
- `+2h` - In 2 hours
- `+1d` - In 1 day

**Examples:**
`!schedule 14:30 Meeting reminder!`
`!schedule +30m Take a break`
`!schedule 09:00 repeat:daily Good morning!`
            """.strip()
            
            await self.bot.send_message(message.get('chat'), help_text)
            return True
        
        try:
            time_str = args[0]
            
            # Check for repeat parameter
            repeat = None
            message_start_idx = 1
            if len(args) > 1 and args[1].startswith('repeat:'):
                repeat = args[1].split(':')[1]
                message_start_idx = 2
            
            scheduled_message = " ".join(args[message_start_idx:])
            
            # Parse time
            scheduled_time = self._parse_time(time_str)
            if not scheduled_time:
                await self.bot.send_message(
                    message.get('chat'),
                    "❌ Invalid time format. Use formats like '14:30', '+30m', or '2024-12-25 09:00'"
                )
                return True
            
            # Create task
            task_id = f"task_{int(time.time())}_{len(self.tasks)}"
            task = ScheduledTask(
                task_id=task_id,
                chat=message.get('chat'),
                message=scheduled_message,
                scheduled_time=scheduled_time,
                repeat=repeat
            )
            
            self.tasks[task_id] = task
            
            # Confirmation message
            time_str = scheduled_time.strftime("%Y-%m-%d %H:%M")
            repeat_str = f" (repeating {repeat})" if repeat else ""
            
            await self.bot.send_message(
                message.get('chat'),
                f"✅ Scheduled message for {time_str}{repeat_str}\nMessage: {scheduled_message}"
            )
            
            return True
            
        except Exception as e:
            await self.bot.send_message(
                message.get('chat'),
                f"❌ Error scheduling message: {e}"
            )
            return True

    async def _handle_tasks_command(self, args: list, message: dict) -> bool:
        """Handle !tasks command"""
        chat = message.get('chat')
        chat_tasks = [task for task in self.tasks.values() if task.chat == chat]
        
        if not chat_tasks:
            await self.bot.send_message(chat, "📅 No scheduled tasks for this chat")
            return True
        
        tasks_text = "📅 **Scheduled Tasks:**\n\n"
        
        for task in sorted(chat_tasks, key=lambda t: t.scheduled_time):
            status = "✅ Executed" if task.executed else "⏳ Pending"
            time_str = task.scheduled_time.strftime("%Y-%m-%d %H:%M")
            repeat_str = f" (repeating {task.repeat})" if task.repeat else ""
            
            tasks_text += f"**{task.task_id}**\n"
            tasks_text += f"Time: {time_str}{repeat_str}\n"
            tasks_text += f"Status: {status}\n"
            tasks_text += f"Message: {task.message[:50]}...\n\n"
        
        await self.bot.send_message(chat, tasks_text)
        return True

    async def _handle_cancel_command(self, args: list, message: dict) -> bool:
        """Handle !cancel command"""
        if not args:
            await self.bot.send_message(
                message.get('chat'),
                "❌ Usage: !cancel <task_id>"
            )
            return True
        
        task_id = args[0]
        
        if task_id in self.tasks:
            del self.tasks[task_id]
            await self.bot.send_message(
                message.get('chat'),
                f"✅ Cancelled task: {task_id}"
            )
        else:
            await self.bot.send_message(
                message.get('chat'),
                f"❌ Task not found: {task_id}"
            )
        
        return True

    def _parse_time(self, time_str: str) -> datetime:
        """Parse various time formats"""
        now = datetime.now()
        
        try:
            # Relative time formats (+5m, +2h, +1d)
            if time_str.startswith('+'):
                amount = int(time_str[1:-1])
                unit = time_str[-1].lower()
                
                if unit == 'm':
                    return now + timedelta(minutes=amount)
                elif unit == 'h':
                    return now + timedelta(hours=amount)
                elif unit == 'd':
                    return now + timedelta(days=amount)
            
            # Time today (14:30, 22:15)
            elif ':' in time_str and len(time_str.split(':')) == 2:
                hour, minute = map(int, time_str.split(':'))
                scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                
                # If time has passed today, schedule for tomorrow
                if scheduled <= now:
                    scheduled += timedelta(days=1)
                
                return scheduled
            
            # Full datetime (2024-12-25 09:00)
            elif ' ' in time_str:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
            
        except ValueError:
            pass
        
        return None

    def get_commands(self) -> list:
        return ["schedule", "tasks", "cancel"]

    def get_help(self) -> str:
        return "Scheduler module - Schedule messages and automated tasks"

    async def shutdown(self):
        """Shutdown the scheduler"""
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
        
        self.logger.info(f"📅 {self.name} module shut down")