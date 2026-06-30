# Command Server Launcher
# 纯命令行 Minecraft 服务端管理程序
#
# 功能: 启动/停止/重启服务器, 下载核心, 备份, 定时任务, 系统监控

import os
import sys
import time

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from launcher.logger import (
    log_info, log_debug, log_error, log_warn,
    log_success, log_request, log_input)
from launcher.config import ConfigManager, APP_DATA_DIR
from launcher.downloader import init as init_downloader
from launcher.server import (
    ServerInfo, ServerManager,
    ScheduleTask, download_core)


def main():
    os.system("title Command Server Launcher")
    os.system("chcp 65001 >nul")

    log_success("Command Server Launcher - Minecraft 服务端管理程序")
    log_debug(f"数据目录: {APP_DATA_DIR}")

    config = ConfigManager()
    init_downloader(config)
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "Backups"), exist_ok=True)
    os.makedirs(os.path.join(APP_DATA_DIR, "Tools", "Java"), exist_ok=True)

    manager = ServerManager()
    manager.start_scheduler()

    # 开机自启
    srv = manager.get_config()
    if srv.run_on_startup:
        log_info("开机自启已开启，正在启动服务器...")
        ok, msg = manager.run_foreground()
        log_info(msg)

    while True:
        try:
            log_info("[1] 启动/控制服务器")
            log_info("[2] 下载服务端核心")
            log_info("[3] 备份管理")
            log_info("[4] 定时任务")
            log_info("[5] 设置")
            log_info("[0] 退出")
            choice = log_input("请选择操作: ").strip()

            if choice == "0":
                log_info("正在关闭...")
                manager.stop_all()
                log_info("感谢使用!")
                time.sleep(2)
                break
            elif choice == "1":
                handle_server_control(config, manager)
            elif choice == "2":
                handle_download_core(config, manager)
            elif choice == "3":
                handle_backup_manager(config, manager)
            elif choice == "4":
                handle_task_scheduler(config, manager)
            elif choice == "5":
                handle_settings(config, manager)
            else:
                log_warn("无效的选项，请重新输入")

        except KeyboardInterrupt:
            log_info("用户取消操作")
            manager.stop_all()
            break
        except Exception as e:
            log_error(f"发生错误: {e}")
            log_debug(f"详细信息: {e}")

def handle_server_control(config: ConfigManager, manager: ServerManager):
    """启动服务器（前台直出日志）"""
    srv = manager.get_config()
    log_info(f"服务器: {srv.name}")
    log_info(f"目录: {srv.base}")
    log_info(f"核心: {srv.core}")
    log_info(f"内存: {srv.min_m}-{srv.max_m}MB")
    if manager.is_running():
        log_info("服务器已在运行")
        return
    log_info("[t] 启动  [0] 返回")
    choice = log_input("操作: ").strip().lower()
    if choice == "t":
        ok, msg = manager.run_foreground()
        log_success(msg) if ok else log_error(msg)


def _browse_versions(core_type: str) -> str:
    """浏览可用版本列表（支持翻页）"""
    from launcher.network import net_get_manifest
    PAGE_SIZE = 20

    log_info("正在获取版本列表...")
    manifest = net_get_manifest()
    if not manifest:
        log_error("获取版本列表失败")
        return ""

    all_versions = manifest.get("versions", [])
    # 先正式版再快照
    releases = [v for v in all_versions if v.get("type") == "release"]
    snapshots = [v for v in all_versions if v.get("type") == "snapshot"]
    versions = releases + snapshots

    total = len(versions)
    page = 0
    max_page = (total - 1) // PAGE_SIZE

    while True:
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        log_info(f"--- Minecraft 版本列表 (第{page+1}/{max_page+1}页, 共{total}个) ---")
        for i in range(start, end):
            v = versions[i]
            tag = "[R]" if v.get("type") == "release" else "[S]"
            log_info(f"  {i+1:>4}. {tag} {v['id']:12} {v.get('releaseTime','')[:10]}")
        log_info("--- 输入版本号直接下载, n下一页, p上一页, q取消 ---")

        cmd = log_input("> ").strip().lower()
        if cmd == "q":
            return ""
        elif cmd == "n":
            if page < max_page:
                page += 1
        elif cmd == "p":
            if page > 0:
                page -= 1
        else:
            # 尝试匹配版本 ID
            for v in versions:
                if v["id"] == cmd:
                    return cmd
            # 模糊匹配
            matches = [v for v in versions if cmd in v["id"]]
            if len(matches) == 1:
                return matches[0]["id"]
            elif len(matches) > 1:
                log_info(f"匹配到多个版本: {', '.join(v['id'] for v in matches[:10])}")
            else:
                log_warn(f"未找到版本: {cmd}")


