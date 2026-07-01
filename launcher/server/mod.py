# 模组管理 - 参考 PCL 实现
# 支持: 列出/禁用/启用/移除/添加模组

from __future__ import annotations
import os
import re
import zipfile
import shutil
import json
from dataclasses import dataclass, field
from typing import Optional

from ..logger import log_info, log_warn, log_error, log_success

MODS_DIR = "mods"
DISABLED_SUFFIX = ".disabled"


@dataclass
class ModInfo:
    name: str = ""              # 显示名（优先中文）
    file_name: str = ""         # 实际文件名
    enabled: bool = True        # 是否启用
    version: str = ""           # 版本号
    path: str = ""              # 完整路径
    description: str = ""       # 描述


def _parse_name_from_jar(jar_path: str) -> tuple[str, str, str]:
    """从 JAR 中提取模组信息，返回 (显示名, 版本, 描述)"""
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            # Fabric
            if "fabric.mod.json" in zf.namelist():
                data = json.loads(zf.read("fabric.mod.json"))
                name = data.get("name", "") or data.get("id", "")
                cn = ""
                for entry in data.get("authors", []):
                    if isinstance(entry, dict):
                        cn = entry.get("name", "")
                # 尝试从自定义字段获取中文名
                custom = data.get("custom", {})
                if isinstance(custom, dict):
                    for key in ("chinese_name", "chineseName", "cn_name"):
                        if key in custom:
                            cn = custom[key]
                            break
                return (name or os.path.splitext(os.path.basename(jar_path))[0],
                        data.get("version", ""),
                        data.get("description", ""))

            # NeoForge / Forge (mods.toml)
            for toml_name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
                if toml_name in zf.namelist():
                    text = zf.read(toml_name).decode("utf-8", errors="replace")
                    m = re.search(r'displayName\s*=\s*"([^"]+)"', text)
                    if not m:
                        m = re.search(r'displayName\s*=\s*([^\s]+)', text)
                    name = m.group(1) if m else ""
                    if not name:
                        m = re.search(r'modId\s*=\s*"([^"]+)"', text)
                        name = m.group(1) if m else os.path.splitext(os.path.basename(jar_path))[0]
                    ver = ""
                    m = re.search(r'version\s*=\s*"([^"]+)"', text)
                    if m:
                        ver = m.group(1)
                    desc = ""
                    m = re.search(r'description\s*=\s*"([^"]+)"', text)
                    if m:
                        desc = m.group(1)
                    return (name, ver, desc)

            # MCMOD.info (旧版)
            if "mcmod.info" in zf.namelist():
                try:
                    data = json.loads(zf.read("mcmod.info"))
                    if isinstance(data, list) and data:
                        entry = data[0]
                        cn = entry.get("name", "")
                        # 尝试中文名
                        for k in ("chineseName", "ChineseName", "cnName"):
                            if k in entry:
                                cn = entry[k]
                                break
                        return (cn or entry.get("modid", os.path.splitext(os.path.basename(jar_path))[0]),
                                entry.get("version", ""),
                                entry.get("description", ""))
                except Exception:
                    pass

            # MANIFEST.MF
            if "META-INF/MANIFEST.MF" in zf.namelist():
                text = zf.read("META-INF/MANIFEST.MF").decode("utf-8", errors="replace")
                m = re.search(r'Implementation-Title:\s*(.+)', text)
                name = m.group(1).strip() if m else ""
                m = re.search(r'Implementation-Version:\s*(.+)', text)
                ver = m.group(1).strip() if m else ""
                if name:
                    return (name, ver, "")

    except Exception:
        pass
    return ("", "", "")


def scan_mods(server_base: str) -> list[ModInfo]:
    """扫描服务器 mods 目录，返回模组列表"""
    mods_path = os.path.join(server_base, MODS_DIR)
    if not os.path.isdir(mods_path):
        return []

    mods: list[ModInfo] = []
    seen_names: dict[str, int] = {}

    for f in sorted(os.listdir(mods_path), key=str.lower):
        full = os.path.join(mods_path, f)

        # 判断启用状态
        enabled = True
        file_name = f
        if f.endswith(DISABLED_SUFFIX):
            enabled = False
            file_name = f[:-len(DISABLED_SUFFIX)]

        if not (file_name.endswith(".jar") or file_name.endswith(".litemod")):
            continue

        # 尝试提取元数据
        display_name, version, desc = "", "", ""
        if enabled and f.endswith(".jar"):
            display_name, version, desc = _parse_name_from_jar(full)
        elif not enabled:
            disabled_path = os.path.join(mods_path, file_name)
            if file_name.endswith(".jar") and os.path.exists(disabled_path):
                display_name, version, desc = _parse_name_from_jar(disabled_path)
            # 从文件名猜测
            display_name = display_name or os.path.splitext(file_name)[0]
        else:
            display_name = os.path.splitext(file_name)[0]

        if not display_name:
            display_name = os.path.splitext(file_name)[0]

        # 去重显示名
        base_name = display_name
        idx = seen_names.get(base_name, 0) + 1
        seen_names[base_name] = idx
        if idx > 1:
            display_name = f"{base_name} ({idx})"

        mods.append(ModInfo(
            name=display_name,
            file_name=file_name,
            enabled=enabled,
            version=version,
            path=full,
            description=desc,
        ))

    return mods


def set_mod_enabled(mod_path: str, enable: bool) -> bool:
    """启用/禁用模组（重命名 .disabled）"""
    try:
        if enable:
            # 移除 .disabled
            if mod_path.endswith(DISABLED_SUFFIX):
                new_path = mod_path[:-len(DISABLED_SUFFIX)]
                os.rename(mod_path, new_path)
                return True
        else:
            # 添加 .disabled
            if not mod_path.endswith(DISABLED_SUFFIX):
                new_path = mod_path + DISABLED_SUFFIX
                if os.path.exists(new_path):
                    new_path = mod_path + ".old"
                os.rename(mod_path, new_path)
                return True
    except Exception as e:
        log_error(f"操作失败: {e}")
    return False


def delete_mod(mod_path: str) -> bool:
    """删除模组文件"""
    try:
        if os.path.exists(mod_path):
            os.remove(mod_path)
            return True
    except Exception as e:
        log_error(f"删除失败: {e}")
    return False


def add_mod(source_path: str, server_base: str) -> bool:
    """添加模组文件到 mods 目录"""
    try:
        mods_path = os.path.join(server_base, MODS_DIR)
        os.makedirs(mods_path, exist_ok=True)
        dest = os.path.join(mods_path, os.path.basename(source_path))
        shutil.copy2(source_path, dest)
        return True
    except Exception as e:
        log_error(f"添加失败: {e}")
    return False


def parse_selection(text: str, total: int) -> list[int]:
    """解析选择语法，返回 0-based 索引列表
    
    支持:
        a          → 全部
        3          → [2]
        1,4,5-8,9  → [0,3,4,5,6,7,8]
    """
    text = text.strip().lower()
    if text == "a":
        return list(range(total))

    indices: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                for i in range(int(start) - 1, int(end)):
                    if 0 <= i < total:
                        indices.add(i)
            except ValueError:
                pass
        else:
            try:
                i = int(part) - 1
                if 0 <= i < total:
                    indices.add(i)
            except ValueError:
                pass

    return sorted(indices)
