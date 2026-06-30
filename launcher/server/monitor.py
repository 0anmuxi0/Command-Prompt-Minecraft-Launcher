# 系统监控 - 参考 MSLX SystemMonitor 和 SystemMonitorWorker

from __future__ import annotations
import os
import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable

from ..logger import log_debug


@dataclass
class SystemStatus:
    """系统状态"""
    cpu_percent: float = 0.0
    total_memory_mb: float = 0.0
    used_memory_mb: float = 0.0
    memory_percent: float = 0.0


class SystemMonitor:
    """系统资源监控器
    
    每 2 秒采集一次 CPU/内存信息
    """
    
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[SystemStatus], None]] = None
        self._last_status = SystemStatus()
        
        # Linux /proc 计数器缓存（差值法计算 CPU）
        self._prev_idle = 0
        self._prev_total = 0
    
    def start(self, callback: Optional[Callable[[SystemStatus], None]] = None):
        """启动监控"""
        if self._running:
            return
        self._running = True
        self._callback = callback
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        log_debug("系统监控已启动")
    
    def stop(self):
        """停止监控"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        log_debug("系统监控已停止")
    
    def get_status(self) -> SystemStatus:
        """获取最新状态"""
        return self._last_status
    
    def _monitor_loop(self):
        """监控循环（每 2 秒）"""
        while self._running:
            try:
                status = self._collect_status()
                self._last_status = status
                if self._callback:
                    self._callback(status)
            except Exception:
                pass
            time.sleep(2)
    
    def _collect_status(self) -> SystemStatus:
        """采集系统状态"""
        cpu = self._get_cpu_usage()
        total_mem, used_mem = self._get_memory_usage()
        
        mem_percent = 0.0
        if total_mem > 0:
            mem_percent = (used_mem / total_mem) * 100
        
        return SystemStatus(
            cpu_percent=cpu,
            total_memory_mb=total_mem / (1024 * 1024),
            used_memory_mb=used_mem / (1024 * 1024),
            memory_percent=mem_percent,
        )
    
    def _get_cpu_usage(self) -> float:
        """获取 CPU 使用率"""
        if os.name == "nt":
            return self._get_cpu_windows()
        else:
            return self._get_cpu_linux()
    
    def _get_cpu_windows(self) -> float:
        """Windows CPU 使用率（通过性能计数器）"""
        try:
            import ctypes
            from ctypes import wintypes
            
            # 使用 GetSystemTimes API
            kernel32 = ctypes.windll.kernel32
            
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD),
                           ("dwHighDateTime", wintypes.DWORD)]
            
            idle_time = FILETIME()
            kernel_time = FILETIME()
            user_time = FILETIME()
            
            if kernel32.GetSystemTimes(
                ctypes.byref(idle_time),
                ctypes.byref(kernel_time),
                ctypes.byref(user_time)
            ):
                def filetime_to_int(ft):
                    return (ft.dwHighDateTime << 32) + ft.dwLowDateTime
                
                idle = filetime_to_int(idle_time)
                kernel = filetime_to_int(kernel_time)
                user = filetime_to_int(user_time)
                total = kernel + user
                
                if self._prev_total > 0:
                    delta_total = total - self._prev_total
                    delta_idle = idle - self._prev_idle
                    if delta_total > 0:
                        usage = (1.0 - delta_idle / delta_total) * 100.0
                        self._prev_idle = idle
                        self._prev_total = total
                        return min(max(usage, 0.0), 100.0)
                
                self._prev_idle = idle
                self._prev_total = total
        except Exception:
            pass
        return 0.0
    
    def _get_cpu_linux(self) -> float:
        """Linux CPU 使用率（通过 /proc/stat）"""
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            if not line.startswith("cpu "):
                return 0.0
            
            parts = line.split()
            # user, nice, system, idle, iowait, irq, softirq, steal
            values = [int(v) for v in parts[1:]]
            idle = values[3] + values[4]  # idle + iowait
            total = sum(values)
            
            if self._prev_total > 0:
                delta_total = total - self._prev_total
                delta_idle = idle - self._prev_idle
                if delta_total > 0:
                    usage = (1.0 - delta_idle / delta_total) * 100.0
                    self._prev_idle = idle
                    self._prev_total = total
                    return min(max(usage, 0.0), 100.0)
            
            self._prev_idle = idle
            self._prev_total = total
        except Exception:
            pass
        return 0.0
    
    def _get_memory_usage(self) -> tuple[int, int]:
        """获取内存使用情况 (total, used) bytes"""
        if os.name == "nt":
            return self._get_memory_windows()
        else:
            return self._get_memory_linux()
    
    def _get_memory_windows(self) -> tuple[int, int]:
        """Windows 内存信息"""
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            
            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                total = memory_status.ullTotalPhys
                avail = memory_status.ullAvailPhys
                used = total - avail
                return total, used
        except Exception:
            pass
        return 0, 0
    
    def _get_memory_linux(self) -> tuple[int, int]:
        """Linux 内存信息（通过 /proc/meminfo）"""
        try:
            total = 0
            available = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total = int(line.split()[1]) * 1024  # kB to bytes
                    elif line.startswith("MemAvailable:"):
                        available = int(line.split()[1]) * 1024
                    if total and available:
                        break
            return total, total - available
        except Exception:
            pass
        return 0, 0
