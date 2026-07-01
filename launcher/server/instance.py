# 服务器实例模型 - 单服务器版

from __future__ import annotations
import os
import json
from dataclasses import dataclass, asdict
from typing import Optional
from enum import IntEnum


class ServerStatus(IntEnum):
    """服务器状态枚举"""
    STOPPED = 0       # 未启动
    STARTING = 1      # 启动中
    RUNNING = 2       # 运行中
    STOPPING = 3      # 停止中
    RESTARTING = 4    # 重启中


@dataclass
class ServerInfo:
    """Minecraft 服务器实例配置"""
    name: str = ""                             # 服务器名称
    base: str = ""                             # 工作目录（留空则首次下载核心时指定）
    java: str = ""                             # Java 路径/版本
    core: str = ""                             # 核心文件名 (如 server.jar)
    min_m: int = 1024                          # 最小内存 (MB)
    max_m: int = 2048                          # 最大内存 (MB)
    args: str = ""                             # 额外 JVM 参数
    force_exit_delay: int = 10                 # 强制退出等待秒数
    stop_command: str = "stop"                 # 停止命令
    backup_max_count: int = 20                 # 最大备份数
    backup_delay: int = 10                     # 备份前等待秒数
    backup_path: str = ""                      # 备份路径
    monitor_players: bool = True               # 玩家监控
    auto_restart: bool = False                 # 自动重启
    force_auto_restart: bool = True            # 强制自动重启
    max_crash_count: int = 5                   # 连续崩溃次数上限(0=无限)
    crash_check_window: int = 300              # 连续崩溃判定时间(秒)
    run_on_startup: bool = False               # 开机自启
    ignore_eula: bool = False                  # 忽略 EULA
    install_retry_count: int = 3               # 安装器失败重试次数
    status: int = ServerStatus.STOPPED         # 当前状态

    def to_dict(self) -> dict:
        """转换为字典"""
        d = asdict(self)
        d['status'] = int(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ServerInfo:
        """从字典创建"""
        data = dict(data)
        data['status'] = ServerStatus(data.get('status', 0))
        return cls(**data)

    @property
    def base_path(self) -> str:
        """获取工作目录绝对路径"""
        return os.path.abspath(self.base)

    @property
    def core_path(self) -> str:
        """获取核心文件绝对路径"""
        if self.core.startswith("@libraries"):
            # @libraries/net/neoforged/... → 转为绝对路径
            rel = self.core.lstrip("@")
            return os.path.join(self.base_path, rel)
        return os.path.join(self.base_path, self.core)

    @property
    def eula_path(self) -> str:
        return os.path.join(self.base_path, "eula.txt")

    @property
    def server_properties_path(self) -> str:
        return os.path.join(self.base_path, "server.properties")

    @property
    def level_name(self) -> str:
        """从 server.properties 读取世界名称"""
        try:
            if os.path.exists(self.server_properties_path):
                with open(self.server_properties_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("level-name="):
                            return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return "world"

    def get_backup_dir(self) -> str:
        """获取备份目录"""
        if self.backup_path == "MSLX://Backup/Instance":
            return os.path.join(self.base_path, "mslx-backups")
        elif self.backup_path.startswith("MSLX://Backup/"):
            # 自定义路径
            custom = self.backup_path[len("MSLX://Backup/"):]
            from ..config import APP_DATA_DIR
            return os.path.join(APP_DATA_DIR, "Backups", custom)
        return self.backup_path

    def get_world_dirs(self) -> list[str]:
        """获取需要备份的世界文件夹列表"""
        base = self.base_path
        level = self.level_name
        dirs = [
            os.path.join(base, level),
            os.path.join(base, f"{level}_nether"),
            os.path.join(base, f"{level}_the_end"),
        ]
        return [d for d in dirs if os.path.isdir(d)]