def handle_download_core(config: ConfigManager, manager: ServerManager):
    """下载服务端核心"""
    log_success("下载服务端核心")
    log_info("选择下载类型:")
    log_info("[1] Vanilla")
    log_info("[2] Paper")
    log_info("[3] Purpur")
    log_info("[4] Fabric")
    log_info("[5] Forge")
    log_info("[6] NeoForge")
    types = {"1": "vanilla", "2": "paper", "3": "purpur",
             "4": "fabric", "5": "forge", "6": "neoforge"}
    choice = log_input("选择类型 (1-6): ").strip()
    core_type = types.get(choice)
    if not core_type:
        log_error("无效的选择")
        return

    if core_type in ("vanilla", "paper", "purpur", "fabric", "forge", "neoforge"):
        log_info("直接输入版本号，或输入 list 浏览可用版本")
    version = log_input("Minecraft 版本 (如 1.20.1): ").strip().lower()
    if version == "list":
        version = _browse_versions(core_type)
        if not version:
            return
    elif not version:
        log_error("版本号不能为空")
        return

    srv = manager.get_config()
    dest = srv.base
    if not dest or not os.path.isdir(dest):
        log_warn(f"服务器目录不存在: {dest}")
        use_custom = log_input("是否指定其他目录? (y/N): ").strip().lower() == "y"
        if use_custom:
            dest = log_input("目标目录: ").strip()
            if not dest:
                return
        else:
            return

    os.makedirs(dest, exist_ok=True)
    log_info(f"正在下载 {core_type} {version} 到 {dest}...")

    filename = download_core(core_type, version, dest)
    if filename:
        log_success(f"下载完成: {filename}")

        # 保存配置
        srv.base = dest
        srv.core = filename
        manager.save_config(srv)
        log_info(f"已保存配置: 目录={dest}, 核心={filename}")

        start_now = log_input("是否立即启动? (Y/n): ").strip().lower()
        if start_now != "n":
            ok, msg = manager.run_foreground()
            log_info(msg)
    else:
        log_error("下载失败")


def handle_backup_manager(config: ConfigManager, manager: ServerManager):
    """备份管理"""
    while True:
        srv = manager.get_config()
        log_info(f"备份管理 - {srv.name}")
        log_info("[1] 创建备份")
        log_info("[2] 查看备份列表")
        log_info("[0] 返回")

        choice = log_input("操作: ").strip()
        if choice == "0":
            break
        elif choice == "1":
            success, msg = manager.create_backup()
            log_success(msg) if success else log_error(msg)
        elif choice == "2":
            backups = manager.list_backups()
            if backups:
                log_info("备份列表:")
                for i, b in enumerate(backups, 1):
                    log_info(f"  [{i}] {b['name']} ({b['size_mb']:.1f}MB, {b['mtime_str']})")
                del_choice = log_input("输入序号删除 (0=返回): ").strip()
                try:
                    di = int(del_choice) - 1
                    if 0 <= di < len(backups):
                        if manager.delete_backup(backups[di]['name']):
                            log_success("备份已删除")
                except ValueError:
                    pass
            else:
                log_info("暂无备份")


