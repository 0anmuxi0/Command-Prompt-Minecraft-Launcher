# 服务器进程管理 - 前台控制台直连模式

from __future__ import annotations
import os
import re
import time
import signal
import subprocess
import threading
from typing import Optional

from ..logger import log_info, log_debug, log_warn, log_error, log_success, log_input
from .instance import ServerInfo
from .java import find_java

MAX_LOG_LINES = 500


# 全局崩溃追踪
_crash_times: list[float] = []


def run_server_foreground(server_info: ServerInfo) -> int:
    """在前台启动 MC 服务器，支持自动重启循环"""
    last_code = 0
    while True:
        last_code = _run_once(server_info)

        # 正常退出（exit_code=0）或未开启自动重启 → 结束循环
        if last_code == 0 or not server_info.auto_restart:
            break

        # 崩溃检测
        now = time.time()
        _crash_times[:] = [t for t in _crash_times if now - t < server_info.crash_check_window]
        _crash_times.append(now)
        crash_count = len(_crash_times)

        if server_info.max_crash_count > 0 and crash_count > server_info.max_crash_count:
            log_error(f"连续崩溃 {crash_count} 次，超过上限 {server_info.max_crash_count}，停止自动重启")
            break

        log_warn(f"服务器崩溃 (第{crash_count}次)，{5} 秒后自动重启 (Ctrl+C 取消)...")
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            break

    return last_code


def _run_once(server_info: ServerInfo) -> int:
    """单次运行 MC 服务器"""
    eula_path = server_info.eula_path
    if not os.path.exists(eula_path):
        _auto_agree_eula(server_info)
    else:
        with open(eula_path, "r") as f:
            if "eula=true" not in f.read().lower().replace(" ", ""):
                _auto_agree_eula(server_info)

    java_exe = _resolve_java(server_info)
    if not java_exe:
        log_error("未找到可用的 Java")
        return -1

    # 清理旧日志文件（上次退出可能残留锁）
    latest_log = os.path.join(server_info.base_path, "logs", "latest.log")
    if os.path.exists(latest_log):
        try:
            os.remove(latest_log)
        except PermissionError:
            log_warn("日志文件被占用，尝试终止残留进程...")
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "java.exe", "/IM", "javaw.exe"],
                    capture_output=True, timeout=5)
            time.sleep(1)
            try:
                os.remove(latest_log)
            except PermissionError:
                log_warn("无法删除日志文件，但将继续启动")

    args = _build_args(server_info, java_exe)

    log_success(f"启动 {server_info.name}...")
    log_debug(f"目录: {server_info.base}")
    log_debug(f"命令: {' '.join(args)}")
    try:
        process = subprocess.Popen(
            args,
            cwd=server_info.base_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        # 读取输出线程（直接打印到终端）
        assert process.stdout is not None
        assert process.stdin is not None
        _stop = [False]

        def _reader():
            import sys as _sys
            for raw in iter(process.stdout.readline, b""):  # type: ignore
                if not raw or _stop[0]:
                    break
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = raw.decode("gbk")
                    except UnicodeDecodeError:
                        text = raw.decode("utf-8", errors="replace")
                # 根据日志等级着色
                stripped = text.rstrip("\r\n")
                if stripped:
                    upper = stripped.upper()
                    if ("[ERROR]" in upper or "/ERROR]" in upper or " ERROR:" in upper
                            or " FATAL" in upper or "Exception in thread" in stripped):
                        color = "\033[91m"  # 红
                    elif ("[WARN]" in upper or "/WARN]" in upper or " WARN:" in upper
                          or " WARNING:" in upper):
                        color = "\033[93m"  # 黄
                    elif "[SUCCESS]" in upper:
                        color = "\033[92m"  # 绿
                    elif "[DEBUG]" in upper or "/DEBUG]" in upper or "[TRACE]" in upper:
                        color = "\033[90m"  # 灰
                    else:
                        color = "\033[97m"  # 白
                    colored = color + stripped + "\033[0m\n"
                else:
                    colored = text
                _sys.stdout.buffer.write(colored.encode("utf-8", errors="replace"))
                _sys.stdout.buffer.flush()
            process.stdout.close()  # type: ignore

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

        # 主线程处理命令输入
        try:
            while True:
                cmd = input()
                if not cmd:
                    continue
                try:
                    process.stdin.write((cmd + "\n").encode("utf-8"))  # type: ignore
                    process.stdin.flush()  # type: ignore
                except BrokenPipeError:
                    break
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            _stop[0] = True

        # 等待进程退出
        process.wait(timeout=5)

    except FileNotFoundError:
        log_error(f"Java 未找到: {java_exe}")
        return -1
    except subprocess.TimeoutExpired:
        _kill(process.pid)
        process.wait()
    except Exception as e:
        log_error(f"启动失败: {e}")
        return -1

    exit_code = process.returncode
    print("-" * 50)
    log_info(f"服务器已停止 (退出码: {exit_code})")
    return exit_code


def _auto_agree_eula(server_info: ServerInfo):
    """自动同意 EULA"""
    path = server_info.eula_path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("eula=true\n")
    log_info("已自动同意 EULA (eula.txt)")


def _detect_mc_version(server_info: ServerInfo) -> int:
    """从核心文件名推断需要的 Java 主版本号"""
    import re
    name = os.path.basename(server_info.core)
    # 尝试提取 MC 版本号
    m = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?', name)
    if not m:
        return 21  # 无法识别时默认 Java 21
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    # MC 版本 → Java 需求映射
    if major == 1:
        if minor < 17:    return 8
        if minor == 17:   return 16
        if 18 <= minor <= 20 and patch <= 4: return 17
        if minor >= 20:   return 21
    if major >= 2:
        return 21  # 未来版本
    return 21


def _resolve_java(server_info: ServerInfo) -> Optional[str]:
    """根据服务器版本自动选择合适 Java（优先 java.exe）"""
    jc = server_info.java
    if not jc or jc == "auto":
        need = _detect_mc_version(server_info)
        log_info(f"该版本需要 Java {need}+，正在搜索...")
        info = find_java(min_version=need)
        if info and info.path:
            return info.path.replace("javaw.exe", "java.exe")
        # 回退：找任意可用 Java
        log_warn(f"未找到 Java {need}+，尝试 Java 21+...")
        info = find_java(min_version=21)
        if info and info.path:
            return info.path.replace("javaw.exe", "java.exe")
        return None
    if jc == "java":
        return "java"
    if os.path.isfile(jc):
        return jc.replace("javaw.exe", "java.exe")
    return None


def _build_args(server_info: ServerInfo, java_exe: str) -> list[str]:
    """构建 JVM 参数"""
    args = [java_exe,
            f"-Xms{server_info.min_m}M",
            f"-Xmx{server_info.max_m}M"]
    if server_info.args:
        args.extend(server_info.args.split())
    # NeoForge: core 以 @ 开头时不加 -jar，直接传参文件
    if server_info.core.startswith("@"):
        args.append(server_info.core)
    else:
        args += ["-jar", server_info.core]
    args.append("nogui")
    return args


def _kill(pid: int):
    """强制结束进程"""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                          capture_output=True, timeout=5)
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
