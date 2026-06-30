# Java 环境扫描与管理 - 参考 MSLX JavaScannerService

from __future__ import annotations
import os
import re
import subprocess
import glob as glob_module
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..logger import log_info, log_debug, log_warn, log_error


@dataclass
class JavaInfo:
    """Java 环境信息"""
    path: str = ""              # java 可执行文件绝对路径
    home: str = ""              # JAVA_HOME
    version: str = ""           # 版本号 (例如 "21.0.1")
    major_version: int = 0      # 主版本号 (例如 21)
    vendor: str = "Unknown"     # 供应商
    is_64bit: bool = True       # 是否 64 位

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "home": self.home,
            "version": self.version,
            "major_version": self.major_version,
            "vendor": self.vendor,
            "is_64bit": self.is_64bit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> JavaInfo:
        return cls(**data)


def _get_java_major_version(java_path: str) -> int:
    """获取 Java 主版本号"""
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stderr + result.stdout
        match = re.search(r'"(\d+)(?:\.(\d+))?', output)
        if match:
            major = int(match.group(1))
            if major == 1:
                return int(match.group(2)) if match.group(2) else 8
            return major
        return 0
    except Exception:
        return 0


def _validate_and_parse_java(java_path: str) -> Optional[JavaInfo]:
    """验证并解析 Java 版本信息"""
    if not os.path.isfile(java_path):
        return None

    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10
        )
    except (subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None

    output = result.stderr + result.stdout

    # 解析版本号
    ver_match = re.search(r'"(\d+\.\d+(?:\.\d+)?(?:_\d+)?)"', output)
    if not ver_match:
        return None

    version_str = ver_match.group(1)
    major = _get_java_major_version(java_path)
    if major == 0:
        return None

    # 解析供应商
    vendor = "Unknown"
    vendor_match = re.search(r'(OpenJDK|Oracle|Microsoft|BellSoft|Azul|Eclipse|IBM|Graal)', output, re.IGNORECASE)
    if vendor_match:
        vendor = vendor_match.group(1)

    # 检测 64 位
    is_64 = "64-Bit" in output or "amd64" in output or "x86_64" in output

    # 推断 JAVA_HOME
    java_home = ""
    real_path = os.path.realpath(java_path)
    # 向上查找 jdk 目录
    parts = real_path.replace("\\", "/").split("/")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].lower().startswith("jdk") or parts[i].lower().startswith("jre") or parts[i].lower() == "java":
            java_home = "/".join(parts[:i + 1])
            break

    return JavaInfo(
        path=os.path.abspath(java_path),
        home=java_home,
        version=version_str,
        major_version=major,
        vendor=vendor,
        is_64bit=is_64,
    )


# 常见 Java 搜索路径
WINDOWS_SEARCH_ROOTS = [
    r"C:\Program Files\Java",
    r"C:\Program Files (x86)\Java",
    r"C:\Program Files\Eclipse Adoptium",
    r"C:\Program Files\Eclipse Foundation",
    r"C:\Program Files\BellSoft",
    r"C:\Program Files\Zulu",
    r"C:\Program Files\AdoptOpenJDK",
    r"C:\Program Files\Microsoft",
    r"C:\Program Files\Amazon Corretto",
    r"C:\Program Files\GraalVM",
]

LINUX_SEARCH_ROOTS = [
    "/usr/lib/jvm",
    "/usr/java",
    "/opt/java",
    "/usr/lib/sdkman/candidates/java",
]

MACOS_SEARCH_ROOTS = [
    "/Library/Java/JavaVirtualMachines",
    "/System/Library/Java/JavaVirtualMachines",
]


def _search_path_env() -> list[str]:
    """从 PATH 环境变量搜索 Java"""
    found = set()
    path_env = os.environ.get("PATH", "")
    for p in path_env.split(";" if os.name == "nt" else ":"):
        p = p.strip().strip('"')
        if not p:
            continue
        for exe in ("java.exe", "javaw.exe") if os.name == "nt" else ("java",):
            full = os.path.join(p, exe)
            if os.path.isfile(full):
                found.add(os.path.abspath(full))
    return list(found)


