# 配置管理 - 统一 JSON 配置系统
# 所有配置存储在项目根目录 config.json
# 仅 Minecraft 服务端管理

import os
import json
from typing import Optional
from .logger import log_info, log_debug, log_warn, log_error

# 配置文件路径（项目根目录）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = PROJECT_ROOT
CONFIG_JSON = os.path.join(PROJECT_ROOT, "config.json")
CACHE_DIR = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", PROJECT_ROOT)), "CML-Cache")

# 应用数据目录（用于存放服务器数据、Java 等）
APP_DATA_DIR = os.path.join(PROJECT_ROOT, "DaemonData")

# 默认配置（launch / general / download / server 全部统一）
DEFAULT_CONFIG: dict = {
    "server": {
        "name": "我的服务器",
        "base": "",
        "core": "server.jar",
        "java": "",
        "min_m": 1024,
        "max_m": 2048,
        "args": "",
        "stop_command": "stop",
        "auto_restart": False,
        "force_auto_restart": True,
        "max_crash_count": 5,
        "crash_check_window": 300,
        "monitor_players": True,
        "ignore_eula": False,
        "force_exit_delay": 10,
        "backup_max_count": 20,
        "backup_delay": 10,
        "backup_path": "",
        "status": 0,
    },
    "download": {
        "max_threads": 32,
        "max_retries": 3,
        "timeout": 60,
    },
    "general": {
        "Language": "zh-cn",
    },
}


def ensure_config_dir():
    # 确保配置目录存在
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    log_debug(f"配置文件: {CONFIG_JSON}")


def _load_json() -> dict:
    # 加载 config.json
    if os.path.exists(CONFIG_JSON):
        try:
            with open(CONFIG_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log_warn(f"加载 config.json 失败: {e}")
    return {}


def _save_json(data: dict):
    # 保存 config.json
    try:
        ensure_config_dir()
        with open(CONFIG_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_error(f"保存 config.json 失败: {e}")


class ConfigManager:
    # 配置管理器 - 读取/写入 CML/config.json

    def __init__(self):
        ensure_config_dir()
        self._data: dict = {}
        self._load()

    def _load(self):
        # 加载配置文件（合并默认值）
        self._data = {}
        for section, options in DEFAULT_CONFIG.items():
            self._data[section] = dict(options)

        # 加载 config.json（覆盖默认值）
        json_data = _load_json()
        for section, options in json_data.items():
            sec = section.lower()
            if sec in self._data and isinstance(options, dict):
                self._data[sec].update(options)
            elif isinstance(options, dict):
                self._data[sec] = dict(options)

        # 确保关键值合法
        dl = self._data.get("download", {})
        dl["max_threads"] = max(int(dl.get("max_threads", 32)), 1)
        raw_retries = int(dl.get("max_retries", 3))
        dl["max_retries"] = raw_retries if raw_retries >= 0 else 0
        dl["timeout"] = max(int(dl.get("timeout", 60)), 5)

        log_debug(f"已加载配置: {CONFIG_JSON}")
        self.save()

    def save(self):
        # 保存配置到 config.json
        _save_json(self._data)

    # ---- 通用配置接口（保持兼容） ----

    def get(self, section: str, key: str, fallback: str = "") -> str:
        # 获取配置项（字符串）
        try:
            val = self._data[section.lower()][key]
            return str(val) if val is not None else fallback
        except KeyError:
            return fallback

    def set(self, section: str, key: str, value: str):
        # 设置配置项
        sec = section.lower()
        if sec not in self._data:
            self._data[sec] = {}
        self._data[sec][key] = value
        self.save()

    def get_int(self, section: str, key: str, fallback: int = 0) -> int:
        # 获取整数配置项
        try:
            return int(self._data[section.lower()][key])
        except (KeyError, ValueError, TypeError):
            return fallback

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        # 获取布尔配置项
        try:
            val = str(self._data[section.lower()][key]).lower()
            if val in ("true", "1", "yes"):
                return True
            if val in ("false", "0", "no"):
                return False
        except KeyError:
            pass
        return fallback

    # ---- 下载配置接口 ----

    def get_download_config(self) -> dict:
        # 获取下载配置
        return dict(self._data.get("download", DEFAULT_CONFIG["download"]))

    def set_download_config(self, **kwargs):
        # 设置下载配置项
        if "download" not in self._data:
            self._data["download"] = dict(DEFAULT_CONFIG["download"])
        self._data["download"].update(kwargs)
        self.save()

    # ---- 服务器配置接口（单服务器） ----

    def get_server_config(self, key: str, fallback: str = ""):
        """获取服务器配置项（字符串值）"""
        return str(self._data.get("server", {}).get(key, fallback))

    def set_server_config(self, key: str, value):
        """设置服务器配置项"""
        if "server" not in self._data:
            self._data["server"] = dict(DEFAULT_CONFIG.get("server", {}))
        self._data["server"][key] = value
        self.save()

    def get_server_config_obj(self):
        """获取完整服务器配置对象"""
        from .server.instance import ServerInfo
        srv = self._data.get("server", {})
        return ServerInfo.from_dict(srv)

    def set_server_config_obj(self, server_info):
        """保存完整服务器配置对象"""
        self._data["server"] = server_info.to_dict()
        self.save()

    # ---- Java 缓存接口 ----

    def set_java_cache(self, java_list: list[dict]):
        if "java" not in self._data:
            self._data["java"] = {}
        self._data["java"]["cache"] = java_list
        self.save()

    def get_java_cache(self) -> list[dict]:
        return self._data.get("java", {}).get("cache", [])
