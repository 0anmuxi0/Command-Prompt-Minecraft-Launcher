"""全面错误检查脚本"""
import importlib
import traceback
import sys
import os

# 确保路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

modules = [
    'launcher.logger',
    'launcher.network',
    'launcher.config',
    'launcher.downloader',
    'launcher.server.instance',
    'launcher.server.java',
    'launcher.server.process',
    'launcher.server.backup',
    'launcher.server.monitor',
    'launcher.server.scheduler',
    'launcher.server.deploy',
    'launcher.server.manager',
    'launcher.server',
]

print("=" * 60)
print("1. 导入检查")
print("=" * 60)
all_ok = True
for mod_name in modules:
    try:
        importlib.import_module(mod_name)
        print(f"  ✅ {mod_name}")
    except Exception as e:
        print(f"  ❌ {mod_name}: {e}")
        traceback.print_exc()
        all_ok = False

print()
print("=" * 60)
print("2. 功能检查")
print("=" * 60)

if all_ok:
    from launcher.config import ConfigManager, APP_DATA_DIR
    from launcher.server.instance import ServerInfo, ServerStatus
    from launcher.server.java import scan_java, JavaInfo
    from launcher.server.process import ServerProcess
    from launcher.server.backup import BackupManager
    from launcher.server.monitor import SystemMonitor
    from launcher.server.scheduler import TaskScheduler, ScheduleTask
    from launcher.server.deploy import ServerDeployer, CreateServerRequest
    from launcher.server.manager import ServerManager

    # Test ConfigManager
    try:
        config = ConfigManager()
        print(f"  ✅ ConfigManager: APP_DATA_DIR={APP_DATA_DIR}")
    except Exception as e:
        print(f"  ❌ ConfigManager: {e}")
        all_ok = False

    # Test ServerInfo
    try:
        s = ServerInfo(id=1, name="Test", base="C:/test", core="server.jar")
        assert s.name == "Test"
        assert s.id == 1
        assert s.status == ServerStatus.STOPPED
        assert s.to_dict()["name"] == "Test"
        restored = ServerInfo.from_dict(s.to_dict())
        assert restored.name == "Test"
        print(f"  ✅ ServerInfo: 序列化/反序列化正常")
    except Exception as e:
        print(f"  ❌ ServerInfo: {e}")
        all_ok = False

    # Test Java scan
    try:
        java_list = scan_java()
        print(f"  ✅ scan_java: 找到 {len(java_list)} 个 Java")
        for j in java_list[:2]:
            print(f"      Java {j.major_version}: {j.path}")
    except Exception as e:
        print(f"  ❌ scan_java: {e}")
        all_ok = False

    # Test SystemMonitor
    try:
        monitor = SystemMonitor()
        status = monitor.get_status()
        assert hasattr(status, 'cpu_percent')
        assert hasattr(status, 'memory_percent')
        print(f"  ✅ SystemMonitor: CPU={status.cpu_percent:.1f}%, Mem={status.memory_percent:.1f}%")
    except Exception as e:
        print(f"  ❌ SystemMonitor: {e}")
        all_ok = False

    # Test ServerProcess
    try:
        proc = ServerProcess()
        assert not proc.is_server_running(999)  # 不存在的服务器
        ctx = proc.get_server_context(999)
        assert ctx is None
        print(f"  ✅ ServerProcess: 基础状态检查正常")
    except Exception as e:
        print(f"  ❌ ServerProcess: {e}")
        all_ok = False

    # Test BackupManager
    try:
        backup = BackupManager()
        backups = backup.list_backups(s)
        assert isinstance(backups, list)
        print(f"  ✅ BackupManager: list_backups 正常")
    except Exception as e:
        print(f"  ❌ BackupManager: {e}")
        all_ok = False

    # Test TaskScheduler
    try:
        scheduler = TaskScheduler()
        tasks = scheduler.get_tasks()
        assert isinstance(tasks, list)
        print(f"  ✅ TaskScheduler: get_tasks 正常")
        
        import uuid
        task = ScheduleTask(
            id=str(uuid.uuid4()), instance_id=1, name="test",
            type="command", cron="0 0 * * * *", payload="say hello"
        )
        assert scheduler.add_task(task)
        assert len(scheduler.get_tasks()) == 1
        assert scheduler.delete_task(task.id)
        assert len(scheduler.get_tasks()) == 0
        print(f"  ✅ TaskScheduler: 增删任务正常")
    except Exception as e:
        print(f"  ❌ TaskScheduler: {e}")
        all_ok = False

    # Test ServerDeployer
    try:
        deployer = ServerDeployer()
        request = CreateServerRequest(name="test", core_type="vanilla", core_version="1.20.1")
        print(f"  ✅ ServerDeployer: CreateServerRequest 正常")
    except Exception as e:
        print(f"  ❌ ServerDeployer: {e}")
        all_ok = False

    # Test ServerManager
    try:
        manager = ServerManager()
        servers = manager.get_servers()
        assert isinstance(servers, list)
        manager.stop_all()
        print(f"  ✅ ServerManager: 启动/停止正常")
    except Exception as e:
        print(f"  ❌ ServerManager: {e}")
        all_ok = False

print()
print("=" * 60)
if all_ok:
    print("  全部检查通过！✅")
else:
    print("  存在错误，请修复！❌")
print("=" * 60)