def _search_common_dirs() -> list[str]:
    """从常见安装目录搜索 Java"""
    found = set()
    if os.name == "nt":
        roots = WINDOWS_SEARCH_ROOTS
    elif os.name == "darwin":
        roots = MACOS_SEARCH_ROOTS
        # macOS 还可以用 /usr/libexec/java_home
        try:
            result = subprocess.run(
                ["/usr/libexec/java_home", "-V"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stderr.split("\n"):
                match = re.search(r'/(.+?/Home)', line)
                if match:
                    java_home_path = "/" + match.group(1)
                    java_bin = os.path.join(java_home_path, "bin", "java")
                    if os.path.isfile(java_bin):
                        found.add(os.path.abspath(java_bin))
        except Exception:
            pass
    else:
        roots = LINUX_SEARCH_ROOTS

    # 用户主目录下的常见位置
    home = os.path.expanduser("~")
    user_roots = [
        os.path.join(home, ".jdks"),
        os.path.join(home, ".sdkman", "candidates", "java"),
        os.path.join(home, "sdkman", "candidates", "java"),
    ]
    roots = list(roots) + user_roots

    for root in roots:
        if not os.path.exists(root):
            continue
        try:
            for dirpath, _, filenames in os.walk(root):
                for exe in ("java.exe", "javaw.exe") if os.name == "nt" else ("java",):
                    if exe in filenames:
                        full_path = os.path.join(dirpath, exe)
                        found.add(os.path.abspath(full_path))
        except PermissionError:
            continue
        except Exception as e:
            log_debug(f"搜索目录 {root} 出错: {e}")

    return list(found)


def scan_java(force_refresh: bool = False) -> list[JavaInfo]:
    """扫描系统 Java 环境
    
    Args:
        force_refresh: 是否强制重新扫描
    
    Returns:
        JavaInfo 列表，按版本号降序排列
    """
    # 收集候选路径
    candidates = set()

    # JAVA_HOME
    java_home = os.environ.get("JAVA_HOME", "")
    if java_home:
        for exe in ("java.exe", "javaw.exe") if os.name == "nt" else ("java",):
            path = os.path.join(java_home, "bin", exe)
            if os.path.isfile(path):
                candidates.add(os.path.abspath(path))

    # PATH
    for path in _search_path_env():
        candidates.add(path)

    # 常见目录
    for path in _search_common_dirs():
        candidates.add(path)

    if not candidates:
        log_warn("未找到任何 Java 候选路径")
        return []

    log_info(f"正在扫描 {len(candidates)} 个 Java 候选路径...")

    # 并发验证
    results: list[JavaInfo] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(_validate_and_parse_java, path): path
            for path in candidates
        }
        for future in as_completed(futures):
            try:
                info = future.result()
                if info:
                    results.append(info)
            except Exception:
                pass

    if not results:
        log_warn("未找到可用的 Java 环境")
        return []

    # 按版本号降序排列，优先 java.exe 而非 javaw.exe
    results.sort(key=lambda x: (x.major_version, "javaw.exe" not in x.path, x.version), reverse=True)

    log_info(f"找到 {len(results)} 个 Java 环境")
    for j in results:
        log_debug(f"  Java {j.major_version}: {j.path} ({j.vendor})")

    return results


def find_java(min_version: int = 8, specific_version: Optional[int] = None) -> Optional[JavaInfo]:
    """查找指定版本的 Java
    
    Args:
        min_version: 最低主版本号
        specific_version: 指定的版本号（精确匹配）
    
    Returns:
        匹配的 JavaInfo，未找到返回 None
    """
    all_java = scan_java()
    if not all_java:
        return None

    if specific_version:
        # 精确匹配
        for j in all_java:
            if j.major_version == specific_version:
                return j
        return None

    # 查找 >= min_version 且最接近的
    for j in all_java:
        if j.major_version >= min_version:
            return j

    return None
