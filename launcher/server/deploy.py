# 服务器核心下载 - 参考 MSLX ServerDeploymentService.DeployCoreAsync

from __future__ import annotations
import os
import re
import signal
import zipfile
import shutil
import subprocess
from typing import Callable

from ..logger import log_info, log_warn, log_error, log_success
from ..network import net_request, net_download


# 核心下载器
def download_core(core_type: str, mc_version: str, dest_dir: str,
                  progress: Callable[[str, int], None] | None = None) -> str:
    """下载服务端核心文件到指定目录
    
    Args:
        core_type: 核心类型 (vanilla/paper/purpur/fabric/forge/neoforge)
        mc_version: Minecraft 版本号
        dest_dir: 目标目录
        progress: 进度回调 (消息, 百分比)
    
    Returns:
        核心文件名，失败返回空字符串
    """
    def report(msg, pct=0):
        if progress:
            progress(msg, pct)
        log_info(msg)

    os.makedirs(dest_dir, exist_ok=True)

    downloaders = {
        "vanilla": _download_vanilla,
        "paper": _download_paper,
        "purpur": _download_purpur,
        "fabric": _download_fabric,
        "forge": _download_forge,
        "neoforge": _download_neoforge,
    }

    dl = downloaders.get(core_type.lower())
    if not dl:
        log_error(f"不支持的核心类型: {core_type}")
        return ""

    if not mc_version:
        log_error("未指定 Minecraft 版本")
        return ""

    report(f"下载 {core_type} {mc_version}...", 5)
    return dl(mc_version, dest_dir, report)