def handle_task_scheduler(config: ConfigManager, manager: ServerManager):
    """定时任务管理"""
    while True:
        tasks = manager.get_tasks()
        log_info("定时任务列表:")
        if tasks:
            for i, t in enumerate(tasks, 1):
                st = "[启用]" if t.enable else "[禁用]"
                log_info(f"  [{i}] {st} {t.name} ({t.type}) - {t.cron}")
        else:
            log_info("  暂无定时任务")
        log_info("[a] 添加任务  [d] 删除任务")
        log_info("[0] 返回")

        choice = log_input("操作: ").strip()
        if choice == "0":
            break
        elif choice == "a":
            _add_task(manager)
        elif choice.startswith("d"):
            idx_str = choice[1:].strip() or log_input("要删除的任务序号: ").strip()
            try:
                idx = int(idx_str) - 1
                if 0 <= idx < len(tasks):
                    manager.delete_task(tasks[idx].id)
                    log_success("任务已删除")
            except ValueError:
                log_error("无效的序号")


def _add_task(manager: ServerManager):
    """添加定时任务"""
    name = log_input("任务名称: ").strip() or f"Task-{int(time.time())}"
    log_info("类型: [1]命令 [2]启动 [3]停止 [4]重启 [5]备份")
    type_map = {"1": "command", "2": "start", "3": "stop", "4": "restart", "5": "backup"}
    task_type = type_map.get(log_input("选择类型: ").strip(), "command")

    log_info("执行频率:")
    log_info("[1] 每分钟")
    log_info("[2] 每小时  [3] 每天4点")
    log_info("[4] 每周一4点  [5] 每月1号4点  [6] 自定义")
    freq_map = {
        "1": "* * * * *",
        "2": "0 0 * * *",
        "3": "0 0 4 * *",
        "4": "0 0 4 * * 1",
        "5": "0 0 4 1 *",
    }
    freq = log_input("选择频率 (1-6): ").strip()
    cron = freq_map.get(freq)
    if not cron:
        cron = log_input("Cron (秒 分 时 日 月 周): ").strip()
        if not cron:
            log_error("Cron 不能为空")
            return

    payload = log_input("命令内容: ").strip() if task_type == "command" else ""
    import uuid
    task = ScheduleTask(id=str(uuid.uuid4()), name=name, type=task_type, cron=cron, payload=payload, enable=True)
    if manager.add_task(task):
        freq_names = {"* * * * *": "每分钟", "0 0 * * *": "每小时",
                       "0 0 4 * *": "每天4点", "0 0 4 * * 1": "每周一4点",
                       "0 0 4 1 *": "每月1号4点"}
        type_names = {"command": "命令", "start": "启动", "stop": "停止",
                       "restart": "重启", "backup": "备份"}
        log_success(f"已添加: [{type_names.get(task_type, task_type)}] {name} ({freq_names.get(cron, cron)})")
    else:
        log_error("添加失败")


