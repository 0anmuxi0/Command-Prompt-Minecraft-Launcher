# 服务器核心下载 - 参考 MSLX ServerDeploymentService.DeployCoreAsync

from __future__ import annotations
import os
import re
import zipfile
import shutil
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
    if not re.match(r"^\d+\.\d+", version):
        code, data = net_request("https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/maven-metadata.xml")
        if code == 200 and isinstance(data, str):
            versions = re.findall(r"<version>([^<]+)</version>", data)
            matching = [v for v in versions if v.startswith(version)]
            if matching:
                version = matching[-1]

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
    try:
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
    except zipfile.BadZipFile:
        log_error("ZIP 文件损坏")
        return False
    
    def _download_server_core(self, core_type: str, mc_version: str,
                               build: str, base_path: str,
                               report: Callable) -> str:
        """下载服务端核心文件"""
        if not mc_version:
            log_error("未指定 Minecraft 版本")
            return ""
        
        core_type = core_type.lower()
        
        if core_type == "vanilla":
            return self._download_vanilla(mc_version, base_path, report)
        elif core_type == "paper":
            return self._download_paper(mc_version, build, base_path, report)
        elif core_type == "purpur":
            return self._download_purpur(mc_version, base_path, report)
        elif core_type == "fabric":
            return self._download_fabric(mc_version, base_path, report)
        elif core_type == "forge":
            return self._download_forge(mc_version, base_path, report)
        elif core_type == "neoforge":
            return self._download_neoforge(mc_version, base_path, report)
        else:
            log_error(f"不支持的核心类型: {core_type}")
            return ""
    
    def _download_vanilla(self, version: str, base_path: str,
                          report: Callable) -> str:
        """下载原版服务端"""
        report(f"正在下载原版 {version} 服务端...", 15)
        
        # 通过 BMCLAPI 获取版本信息
        url = f"https://bmclapi2.bangbang93.com/version/{version}/server"
        code, data = net_request(url, use_mirror=False)
        
        if code != 200 or not isinstance(data, dict):
            log_error(f"获取原版 {version} 信息失败")
            return ""
        
        server_url = data.get("downloads", {}).get("server", {}).get("url", "")
        if not server_url:
            log_error(f"未找到原版 {version} 服务端下载地址")
            return ""
        
        # 替换为 BMCLAPI 镜像
        server_url = server_url.replace("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com")
        server_url = server_url.replace("https://piston-data.mojang.com", "https://bmclapi2.bangbang93.com")
        
        core_name = f"minecraft_server.{version}.jar"
        dest = os.path.join(base_path, core_name)
        
        report(f"正在下载 {core_name}...", 25)
        if not net_download(server_url, dest):
            log_error(f"原版 {version} 服务端下载失败")
            return ""
        
        log_success(f"原版 {version} 服务端下载完成")
        return core_name
    
    def _download_paper(self, version: str, build: str, base_path: str,
                        report: Callable) -> str:
        """下载 Paper 服务端"""
        report(f"正在获取 Paper {version} 构建信息...", 15)
        
        # 获取构建列表
        api_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds"
        code, data = net_request(api_url)
        
        if code != 200 or not isinstance(data, dict):
            log_error(f"获取 Paper {version} 构建列表失败")
            return ""
        
        builds = data.get("builds", [])
        if not builds:
            log_error(f"未找到 Paper {version} 的构建")
            return ""
        
        # 选择构建
        if build == "latest":
            target_build = builds[-1]
        else:
            target_build = None
            for b in builds:
                if str(b.get("build", "")) == build:
                    target_build = b
                    break
            if not target_build:
                log_error(f"未找到 Paper {version} 构建 #{build}")
                return ""
        
        build_num = target_build["build"]
        download_name = target_build.get("downloads", {}).get("application", {}).get("name", "")
        
        if not download_name:
            log_error("未找到 Paper 下载文件")
            return ""
        
        download_url = (f"https://api.papermc.io/v2/projects/paper/versions/{version}"
                       f"/builds/{build_num}/downloads/{download_name}")
        
        core_name = f"paper-{version}-{build_num}.jar"
        dest = os.path.join(base_path, core_name)
        
        report(f"正在下载 Paper {version} build #{build_num}...", 25)
        if not net_download(download_url, dest):
            log_error("Paper 下载失败")
            return ""
        
        log_success(f"Paper {version} build #{build_num} 下载完成")
        return core_name
    
    def _download_purpur(self, version: str, base_path: str, report: Callable) -> str:
        """下载 Purpur 服务端"""
        report(f"正在下载 Purpur {version}...", 15)
        
        download_url = f"https://api.purpurmc.org/v2/purpur/{version}/latest/download"
        core_name = f"purpur-{version}.jar"
        dest = os.path.join(base_path, core_name)
        
        if not net_download(download_url, dest):
            log_error("Purpur 下载失败")
            return ""
        
        log_success(f"Purpur {version} 下载完成")
        return core_name
    
    def _download_fabric(self, version: str, base_path: str, report: Callable) -> str:
        """下载 Fabric 服务端"""
        report(f"正在获取 Fabric {version} 加载器信息...", 15)
        
        # 获取 Fabric 加载器版本
        api_url = "https://bmclapi2.bangbang93.com/fabric-meta/versions"
        code, data = net_request(api_url)
        
        if code != 200 or not isinstance(data, list):
            log_error("获取 Fabric 版本信息失败")
            return ""
        
        # 找最新的加载器
        loaders = [item for item in data if item.get("loader", {}).get("version", "")]
        if not loaders:
            log_error("未找到 Fabric 加载器")
            return ""
        
        latest_loader = loaders[-1]["loader"]["version"]
        
        # 获取安装器版本
        installer_version = "1.0.0"  # 默认
        
        # 下载 Fabric 服务端启动器
        # 使用 fabric-server-launch
        server_launcher_url = (f"https://bmclapi2.bangbang93.com/maven/net/fabricmc/"
                              f"fabric-server-launch/{latest_loader}/"
                              f"fabric-server-launch-{latest_loader}.jar")
        
        core_name = f"fabric-server-launch-{latest_loader}.jar"
        dest = os.path.join(base_path, core_name)
        
        report(f"正在下载 Fabric 服务端启动器 {latest_loader}...", 25)
        
        # 如果直接下载失败，尝试使用 fabric-installer
        if not net_download(server_launcher_url, dest):
            log_warn("Fabric 服务端启动器下载失败，尝试使用安装器...")
            
            installer_url = (f"https://bmclapi2.bangbang93.com/maven/net/fabricmc/"
                           f"fabric-installer/{installer_version}/"
                           f"fabric-installer-{installer_version}.jar")
            installer_name = f"fabric-installer-{installer_version}.jar"
            installer_dest = os.path.join(base_path, installer_name)
            
            if not net_download(installer_url, installer_dest):
                log_error("Fabric 安装器下载失败")
                return ""
            
            # 创建安装脚本
            self._create_fabric_install_script(base_path, version, latest_loader, installer_name)
            return installer_name
        
        return core_name
    
    def _create_fabric_install_script(self, base_path: str, mc_version: str,
                                       loader_version: str, installer_name: str):
        """创建 Fabric 安装脚本"""
        if os.name == "nt":
            script_content = f"""@echo off
java -jar {installer_name} server -mcversion {mc_version} -loader {loader_version} -downloadMinecraft
pause
"""
            script_path = os.path.join(base_path, "install_fabric.bat")
        else:
            script_content = f"""#!/bin/bash
java -jar {installer_name} server -mcversion {mc_version} -loader {loader_version} -downloadMinecraft
"""
            script_path = os.path.join(base_path, "install_fabric.sh")
        
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)
        
        if os.name != "nt":
            os.chmod(script_path, 0o755)
    
    def _download_forge(self, version: str, base_path: str, report: Callable) -> str:
        """下载 Forge 服务端"""
        report(f"正在获取 Forge {version} 信息...", 15)
        
        # 通过 BMCLAPI 获取 Forge 版本
        url = f"https://bmclapi2.bangbang93.com/forge/version/{version}/download"
        core_name = f"forge-{version}-installer.jar"
        dest = os.path.join(base_path, core_name)
        
        report(f"正在下载 Forge {version} 安装器...", 25)
        if not net_download(url, dest):
            log_error("Forge 下载失败")
            return ""
        
        # 创建安装脚本
        if os.name == "nt":
            script = f"""@echo off
java -jar {core_name} --installServer
if exist forge-{version}-universal.jar (
    echo Forge 安装完成
) else (
    echo 请手动运行: java -jar {core_name} --installServer
)
pause
"""
            with open(os.path.join(base_path, "install_forge.bat"), "w", encoding="utf-8") as f:
                f.write(script)
        else:
            script = f"""#!/bin/bash
java -jar {core_name} --installServer
"""
            with open(os.path.join(base_path, "install_forge.sh"), "w", encoding="utf-8") as f:
                f.write(script)
            os.chmod(os.path.join(base_path, "install_forge.sh"), 0o755)
        
        log_success(f"Forge {version} 安装器下载完成")
        return core_name
    
    def _download_neoforge(self, version: str, base_path: str, report: Callable) -> str:
        """下载 NeoForge 服务端"""
        report(f"正在下载 NeoForge {version}...", 15)
        
        # 先获取实际版本号
        import re
        if not re.match(r'^\d+\.\d+', version):
            # 可能是 MC 版本号，需要查找对应的 NeoForge 版本
            url = "https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/maven-metadata.xml"
            code, data = net_request(url)
            if code == 200 and isinstance(data, str):
                # 找到匹配的版本
                versions = re.findall(r'<version>([^<]+)</version>', data)
                matching = [v for v in versions if v.startswith(version)]
                if matching:
                    version = matching[-1]
        
        core_name = f"neoforge-{version}-installer.jar"
        download_url = (f"https://bmclapi2.bangbang93.com/maven/net/neoforged/neoforge/"
                       f"{version}/neoforge-{version}-installer.jar")
        dest = os.path.join(base_path, core_name)
        
        report(f"正在下载 NeoForge {version} 安装器...", 25)
        if not net_download(download_url, dest):
            log_error("NeoForge 下载失败")
            return ""
        
        # 创建安装脚本
        if os.name == "nt":
            script = f"""@echo off
java -jar {core_name} --install-server {os.path.join(base_path).replace('/', '\\')}
pause
"""
            with open(os.path.join(base_path, "install_neoforge.bat"), "w", encoding="utf-8") as f:
                f.write(script)
        else:
            script = f"""#!/bin/bash
java -jar {core_name} --install-server {base_path}
"""
            with open(os.path.join(base_path, "install_neoforge.sh"), "w", encoding="utf-8") as f:
                f.write(script)
            os.chmod(os.path.join(base_path, "install_neoforge.sh"), 0o755)
        
        log_success(f"NeoForge {version} 安装器下载完成")
        return core_name
    
    def _install_package(self, request: CreateServerRequest, base_path: str,
                         report: Callable) -> bool:
        """安装整合包"""
        temp_dir = tempfile.mkdtemp(prefix="mslx_pack_")
        
        try:
            zip_path = ""
            if request.package_local_path:
                zip_path = request.package_local_path
            elif request.package_url:
                report("正在下载整合包...", 50)
                zip_name = os.path.basename(request.package_url) or "pack.zip"
                zip_path = os.path.join(temp_dir, zip_name)
                if not net_download(request.package_url, zip_path):
                    log_error("整合包下载失败")
                    return False
            
            if not zip_path or not os.path.exists(zip_path):
                return False
            
            report("正在解压整合包...", 60)
            
            # 解压 ZIP
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(base_path)
                
                # 去套娃：如果解压后根目录只有一个文件夹，将内容上移
                items = os.listdir(base_path)
                if len(items) == 1:
                    single_item = os.path.join(base_path, items[0])
                    if os.path.isdir(single_item):
                        # 检查该目录下是否有明显的服务器文件
                        server_files = [f for f in os.listdir(single_item)
                                       if f.endswith(".jar") or f in ("server.properties", "eula.txt")]
                        if server_files:
                            report("检测到嵌套目录结构，正在调整...", 65)
                            for item in os.listdir(single_item):
                                shutil.move(
                                    os.path.join(single_item, item),
                                    os.path.join(base_path, item)
                                )
                            os.rmdir(single_item)
            except zipfile.BadZipFile:
                log_error("整合包 ZIP 文件损坏")
                return False
            
            report("整合包安装完成", 70)
            return True
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
