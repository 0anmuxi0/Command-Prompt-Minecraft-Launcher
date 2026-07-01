# 备份管理器 - 参考 MSLX BackupManager

from __future__ import annotations
import os
import zipfile
import time
import threading
from datetime import datetime
from launcher.server import instance
from launcher.server.instance import ServerInfo
from ..logger import log_info, log_debug, log_warn, log_error, log_success

class BackupManager:
    """服务器备份管理器（单服务器）"""
    
    _lock = threading.Lock()
    
    def create_backup(self, server_info: ServerInfo,
                      send_command_fn=None) -> tuple[bool, str]:
        """创建备份"""
        if not self._lock.acquire(blocking=False):
            return False, "备份正在进行中"
        
        try:
            backup_dir = server_info.get_backup_dir()
            os.makedirs(backup_dir, exist_ok=True)
            
            # 获取世界文件夹
            world_dirs = server_info.get_world_dirs()
            if not world_dirs:
                return False, "未找到世界文件夹"
            
            # 如果是在线服务器，发送 save 命令
            if send_command_fn:
                log_info("正在执行在线备份...")
                send_command_fn(instance, "save-off")
                send_command_fn(instance, "save-all")
                time.sleep(server_info.backup_delay)
            
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup-{server_info.name}-{timestamp}.zip"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            log_info(f"正在创建备份: {backup_filename}")
            
            # 创建 ZIP 备份
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for world_dir in world_dirs:
                    world_name = os.path.basename(world_dir)
                    for root, _, files in os.walk(world_dir):
                        for file in files:
                            # 跳过 session.lock
                            if file == "session.lock":
                                continue
                            file_path = os.path.join(root, file)
                            arc_name = os.path.join(world_name, os.path.relpath(file_path, world_dir))
                            zf.write(file_path, arc_name)
            
            log_success(f"备份完成: {backup_filename}")
            
            # 恢复在线模式
            if send_command_fn:
                send_command_fn(instance, "save-on")
            
            # 清理旧备份
            self._cleanup_old_backups(server_info, backup_dir)
            
            size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            return True, f"备份完成: {backup_filename} ({size_mb:.1f}MB)"
            
        except Exception as e:
            log_error(f"备份失败: {e}")
            return False, f"备份失败: {e}"
        finally:
            self._lock.release()
    
    def list_backups(self, server_info: ServerInfo) -> list[dict]:
        """列出所有备份"""
        backup_dir = server_info.get_backup_dir()
        if not os.path.exists(backup_dir):
            return []
        
        backups = []
        for f in sorted(os.listdir(backup_dir), reverse=True):
            file_path = os.path.join(backup_dir, f)
            if os.path.isfile(file_path) and f.endswith(".zip"):
                backups.append({
                    "name": f,
                    "path": file_path,
                    "size": os.path.getsize(file_path),
                    "size_mb": os.path.getsize(file_path) / (1024 * 1024),
                    "mtime": os.path.getmtime(file_path),
                    "mtime_str": datetime.fromtimestamp(
                        os.path.getmtime(file_path)
                    ).strftime("%Y-%m-%d %H:%M:%S"),
                })
        return backups
    
    def delete_backup(self, server_info: ServerInfo, filename: str) -> bool:
        """删除备份
        
        Args:
            server_info: 服务器配置
            filename: 备份文件名
        
        Returns:
            是否成功
        """
        # 安全检查：禁止路径遍历
        if "/" in filename or "\\" in filename or ".." in filename:
            return False
        
        if not filename.endswith(".zip"):
            return False
        
        backup_dir = server_info.get_backup_dir()
        file_path = os.path.join(backup_dir, filename)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log_success(f"已删除备份: {filename}")
                return True
        except Exception as e:
            log_error(f"删除备份失败: {e}")
        
        return False
    
    def _cleanup_old_backups(self, server_info: ServerInfo, backup_dir: str):
        """清理超出最大数量的旧备份"""
        max_count = server_info.backup_max_count
        if max_count <= 0:
            return
        
        backups = self.list_backups(server_info)
        if len(backups) <= max_count:
            return
        
        # 删除最旧的备份
        to_delete = backups[max_count:]
        for b in to_delete:
            try:
                os.remove(b["path"])
                log_debug(f"已删除旧备份: {b['name']}")
            except Exception as e:
                log_warn(f"删除旧备份失败: {b['name']}: {e}")