def _download_vanilla(version: str, dest_dir: str, report: Callable) -> str:
    """下载原版服务端"""
    core_name = f"minecraft_server.{version}.jar"
    dest = os.path.join(dest_dir, core_name)
    dest_tmp = dest + ".tmp"

    # 尝试多个镜像源
    mirrors = [
        f"https://bmclapi2.bangbang93.com/version/{version}/server",
        f"https://download.mcbbs.net/version/{version}/server",
    ]

    for i, dl_url in enumerate(mirrors):
        from urllib.parse import urlparse
        host = urlparse(dl_url).netloc
        report(f"从 {host} 下载 {core_name}...", 20 + i * 20)
        try:
            import urllib.request, ssl
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            req = urllib.request.Request(dl_url, headers={"User-Agent": "CML/1.0"})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(dest_tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = downloaded * 100 // total
                            if pct % 25 == 0:
                                report(f"下载 {core_name} {downloaded//1048576}MB/{total//1048576}MB ({pct}%)", 20 + i * 20 + pct // 5)
            os.replace(dest_tmp, dest)
            log_success(f"原版 {version} 下载完成")
            return core_name
        except Exception as e:
            log_warn(f"{host} 失败: {e}")
            if os.path.exists(dest_tmp):
                os.remove(dest_tmp)
            continue

    # 最终: 通过 version_manifest 获取官方 URL
    log_warn("镜像直链均失败，尝试通过版本清单获取...")
    report("获取版本清单...", 10)
    for manifest_url in [
        "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json",
        "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
    ]:
        try:
            code, manifest = net_request(manifest_url, timeout=30)
            if code == 200 and isinstance(manifest, dict):
                for v in manifest.get("versions", []):
                    if v.get("id") == version:
                        vinfo_url = v.get("url", "")
                        if not vinfo_url:
                            break
                        code2, vinfo = net_request(vinfo_url, timeout=30)
                        if code2 == 200 and isinstance(vinfo, dict):
                            surl = vinfo.get("downloads", {}).get("server", {}).get("url", "")
                            if surl:
                                report(f"下载 {core_name}...", 40)
                                if net_download(surl, dest):
                                    log_success(f"原版 {version} 下载完成")
                                    return core_name
                        break
        except Exception:
            continue

    log_error(f"原版 {version} 下载失败，请检查网络或手动下载")
    return ""


def _download_paper(version: str, dest_dir: str, report: Callable) -> str:
    """下载 Paper 服务端"""
    report("获取构建列表...", 10)
    api_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds"
    code, data = net_request(api_url)
    if code != 200 or not isinstance(data, dict):
        log_error(f"获取 Paper {version} 构建列表失败")
        return ""

    builds = data.get("builds", [])
    if not builds:
        log_error(f"未找到 Paper {version} 的构建")
        return ""

    target = builds[-1]
    build_num = target["build"]
    dl_name = target.get("downloads", {}).get("application", {}).get("name", "")
    if not dl_name:
        log_error("未找到 Paper 下载文件")
        return ""

    dl_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{build_num}/downloads/{dl_name}"
    core_name = f"paper-{version}-{build_num}.jar"
    dest = os.path.join(dest_dir, core_name)

    report(f"下载 Paper {version} build #{build_num}...", 40)
    if not net_download(dl_url, dest):
        log_error("Paper 下载失败")
        return ""

    log_success(f"Paper {version}-{build_num} 下载完成")
    return core_name


def _download_purpur(version: str, dest_dir: str, report: Callable) -> str:
    """下载 Purpur 服务端"""
    core_name = f"purpur-{version}.jar"
    dest = os.path.join(dest_dir, core_name)
    dl_url = f"https://api.purpurmc.org/v2/purpur/{version}/latest/download"

    report(f"下载 {core_name}...", 40)
    if not net_download(dl_url, dest):
        log_error("Purpur 下载失败")
        return ""

    log_success(f"Purpur {version} 下载完成")
    return core_name


def _download_fabric(version: str, dest_dir: str, report: Callable) -> str:
    """下载 Fabric 服务端启动器"""
    report("获取 Fabric 版本信息...", 10)
    code, data = net_request("https://bmclapi2.bangbang93.com/fabric-meta/versions")
    if code != 200 or not isinstance(data, list):
        log_error("获取 Fabric 版本信息失败")
        return ""

    loaders = [item for item in data if isinstance(item, dict) and item.get("loader")]
    if not loaders:
        log_error("未找到 Fabric 加载器")
        return ""

    loader_ver = loaders[-1]["loader"]["version"]  # type: ignore
    core_name = f"fabric-server-launch-{loader_ver}.jar"
    dest = os.path.join(dest_dir, core_name)
    dl_url = (f"https://bmclapi2.bangbang93.com/maven/net/fabricmc/"
              f"fabric-server-launch/{loader_ver}/{core_name}")

    report(f"下载 Fabric {loader_ver}...", 40)
    if not net_download(dl_url, dest):
        log_warn("Fabric 服务端启动器下载失败，尝试安装器...")
        installer_ver = "1.0.0"
        installer_name = f"fabric-installer-{installer_ver}.jar"
        installer_url = (f"https://bmclapi2.bangbang93.com/maven/net/fabricmc/"
                        f"fabric-installer/{installer_ver}/{installer_name}")
        installer_dest = os.path.join(dest_dir, installer_name)
        if not net_download(installer_url, installer_dest):
            log_error("Fabric 安装器下载失败")
            return ""
        _write_fabric_script(dest_dir, version, loader_ver, installer_name)
        return installer_name

    log_success(f"Fabric {loader_ver} 下载完成")
    return core_name


def _write_fabric_script(base_path: str, mc_version: str, loader_ver: str, installer: str):
    """创建 Fabric 安装脚本"""
    if os.name == "nt":
        content = f"@echo off\njava -jar {installer} server -mcversion {mc_version} -loader {loader_ver} -downloadMinecraft\npause\n"
        path = os.path.join(base_path, "install_fabric.bat")
    else:
        content = f"#!/bin/bash\njava -jar {installer} server -mcversion {mc_version} -loader {loader_ver} -downloadMinecraft\n"
        path = os.path.join(base_path, "install_fabric.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if os.name != "nt":
        os.chmod(path, 0o755)


def _download_forge(version: str, dest_dir: str, report: Callable) -> str:
    """下载 Forge 安装器"""
    core_name = f"forge-{version}-installer.jar"
    dest = os.path.join(dest_dir, core_name)
    url = f"https://bmclapi2.bangbang93.com/forge/version/{version}/download"

    report(f"下载 Forge {version}...", 40)
    if not net_download(url, dest):
        log_error("Forge 下载失败")
        return ""

    _write_forge_script(dest_dir, version, core_name)
    log_success(f"Forge {version} 安装器下载完成")
    return core_name


def _write_forge_script(base_path: str, version: str, installer: str):
    """创建 Forge 安装脚本"""
    if os.name == "nt":
        content = f"@echo off\njava -jar {installer} --installServer\nif exist forge-{version}-universal.jar (\n  echo Forge 安装完成\n) else (\n  echo 请运行: java -jar {installer} --installServer\n)\npause\n"
        path = os.path.join(base_path, "install_forge.bat")
    else:
        content = f"#!/bin/bash\njava -jar {installer} --installServer\n"
        path = os.path.join(base_path, "install_forge.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if os.name != "nt":
        os.chmod(path, 0o755)


def _download_neoforge(version: str, dest_dir: str, report: Callable) -> str:
    """下载 NeoForge 安装器"""
    # NeoForge 版本号格式: 21.1.65 (对应 MC 1.21.1)
    # 将 MC 版本 1.21.1 转为 NeoForge 前缀 21.1
    neoforge_prefix = version
    if version.startswith("1."):
        neoforge_prefix = version[2:]  # 1.21.1 → 21.1
    neoforge_prefix = re.sub(r"\.0$", "", neoforge_prefix)

    # 总是查询 metadata，找到匹配的 NeoForge 版本
    code, data = net_request("https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/maven-metadata.xml")
    if code == 200 and isinstance(data, str):
        all_neo_versions = re.findall(r"<version>([^<]+)</version>", data)
        matching = [v for v in all_neo_versions if v.startswith(neoforge_prefix)]
        if matching:
            version = matching[-1]
            report(f"NeoForge 版本: {version}", 20)
        else:
            # 没找到匹配，尝试直接搜索版本号中的 MC 版本标识
            log_warn(f"未找到 NeoForge 版本前缀 {neoforge_prefix}，尝试精确匹配...")
            if version in all_neo_versions:
                pass  # version 已经是完整 NeoForge 版本号
            else:
                log_error(f"NeoForge {version} 在 BMCLAPI 上未找到")
                return ""

    core_name = f"neoforge-{version}-installer.jar"
    dest = os.path.join(dest_dir, core_name)
    url = f"https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/{version}/{core_name}"

    report(f"下载 NeoForge {version}...", 40)
    if not net_download(url, dest):
        log_error("NeoForge 下载失败")
        return ""

    _write_neoforge_script(dest_dir, version, core_name)
    log_success(f"NeoForge {version} 安装器下载完成")
    return core_name


def _write_neoforge_script(base_path: str, version: str, installer: str):
    """创建 NeoForge 安装脚本"""
    if os.name == "nt":
        content = f"@echo off\njava -jar {installer} --install-server {base_path}\npause\n"
        path = os.path.join(base_path, "install_neoforge.bat")
    else:
        content = f"#!/bin/bash\njava -jar {installer} --install-server {base_path}\n"
        path = os.path.join(base_path, "install_neoforge.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    if os.name != "nt":
        os.chmod(path, 0o755)


def install_package(package_path: str, target_dir: str,
                    progress: Callable[[str, int], None] | None = None) -> bool:
    """安装整合包（解压到目标目录，自动去套娃）"""
    def report(msg, pct=0):
        if progress:
            progress(msg, pct)
        log_info(msg)

    if not os.path.isfile(package_path):
        log_error(f"文件不存在: {package_path}")
        return False

    report("解压整合包...", 10)
    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(target_dir)

    dirs = [d for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))]
    files = [f for f in os.listdir(target_dir) if os.path.isfile(os.path.join(target_dir, f))]

    if not files and len(dirs) == 1:
        report("检测到嵌套目录，调整结构...", 30)
        nested = os.path.join(target_dir, dirs[0])
        for item in os.listdir(nested):
            shutil.move(os.path.join(nested, item), os.path.join(target_dir, item))
        os.rmdir(nested)

    report("整合包安装完成", 50)
    return True


def run_forge_installer(installer_path: str, server_dir: str,
                        java_path: str = "java",
                        max_retries: int = 3,
                        progress: Callable[[str, int], None] | None = None) -> str:
    """运行 Forge/NeoForge 安装器，完成后返回实际服务端核心文件名
    
    流程:
        1. java -jar installer.jar --install-server <dir>
        2. 等待安装完成
        3. 查找生成的服务端 jar
    
    Args:
        max_retries: 失败重试次数（默认3，设为0不重试）
    
    Returns:
        服务端核心文件名（如 neoforge-21.1.234.jar），失败返回空字符串
    """
    def report(msg, pct=0):
        if progress:
            progress(msg, pct)
        log_info(msg)

    if not os.path.isfile(installer_path):
        log_error(f"安装器不存在: {installer_path}")
        return ""

    installer_name = os.path.basename(installer_path)
    is_neoforge = "neo" in installer_name.lower()

    retries = max_retries if max_retries > 0 else 999  # 0 = 无限重试
    for attempt in range(1, retries + 1):
        if attempt > 1:
            log_warn(f"第 {attempt} 次重试安装...")
            if os.path.exists(server_dir):
                temp_dir = os.path.join(server_dir, "temp")
                if os.path.isdir(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)

        report(f"正在安装 {installer_name}{' (第'+str(attempt)+'次)' if attempt > 1 else ''}...", 60)
        try:
            proc = subprocess.Popen(
                [java_path, "-jar", installer_path, "--install-server", server_dir],
                cwd=server_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            assert proc.stdout is not None
            success = True
            for raw in iter(proc.stdout.readline, b""):
                if not raw:
                    break
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    text = raw.decode("gbk", errors="replace")
                line = text.rstrip("\r\n")
                if line:
                    log_info(f"{line}")

            proc.stdout.close()
            proc.wait(timeout=120)

        except subprocess.TimeoutExpired:
            log_error("安装器超时（120秒）")
            _kill_process(proc.pid)
            continue  # 重试
        except FileNotFoundError:
            log_error(f"Java 未找到: {java_path}")
            return ""
        except Exception as e:
            log_error(f"安装过程出错: {e}")
            return ""

        if proc.returncode != 0:
            log_error(f"安装器退出码: {proc.returncode}")
            # 非零退出码可能是网络问题，重试
            continue

        # 查找实际服务端核心
        server_jar = _find_server_jar(server_dir, installer_name, is_neoforge)
        if server_jar:
            try:
                os.remove(installer_path)
                log_info("已删除安装器")
            except Exception:
                pass
            log_success(f"安装完成，服务端核心: {server_jar}")
            return server_jar

        log_error("安装完成但未找到服务端核心文件，重试...")
        continue

    log_error(f"安装失败，已重试 {retries} 次，请检查网络或手动运行:")
    log_info(f"  java -jar {installer_name} --install-server {server_dir}")
    return ""


def _find_server_jar(server_dir: str, installer_name: str, is_neoforge: bool) -> str:
    """在安装目录中查找安装器生成的服务端核心文件"""
    # 策略1: 匹配 neoforge-{version}.jar（去掉 -installer）
    base = installer_name.replace("-installer.jar", ".jar")
    candidate = os.path.join(server_dir, base)
    if os.path.isfile(candidate):
        return base

    # 策略2: neoforge-{version}.jar（可能版本号中有差异）
    pattern = installer_name.replace("-installer.jar", "")
    for f in sorted(os.listdir(server_dir), key=str.lower):
        if f.endswith(".jar") and "installer" not in f:
            if f.startswith(pattern.split("-")[0]) and pattern.split("-")[-1] in f:
                return f

    # 策略3: forge-{version}-universal.jar / forge-{version}.jar
    if not is_neoforge:
        for f in os.listdir(server_dir):
            if f.endswith(".jar") and "forge" in f.lower() and "installer" not in f:
                if "universal" in f or f.endswith(".jar"):
                    return f

    # 策略4 (NeoForge): 从 run.bat 解析 @libraries/... 路径
    if is_neoforge:
        run_bat = os.path.join(server_dir, "run.bat")
        if os.path.isfile(run_bat):
            try:
                with open(run_bat, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                import re
                m = re.search(r'@user_jvm_args\.txt\s+(@\S+)', content)
                if m:
                    lib_path = m.group(1)
                    full_path = os.path.join(server_dir, lib_path.lstrip("@"))
                    if os.path.isfile(full_path):
                        log_info(f"NeoForge 启动参数: {lib_path}")
                        return lib_path
            except Exception:
                pass

    return ""


def _kill_process(pid: int):
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
