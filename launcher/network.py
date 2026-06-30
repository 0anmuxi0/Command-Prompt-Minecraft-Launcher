# 网络请求模块

import json
import urllib.request
import urllib.error
import ssl
from .logger import log_info, log_debug, log_warn, log_error, log_success

# 默认超时时间（秒）
DEFAULT_TIMEOUT = 30
# 最大重试次数
MAX_RETRIES = 3

# 用户代理
USER_AGENT = "Command Server Launcher/1.0.0"

# BMCLAPI 镜像
BMCLAPI_MIRROR = "https://bmclapi2.bangbang93.com"


def _create_request(url: str, method: str = "GET", headers: dict | None = None, data: bytes | None = None):
    # 创建 HTTP 请求对象
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    return req


def net_request(url: str, method: str = "GET", headers: dict | None = None,
                post_data: dict | None = None, timeout: int = DEFAULT_TIMEOUT,
                use_mirror: bool = False) -> tuple[int, str | dict | None]:
    # 网络请求
    #
    # 返回: (状态码, 响应体)
    # 成功时响应体为 dict（JSON）或 str（非 JSON）
    # 失败时响应体为 None
    if use_mirror and "minecraft" in url:
        url = url.replace("https://launchermeta.mojang.com", BMCLAPI_MIRROR)
        url = url.replace("https://resources.download.minecraft.net", f"{BMCLAPI_MIRROR}/assets")
        url = url.replace("https://libraries.minecraft.net", f"{BMCLAPI_MIRROR}/libraries")
        url = url.replace("https://piston-data.mojang.com", BMCLAPI_MIRROR)
        url = url.replace("https://meta.fabricmc.net", f"{BMCLAPI_MIRROR}/fabric-meta")
        url = url.replace("https://maven.fabricmc.net", f"{BMCLAPI_MIRROR}/fabric-maven")

    data = None
    if post_data is not None:
        data = json.dumps(post_data).encode("utf-8")

    for attempt in range(MAX_RETRIES):
        try:
            log_debug(f"请求 [{method}] {url}")
            req = _create_request(url, method, headers, data)
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                status = resp.status
                raw = resp.read()
                
                # 尝试解析 JSON
                try:
                    result = json.loads(raw.decode("utf-8"))
                except:
                    result = raw.decode("utf-8", errors="replace")
                
                log_debug(f"响应状态: {status}")
                return status, result
                
        except urllib.error.HTTPError as e:
            log_warn(f"HTTP 错误: {e.code} {e.reason} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                return e.code, None
        except urllib.error.URLError as e:
            log_warn(f"网络错误: {e.reason} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                return 0, None
        except Exception as e:
            log_error(f"请求异常: {e}")
            return 0, None

    return 0, None


def net_download(url: str, save_path: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    # 下载文件（单文件）
    import os
    for attempt in range(MAX_RETRIES):
        try:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            req = _create_request(url)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                with open(save_path, "wb") as f:
                    f.write(resp.read())
            return True
        except urllib.error.HTTPError as e:
            log_warn(f"HTTP {e.code}: {save_path} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                return False
        except Exception as e:
            log_warn(f"下载失败: {os.path.basename(save_path)} - {e} (尝试 {attempt + 1}/{MAX_RETRIES})")
            if attempt == MAX_RETRIES - 1:
                return False
    return False


def net_get_manifest(use_mirror: bool = True) -> dict | None:
    # 获取 Minecraft 版本清单 (version_manifest_v2.json)
    url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
    if use_mirror:
        url = f"{BMCLAPI_MIRROR}/mc/game/version_manifest_v2.json"
    
    code, data = net_request(url, use_mirror=False)
    if code == 200 and isinstance(data, dict):
        return data
    return None
