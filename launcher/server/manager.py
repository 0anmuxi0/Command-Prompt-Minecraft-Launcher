# 服务器管理器 - 核心编排器（单服务器版）

from __future__ import annotations
import os
import time

from ..logger import log_info, log_warn, log_error
from ..config import ConfigManager
from .instance import ServerInfo
from .process import run_server_foreground
from .backup import BackupManager
from .scheduler import TaskScheduler, ScheduleTask
from .java import JavaInfo, scan_java


class ServerManager:
    """服务器管理器 - 单服务器"""
    
    def __init__(self):
        self.config = ConfigManager()
        self.backup = BackupManager()
        self.scheduler = TaskScheduler()
        self._java_cache: list[JavaInfo] = []
        self._java_cache_time = 0
        self.scheduler.set_executor(self._execute_scheduled_task)
        self._running = False

    # ========== 服务器配置 ==========

    def get_config(self) -> ServerInfo:
        """获取当前服务器配置"""
        return self.config.get_server_config_obj()

    def save_config(self, server: ServerInfo):
        """保存服务器配置"""
        self.config.set_server_config_obj(server)

    # ========== 服务器生命周期 ==========

    def run_foreground(self) -> tuple[bool, str]:
        """前台启动服务器，阻塞直到退出"""
        server = self.get_config()
        if not server.base or not os.path.isdir(server.base):
            msg = f"目录不存在或未设置: {server.base}"
            if os.path.isdir(server.base):
                jars = [f for f in os.listdir(server.base) if f.endswith(".jar")]
                if jars:
                    msg += f"\n目录中有 JAR: {', '.join(jars)}"
            return False, msg
        if not os.path.exists(server.core_path):
            msg = f"核心文件不存在: {server.core_path}"
            if os.path.isdir(server.base):
                jars = [f for f in os.listdir(server.base) if f.endswith(".jar")]
                if jars:
                    msg += f"\n目录中有这些 JAR: {', '.join(jars)}"
            return False, msg
        self._running = True
        code = run_server_foreground(server)
        self._running = False
        return True, f"服务器已停止 (退出码: {code})"

    def is_running(self) -> bool:
        return self._running

    # ========== 备份 ==========

    def create_backup(self) -> tuple[bool, str]:
        return self.backup.create_backup(self.get_config())

    def list_backups(self) -> list[dict]:
        return self.backup.list_backups(self.get_config())

    def delete_backup(self, filename: str) -> bool:
        return self.backup.delete_backup(self.get_config(), filename)

    # ========== Java ==========

    def get_java_list(self, force_refresh: bool = False) -> list[JavaInfo]:
        now = time.time()
        if force_refresh or (now - self._java_cache_time) > 60:
            self._java_cache = scan_java()
            self._java_cache_time = now
            self.config.set_java_cache([j.to_dict() for j in self._java_cache])
        return self._java_cache

    # ========== 定时任务 ==========

    def start_scheduler(self):
        self.scheduler.start()

    def stop_scheduler(self):
        self.scheduler.stop()

    def get_tasks(self) -> list[ScheduleTask]:
        return self.scheduler.get_tasks()

    def add_task(self, task: ScheduleTask) -> bool:
        return self.scheduler.add_task(task)

    def delete_task(self, task_id: str) -> bool:
        return self.scheduler.delete_task(task_id)

    def _execute_scheduled_task(self, task: ScheduleTask):
        log_info(f"执行定时任务: {task.name} ({task.type})")

    def stop_all(self):
        self.stop_scheduler()
