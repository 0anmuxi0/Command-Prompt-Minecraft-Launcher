# 定时任务调度器 - 参考 MSLX TaskSchedulerService

from __future__ import annotations
import json
import os
import time
import threading
import re
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

from ..logger import log_info, log_debug, log_warn, log_error, log_success
from ..config import PROJECT_ROOT


TASKS_FILE = os.path.join(PROJECT_ROOT, "tasks.json")

# 默认任务列表
DEFAULT_TASKS: list[dict] = []


@dataclass
class ScheduleTask:
    """定时任务 - 单服务器版"""
    id: str = ""                    # GUID
    name: str = ""                  # 任务名称
    type: str = "command"           # command / start / stop / restart / backup
    cron: str = ""                  # Cron 表达式（支持秒级）
    payload: str = ""               # 负载（命令内容等）
    enable: bool = True             # 是否启用
    last_run_time: Optional[str] = None  # 最后运行时间

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ScheduleTask:
        return cls(**data)


class TaskScheduler:
    """定时任务调度器
    
    每秒检查一次任务列表，匹配 Cron 表达式并执行
    """
    
    def __init__(self):
        self._tasks: list[ScheduleTask] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._executor: Optional[Callable[[ScheduleTask], None]] = None
        
        self._load()
    
    def set_executor(self, executor: Callable[[ScheduleTask], None]):
        """设置任务执行器"""
        self._executor = executor
    
    def start(self):
        """启动调度器"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._thread.start()
        log_debug("任务调度器已启动")
    
    def stop(self):
        """停止调度器"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        self._save()
        log_debug("任务调度器已停止")
    
    def get_tasks(self) -> list[ScheduleTask]:
        """获取任务列表"""
        with self._lock:
            return list(self._tasks)
    
    def add_task(self, task: ScheduleTask) -> bool:
        """添加任务"""
        with self._lock:
            # 检查 ID 是否重复
            for t in self._tasks:
                if t.id == task.id:
                    return False
            self._tasks.append(task)
            self._save()
        return True
    
    def update_task(self, task: ScheduleTask) -> bool:
        """更新任务"""
        with self._lock:
            for i, t in enumerate(self._tasks):
                if t.id == task.id:
                    self._tasks[i] = task
                    self._save()
                    return True
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self._lock:
            for i, t in enumerate(self._tasks):
                if t.id == task_id:
                    self._tasks.pop(i)
                    self._save()
                    return True
        return False
    
    def _load(self):
        """加载任务列表"""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self._tasks = [ScheduleTask.from_dict(t) for t in data]
                log_debug(f"已加载 {len(self._tasks)} 个定时任务")
            except Exception as e:
                log_warn(f"加载任务列表失败: {e}")
                self._tasks = []
        else:
            self._tasks = []
    
    def _save(self):
        """保存任务列表"""
        try:
            with self._lock:
                data = [t.to_dict() for t in self._tasks]
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log_error(f"保存任务列表失败: {e}")
    
    def _scheduler_loop(self):
        """调度器主循环（每秒 tick）"""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                with self._lock:
                    tasks = list(self._tasks)
                
                for task in tasks:
                    if not task.enable:
                        continue
                    if self._should_run(task, now):
                        log_debug(f"触发定时任务: {task.name}")
                        task.last_run_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                        self.update_task(task)
                        
                        if self._executor:
                            threading.Thread(
                                target=self._executor,
                                args=(task,),
                                daemon=True
                            ).start()
            except Exception as e:
                log_debug(f"调度器循环异常: {e}")
            
            time.sleep(1)
    
    def _should_run(self, task: ScheduleTask, now: datetime) -> bool:
        """检查任务是否应该运行
        
        支持秒级 Cron 表达式: "sec min hour day mon weekday"
        """
        try:
            parts = task.cron.strip().split()
            if len(parts) < 5:
                return False
            
            # 解析 Cron 表达式
            now_tuple = (now.second, now.minute, now.hour,
                        now.day, now.month, now.weekday())
            
            for i, part in enumerate(parts[:6]):
                if not self._cron_match(part, now_tuple[i]):
                    return False
            
            # 检查最后运行时间（避免重复触发）
            if task.last_run_time:
                try:
                    last = datetime.strptime(
                        task.last_run_time.replace("Z", "+0000"),
                        "%Y-%m-%dT%H:%M:%S%z"
                    )
                    # 确保在同一分钟内不重复触发
                    if (now.timestamp() - last.timestamp()) < 60:
                        return False
                except Exception:
                    pass
            
            return True
            
        except Exception:
            return False
    
    def _cron_match(self, pattern: str, value: int) -> bool:
        """匹配单个 Cron 字段"""
        if pattern == "*":
            return True
        
        # 处理步长: */5, 1-10/2
        if "/" in pattern:
            base, step = pattern.split("/")
            step = int(step)
            if base == "*":
                return value % step == 0
            start, end = base.split("-")
            return int(start) <= value <= int(end) and (value - int(start)) % step == 0
        
        # 处理范围: 1-5
        if "-" in pattern:
            start, end = pattern.split("-")
            return int(start) <= value <= int(end)
        
        # 处理列表: 1,3,5
        if "," in pattern:
            return value in [int(x) for x in pattern.split(",")]
        
        # 单个值
        try:
            return int(pattern) == value
        except ValueError:
            return False