def handle_settings(config: ConfigManager, manager: ServerManager):
    """设置"""
    while True:
        srv = manager.get_config()
        log_info("服务器设置:")
        log_info(f"[1] 服务器名称: {srv.name}")
        log_info(f"[2] 工作目录: {srv.base}")
        log_info(f"[3] 核心文件: {srv.core}")
        log_info(f"[4] Java 设置")
        log_info(f"[5] 启动设置")
        log_info(f"[6] 停止命令: {srv.stop_command}")
        log_info("[0] 返回")

        choice = log_input("选择: ").strip()
        if choice == "0":
            break
        elif choice == "1":
            val = log_input(f"名称 [{srv.name}]: ").strip()
            if val: srv.name = val; log_success(f"名称 → {val}")
        elif choice == "2":
            val = log_input(f"目录 [{srv.base}]: ").strip()
            if val: srv.base = val; log_success(f"目录 → {val}")
        elif choice == "3":
            jars = []
            if srv.base and os.path.isdir(srv.base):
                jars = [f for f in os.listdir(srv.base) if f.endswith(".jar")]
            hint = f" (可选: {', '.join(jars[:5])})" if jars else ""
            val = log_input(f"核心{hint} [{srv.core}]: ").strip()
            if val:
                srv.core = val
                log_success(f"核心 → {val}")
            elif jars:
                srv.core = jars[0]
                log_success(f"核心 → {jars[0]}")
        elif choice == "4":
            _settings_java(srv)
        elif choice == "5":
            _settings_startup(srv)
        elif choice == "6":
            val = log_input(f"停止命令 [{srv.stop_command}]: ").strip()
            if val: srv.stop_command = val; log_success(f"停止命令 → {val}")

        manager.save_config(srv)


def _settings_java(srv: ServerInfo):
    """Java 设置子菜单"""
    while True:
        log_info("Java 设置:")
        log_info(f"[1] Java 路径: {srv.java or '自动'}")
        log_info(f"[2] 最小内存: {srv.min_m} MB")
        log_info(f"[3] 最大内存: {srv.max_m} MB")
        log_info(f"[4] JVM 参数: {srv.args or '无'}")
        log_info("[0] 返回")

        c = log_input("选择: ").strip()
        if c == "0":
            break
        elif c == "1":
            val = log_input(f"Java 路径 [{srv.java or '自动'}]: ").strip()
            old = srv.java or "自动"
            srv.java = val
            if val != old: log_success(f"Java → {val or '自动'}")
        elif c == "2":
            val = log_input(f"最小内存 [{srv.min_m}]: ").strip()
            if val:
                try: srv.min_m = int(val); log_success(f"最小内存 → {val}MB")
                except: log_error("无效数字")
        elif c == "3":
            val = log_input(f"最大内存 [{srv.max_m}]: ").strip()
            if val:
                try: srv.max_m = int(val); log_success(f"最大内存 → {val}MB")
                except: log_error("无效数字")
        elif c == "4":
            val = log_input(f"JVM 参数 [{srv.args}]: ").strip()
            srv.args = val
            log_success(f"JVM 参数 → {val or '无'}")


def _settings_startup(srv: ServerInfo):
    """启动设置子菜单"""
    while True:
        crash_max = "无限" if srv.max_crash_count == 0 else str(srv.max_crash_count)
        log_info("启动设置:")
        log_info(f"[1] 自动重启: {'开' if srv.auto_restart else '关'}")
        log_info(f"[2] 连续崩溃次数上限: {crash_max}")
        log_info(f"[3] 连续崩溃判定时间: {srv.crash_check_window} 秒")
        log_info(f"[4] 自动启动: {'开' if srv.run_on_startup else '关'}")
        log_info("[0] 返回")

        c = log_input("选择: ").strip()
        if c == "0":
            break
        elif c == "1":
            srv.auto_restart = not srv.auto_restart
            log_success(f"自动重启 → {'开' if srv.auto_restart else '关'}")
        elif c == "2":
            val = log_input(f"次数上限 [{crash_max}]: ").strip()
            if val:
                try: srv.max_crash_count = max(int(val), 0); log_success(f"上限 → {'无限' if srv.max_crash_count == 0 else str(srv.max_crash_count)}")
                except: log_error("无效数字")
        elif c == "3":
            val = log_input(f"判定时间 [{srv.crash_check_window}]: ").strip()
            if val:
                try: srv.crash_check_window = max(int(val), 10); log_success(f"判定时间 → {srv.crash_check_window} 秒")
                except: log_error("无效数字")
        elif c == "4":
            srv.run_on_startup = not srv.run_on_startup
            log_success(f"自动启动 → {'开' if srv.run_on_startup else '关'}")

if __name__ == "__main__":
    main()
