# Command Server Launcher

纯命令行的 Minecraft 启动器，提供简洁高效的 Minecraft 版本管理与启动体验。

> **基于 EPL 协议开源** | **[GitHub Releases](https://github.com/0anmuxi0/Command-Prompt-Minecraft-Launcher/releases)**

## 功能

- **账号管理** — 支持离线登录、微软正版 OAuth 登录、第三方 Yggdrasil 认证
- **版本管理** — 下载官方 Minecraft 版本（正式版 / 快照），支持版本检测与删除
- **整合包安装** — 支持 CurseForge / Modrinth / HMCL / MultiMC / MCBBS 格式
- **游戏启动** — 自动检测 Java 版本，智能匹配；支持原生库解压、JVM 参数定制
- **BMCLAPI 镜像** — 内置 BMCLAPI 镜像加速下载
- **多线程下载** — 可配置线程数、重试次数、超时时间
- **版本隔离** — 支持按版本独立存储游戏目录
- **窗口设置** — 自定义分辨率、内存分配、自动进服

## 预览

```
[16:34:48] [main/SUCCESS] Command Server Launcher - 纯命令行 MC 启动器
[16:34:48] [main/INFO] [1] 账号管理
[16:34:48] [main/INFO] [2] 启动游戏
[16:34:48] [main/INFO] [3] 安装 Minecraft 版本
[16:34:48] [main/INFO] [4] 安装整合包
[16:34:48] [main/INFO] [5] 版本管理
[16:34:48] [main/INFO] [6] 设置
[16:34:48] [main/INFO] [0] 退出
[16:34:48] [main/REQUEST] 请选择操作:
```

## 快速开始

### 使用预构建版本

从 [Releases](https://github.com/0anmuxi0/Command-Prompt-Minecraft-Launcher/releases) 下载 `Command Server Launcher.exe`，双击运行。

### 从源码解释d运行

```bash
# 克隆仓库
git clone https://github.com/0anmuxi0/Command-Prompt-Minecraft-Launcher.git
cd Command-Prompt-Minecraft-Launcher

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

### 自行构建

```bash
# Windows
build.bat

# 手动构建
pip install pyinstaller
pip install -r requirements.txt
pyinstaller --onefile --console --name "Command Server Launcher" --add-data "launcher;launcher" main.py
```

## 使用说明

### 主菜单

| 选项 | 功能 |
|------|------|
| `1` | 账号管理 — 添加/切换/删除登录账号 |
| `2` | 启动游戏 — 选择已安装的版本并启动 |
| `3` | 安装 Minecraft 版本 — 从官方下载正式版或快照 |
| `4` | 安装整合包 — 从 `.zip` / `.mrpack` 安装整合包 |
| `5` | 版本管理 — 查看和删除已安装的版本 |
| `6` | 设置 — 配置 Java 路径、内存、分辨率等 |

### 设置项

| 设置 | 说明 |
|------|------|
| Java 路径 | 自定义 Java 路径，留空自动检测 |
| 最小/最大内存 | 分配内存 (MB) |
| 游戏目录 | Minecraft 数据存储路径 |
| 版本隔离 | 将每个版本独立存放在各自文件夹 |
| 额外 JVM 参数 | 自定义 JVM 启动参数 |
| 窗口大小 | 游戏分辨率 |
| 自动进服 | 启动后自动连接到指定服务器 |
| 下载线程数 | 多线程下载并发数 |
| 微软 OAuth Client ID | 自定义微软登录 Client ID |

### 支持的整合包格式

| 格式 | 标识文件 |
|------|----------|
| CurseForge | `manifest.json` |
| Modrinth | `modrinth.index.json` |
| HMCL | `modpack.json` |
| MultiMC | `mmc-pack.json` |
| MCBBS | `mcbbs.packmeta` |

## 项目结构

```
Command Server Launcher/
├── main.py                 # 主入口
├── build.bat               # 构建脚本
├── requirements.txt        # Python 依赖
├── launcher/
│   ├── __init__.py
│   ├── logger.py           # 日志系统（彩色输出）
│   ├── config.py           # 配置管理（JSON）
│   ├── login.py            # 登录认证（离线/微软/Yggdrasil）
│   ├── minecraft.py        # Minecraft 版本管理
│   ├── launch.py           # 游戏启动引擎
│   ├── modpack.py          # 整合包检测与安装
│   ├── downloader.py       # 多线程下载器
│   └── network.py          # 网络请求工具
└── logs/                   # 运行日志
```

## 技术栈

- Python 3.10+
- requests >= 2.25.0
- urllib3 >= 1.26.0
- Java (自动检测，支持 Java 8~25)

## License

[EPL](LICENSE) © 0anmuxi0
