"""
================================================================================
【AI 协作系统提示词 / System Prompt for AI Maintainers】
如果你（AI）正在处理此文件，请务必遵守以下开发者习惯与规则：

【确认机制】
※ 如果你（AI）已完整阅读本导言区，并同意严格按照以下所有规则执行，
  请在后续回复中首先向用户确认："已阅读导言区提示词，将严格按照规则执行。"
  之后再进行具体的讨论或操作。

【元规则 - 最高优先级】
0. 【提示词协作】：允许 AI 根据与用户的交流情况，自发在本导言区增加或修改提示词，
   但每次增加或修改提示词前必须先与用户讨论并获得同意。
   AI 必须严格遵照本导言区的所有提示词运作，本导言区规则优先级最高。
   【主动更新】：如果用户提出的需求反映了某些更具一般性的要求，AI 应主动将其整合
   为新的规则添加到本导言区，并在回复中明确告知用户具体修改了哪些内容。

【开发规范】
1. 【逻辑稳定性】：核心功能（JSON 读写、AppID 正则提取）严禁在非必要情况下改动。
2. 【改动确认】：在尝试重构现有功能或大规模调整 UI 前，必须获得用户明确许可。
3. 【更新逻辑】：更新功能（无论是 TXT 还是鉴赏家）必须采用"增量"模式：
   - 主收藏夹：原有 ID + 新增 ID（去重）。
   - 必须创建两个辅助收藏夹："[原名] - 比旧版多的" 和 "[原名] - 比旧版少的"。
   - 【无新增时跳过】：如果更新后没有新增任何游戏，应提示"该列表已是最新"，
     不执行任何操作（不修改主收藏夹、不创建辅助收藏夹）。
4. 【命名规范】：所有通过程序创建或更新的收藏夹名称必须强制添加后缀："(删除这段字以触发云同步)"。
5. 【UI 习惯】：功能按钮的排列顺序保持为：[导入]、[导出]、[更新]。
6. 【反馈机制】：操作完成后必须显示录入/差异数量，并附带数目对不上的免责注记。
7. 【UI 文本风格】：
   - 窗口标题：动宾结构，如"同步 Steam 鉴赏家游戏列表"
   - 使用指南：格式为"使用指南：\n1. xxx\n2. xxx"
   - 状态反馈：✅ 表示成功，❌ 表示失败
   - 按钮文字：emoji + 动宾结构，如"📁 建立为新收藏夹"
   - 说明列表：使用"• "开头
   - 关键信息：使用红色高亮
   - 保持简洁，避免冗余描述
8. 【网络请求】：macOS 需禁用 SSL 证书验证以解决证书问题。
9. 【备份机制】：修改原文件前必须先创建备份，备份存储在 json 同目录的 backups/ 文件夹中。
10.【账号管理】：程序启动时自动扫描所有 Steam 账号，支持多账号切换，始终高亮当前账号。
11.【窗口大小】：所有窗口必须自适应内容大小，禁止使用固定的 geometry() 设置窗口尺寸。
12.【全局配置】：需要跨功能共享的配置项（如 Cookie）应在主界面提供统一的管理入口，
   并在所有相关子功能中全局调用。子功能界面应显示该配置项的当前状态，
   并说明配置后的效果。
13.【主界面布局规范】：主界面采用紧凑布局，减少不必要的空间浪费，具体要求如下：
   a) 【收藏夹列表置左】：收藏夹列表（"📂 当前收藏夹"面板）必须放在程序主界面的
      最左侧，与 Steam 客户端的侧边栏风格保持一致。功能控制区在右侧。
   b) 【备份管理就近放置】："💾 管理收藏夹备份"按钮应放置在"📂 当前收藏夹"标题
      旁边（同一行），而不是作为独立的大按钮占据一整行。这样既节省空间又语义自然。
   c) 【配置按钮并排】："🔑 管理登录态 Cookie" 和 "🎮 管理 IGDB API 凭证" 两个
      按钮必须并排放置在同一行，而不是各自独占一行。
   d) 【整体紧凑】：避免按钮独占整行、说明文字过多导致界面冗长的情况。
      功能说明应尽量精简，能合并的按钮尽量合并在同一行。
14.【增量修改】：生成代码时必须基于现有代码进行增量修改，严禁重新生成整个文件或整个方法。
   应只输出需要变动的部分（如使用 diff/patch 或明确标注修改区域），以节省 token 开销。
================================================================================
"""

import json
import time
import secrets
import os
import re
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import threading
import ssl
import urllib.request
import urllib.error
import base64
import platform
import shutil
from datetime import datetime
from pathlib import Path


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止自动重定向，以便检测 302 等重定向响应"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 返回 None 表示不跟随重定向


class SteamAccountScanner:
    """Steam 账号扫描器：自动发现系统中的 Steam 账号"""
    
    @staticmethod
    def get_steam_paths():
        """获取可能的 Steam 安装路径"""
        system = platform.system()
        paths = []
        
        # 检测是否在 WSL 环境中
        is_wsl = False
        if system == "Linux":
            try:
                with open("/proc/version", "r") as f:
                    if "microsoft" in f.read().lower():
                        is_wsl = True
            except:
                pass
        
        if system == "Windows":
            # Windows 常见路径
            possible_paths = [
                os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
                os.path.expandvars(r"%ProgramFiles%\Steam"),
                r"C:\Steam",
                r"D:\Steam",
                r"E:\Steam",
                r"D:\Program Files (x86)\Steam",
                r"D:\Program Files\Steam",
                r"E:\Program Files (x86)\Steam",
                r"E:\Program Files\Steam",
            ]
            # 从注册表尝试获取（如果可能）
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                if install_path and install_path not in possible_paths:
                    paths.append(install_path)
            except:
                pass
            
            paths.extend(possible_paths)
            
        elif system == "Darwin":  # macOS
            home = os.path.expanduser("~")
            paths = [
                os.path.join(home, "Library/Application Support/Steam"),
                "/Applications/Steam.app/Contents/MacOS/Steam",
            ]
            
        elif system == "Linux":
            home = os.path.expanduser("~")
            paths = [
                os.path.join(home, ".steam/steam"),
                os.path.join(home, ".local/share/Steam"),
                os.path.join(home, ".steam"),
            ]
            
            # WSL 环境：额外搜索 Windows 端的 Steam 路径
            if is_wsl:
                wsl_windows_paths = [
                    "/mnt/c/Program Files (x86)/Steam",
                    "/mnt/c/Program Files/Steam",
                    "/mnt/c/Steam",
                    "/mnt/d/Steam",
                    "/mnt/d/Program Files (x86)/Steam",
                    "/mnt/d/Program Files/Steam",
                    "/mnt/e/Steam",
                    "/mnt/e/Program Files (x86)/Steam",
                    "/mnt/e/Program Files/Steam",
                    "/mnt/f/Steam",
                    "/mnt/f/Program Files (x86)/Steam",
                    "/mnt/f/Program Files/Steam",
                ]
                paths.extend(wsl_windows_paths)
        
        return [p for p in paths if os.path.exists(p)]
    
    @staticmethod
    def scan_accounts():
        """扫描所有 Steam 账号
        
        Returns:
            list of dict: [{'friend_code': '123456', 'userdata_path': '/path/to/userdata/123456', 
                           'json_path': '/path/to/cloud-storage-namespace-1.json', 'persona_name': '...'}]
        """
        accounts = []
        steam_paths = SteamAccountScanner.get_steam_paths()
        
        for steam_path in steam_paths:
            userdata_path = os.path.join(steam_path, "userdata")
            if not os.path.exists(userdata_path):
                continue
            
            # 遍历 userdata 下的所有文件夹（每个文件夹对应一个账号）
            try:
                for entry in os.listdir(userdata_path):
                    entry_path = os.path.join(userdata_path, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    if not entry.isdigit():
                        continue
                    
                    friend_code = entry
                    
                    # 检查 cloud-storage-namespace-1.json 是否存在
                    json_path = os.path.join(entry_path, "config", "cloudstorage", "cloud-storage-namespace-1.json")
                    
                    if os.path.exists(json_path):
                        # 尝试获取用户名（从 localconfig.vdf）
                        persona_name = SteamAccountScanner._get_persona_name(entry_path, friend_code)
                        
                        accounts.append({
                            'friend_code': friend_code,
                            'userdata_path': entry_path,
                            'json_path': json_path,
                            'persona_name': persona_name,
                            'steam_path': steam_path,
                        })
            except PermissionError:
                continue
        
        return accounts
    
    @staticmethod
    def _get_persona_name(userdata_path, friend_code):
        """尝试从配置文件获取用户昵称"""
        # 尝试从 localconfig.vdf 获取
        localconfig_path = os.path.join(userdata_path, "config", "localconfig.vdf")
        if os.path.exists(localconfig_path):
            try:
                with open(localconfig_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                # 简单的正则匹配 PersonaName
                match = re.search(r'"PersonaName"\s+"([^"]+)"', content)
                if match:
                    return match.group(1)
            except:
                pass
        
        return f"Steam 用户 {friend_code}"


class BackupManager:
    """备份管理器：管理 JSON 文件的备份"""
    
    def __init__(self, json_path):
        self.json_path = json_path
        self.json_dir = os.path.dirname(json_path)
        self.backup_dir = os.path.join(self.json_dir, "backups")
        self.json_name = os.path.basename(json_path)
    
    def ensure_backup_dir(self):
        """确保备份目录存在"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def create_backup(self, description=""):
        """创建备份
        
        Args:
            description: 备份描述（可选）
        
        Returns:
            str: 备份文件路径，失败返回 None
        """
        if not os.path.exists(self.json_path):
            return None
        
        self.ensure_backup_dir()
        
        # 生成备份文件名：原文件名_时间戳.json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{os.path.splitext(self.json_name)[0]}_{timestamp}.json"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        try:
            shutil.copy2(self.json_path, backup_path)
            
            # 保存备份元数据
            self._save_backup_metadata(backup_name, description)
            
            return backup_path
        except Exception as e:
            print(f"创建备份失败: {e}")
            return None
    
    def _save_backup_metadata(self, backup_name, description):
        """保存备份元数据"""
        metadata_path = os.path.join(self.backup_dir, "backup_metadata.json")
        metadata = {}
        
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except:
                metadata = {}
        
        if 'backups' not in metadata:
            metadata['backups'] = {}
        
        metadata['backups'][backup_name] = {
            'created_at': datetime.now().isoformat(),
            'description': description,
            'original_file': self.json_name,
        }
        
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def list_backups(self):
        """列出所有备份
        
        Returns:
            list of dict: [{'filename': '...', 'path': '...', 'created_at': '...', 'description': '...', 'size': ...}]
        """
        if not os.path.exists(self.backup_dir):
            return []
        
        backups = []
        metadata = self._load_metadata()
        
        for entry in os.listdir(self.backup_dir):
            if not entry.endswith('.json') or entry == 'backup_metadata.json':
                continue
            
            backup_path = os.path.join(self.backup_dir, entry)
            if not os.path.isfile(backup_path):
                continue
            
            # 从文件名解析时间戳
            try:
                # 格式: cloud-storage-namespace-1_20240101_120000.json
                match = re.search(r'_(\d{8}_\d{6})\.json$', entry)
                if match:
                    ts_str = match.group(1)
                    created_at = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                else:
                    created_at = datetime.fromtimestamp(os.path.getmtime(backup_path))
            except:
                created_at = datetime.fromtimestamp(os.path.getmtime(backup_path))
            
            # 获取元数据中的描述
            meta = metadata.get('backups', {}).get(entry, {})
            description = meta.get('description', '')
            
            backups.append({
                'filename': entry,
                'path': backup_path,
                'created_at': created_at,
                'description': description,
                'size': os.path.getsize(backup_path),
            })
        
        # 按时间倒序排列
        backups.sort(key=lambda x: x['created_at'], reverse=True)
        return backups
    
    def _load_metadata(self):
        """加载备份元数据"""
        metadata_path = os.path.join(self.backup_dir, "backup_metadata.json")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def restore_backup(self, backup_filename):
        """恢复备份
        
        Args:
            backup_filename: 备份文件名
        
        Returns:
            bool: 是否成功
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)
        if not os.path.exists(backup_path):
            return False
        
        try:
            # 先备份当前文件
            self.create_backup(description="恢复前自动备份")
            
            # 恢复
            shutil.copy2(backup_path, self.json_path)
            return True
        except Exception as e:
            print(f"恢复备份失败: {e}")
            return False
    
    def delete_backup(self, backup_filename):
        """删除备份
        
        Args:
            backup_filename: 备份文件名
        
        Returns:
            bool: 是否成功
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)
        if not os.path.exists(backup_path):
            return False
        
        try:
            os.remove(backup_path)
            
            # 更新元数据
            metadata_path = os.path.join(self.backup_dir, "backup_metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    if 'backups' in metadata and backup_filename in metadata['backups']:
                        del metadata['backups'][backup_filename]
                        with open(metadata_path, 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, ensure_ascii=False, indent=2)
                except:
                    pass
            
            return True
        except Exception as e:
            print(f"删除备份失败: {e}")
            return False
    
    def compare_with_current(self, backup_filename):
        """比较备份与当前文件的差异
        
        Args:
            backup_filename: 备份文件名
        
        Returns:
            dict: 差异信息
        """
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        try:
            with open(backup_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            with open(self.json_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
        except Exception as e:
            return {'error': str(e)}
        
        return self._compare_collections(backup_data, current_data)
    
    def compare_backups(self, backup1_filename, backup2_filename):
        """比较两个备份之间的差异
        
        Args:
            backup1_filename: 较旧的备份文件名
            backup2_filename: 较新的备份文件名
        
        Returns:
            dict: 差异信息
        """
        backup1_path = os.path.join(self.backup_dir, backup1_filename)
        backup2_path = os.path.join(self.backup_dir, backup2_filename)
        
        try:
            with open(backup1_path, 'r', encoding='utf-8') as f:
                data1 = json.load(f)
            with open(backup2_path, 'r', encoding='utf-8') as f:
                data2 = json.load(f)
        except Exception as e:
            return {'error': str(e)}
        
        return self._compare_collections(data1, data2)
    
    def _compare_collections(self, old_data, new_data):
        """比较两个数据的收藏夹差异
        
        Returns:
            dict: {
                'added_collections': [...],      # 新增的收藏夹
                'removed_collections': [...],    # 删除的收藏夹
                'modified_collections': [...],   # 修改的收藏夹（含详细变化）
                'unchanged_collections': [...],  # 未变化的收藏夹
                'summary': {...}                 # 摘要信息
            }
        """
        def extract_collections(data):
            """提取收藏夹信息"""
            collections = {}
            for entry in data:
                key = entry[0]
                meta = entry[1]
                if key.startswith("user-collections."):
                    if meta.get("is_deleted") is True or "value" not in meta:
                        continue
                    try:
                        val_obj = json.loads(meta['value'])
                        col_id = val_obj.get("id", key)
                        collections[col_id] = {
                            'name': val_obj.get("name", "未命名"),
                            'added': set(val_obj.get("added", [])),
                            'removed': set(val_obj.get("removed", [])),
                            'is_dynamic': "filterSpec" in val_obj,
                            'raw_value': val_obj,
                        }
                    except:
                        continue
            return collections
        
        old_cols = extract_collections(old_data)
        new_cols = extract_collections(new_data)
        
        old_ids = set(old_cols.keys())
        new_ids = set(new_cols.keys())
        
        added_ids = new_ids - old_ids
        removed_ids = old_ids - new_ids
        common_ids = old_ids & new_ids
        
        result = {
            'added_collections': [],
            'removed_collections': [],
            'modified_collections': [],
            'unchanged_collections': [],
            'summary': {
                'total_added': 0,
                'total_removed': 0,
                'total_modified': 0,
                'total_unchanged': 0,
            }
        }
        
        # 新增的收藏夹
        for col_id in added_ids:
            col = new_cols[col_id]
            result['added_collections'].append({
                'id': col_id,
                'name': col['name'],
                'game_count': len(col['added']),
                'is_dynamic': col['is_dynamic'],
            })
        result['summary']['total_added'] = len(added_ids)
        
        # 删除的收藏夹
        for col_id in removed_ids:
            col = old_cols[col_id]
            result['removed_collections'].append({
                'id': col_id,
                'name': col['name'],
                'game_count': len(col['added']),
                'is_dynamic': col['is_dynamic'],
            })
        result['summary']['total_removed'] = len(removed_ids)
        
        # 检查修改的收藏夹
        for col_id in common_ids:
            old_col = old_cols[col_id]
            new_col = new_cols[col_id]
            
            # 检查是否有变化
            name_changed = old_col['name'] != new_col['name']
            added_games = new_col['added'] - old_col['added']
            removed_games = old_col['added'] - new_col['added']
            
            if name_changed or added_games or removed_games:
                result['modified_collections'].append({
                    'id': col_id,
                    'old_name': old_col['name'],
                    'new_name': new_col['name'],
                    'name_changed': name_changed,
                    'added_games': list(added_games),
                    'removed_games': list(removed_games),
                    'old_game_count': len(old_col['added']),
                    'new_game_count': len(new_col['added']),
                    'is_dynamic': new_col['is_dynamic'],
                })
            else:
                result['unchanged_collections'].append({
                    'id': col_id,
                    'name': new_col['name'],
                    'game_count': len(new_col['added']),
                    'is_dynamic': new_col['is_dynamic'],
                })
        
        result['summary']['total_modified'] = len(result['modified_collections'])
        result['summary']['total_unchanged'] = len(result['unchanged_collections'])
        
        return result


class SteamToolbox:
    def __init__(self):
        self.current_account = None  # 当前选中的账号
        self.accounts = []           # 所有扫描到的账号
        self.backup_manager = None   # 备份管理器
        
        # 这些属性会在选择账号后设置
        self.json_path = None
        self.json_name = "cloud-storage-namespace-1.json"
        self.current_dir = None
        
        # 配置文件路径（全局）
        self.global_config_path = os.path.join(os.path.expanduser("~"), ".steam_toolbox_config.json")
        
        self.induce_suffix = "(删除这段字以触发云同步)"
        self.disclaimer = f"\n\n(若其中包含未拥有的游戏、重复条目或是 DLC，会导致 Steam 收藏夹内显示的数目偏少。)"
        
        # SSL 上下文（解决 macOS 证书问题）
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    def set_current_account(self, account):
        """设置当前账号"""
        self.current_account = account
        self.json_path = account['json_path']
        self.current_dir = os.path.dirname(self.json_path)
        self.backup_manager = BackupManager(self.json_path)
    
    def _load_config(self):
        """加载全局配置文件"""
        if os.path.exists(self.global_config_path):
            try:
                with open(self.global_config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_config(self, config):
        """保存全局配置文件"""
        try:
            with open(self.global_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def _get_saved_cookie(self):
        """获取已保存的 Cookie（简单混淆存储）"""
        config = self._load_config()
        encoded = config.get("steam_cookie_encoded", "")
        if encoded:
            try:
                return base64.b64decode(encoded.encode()).decode()
            except:
                pass
        return ""

    def _save_cookie(self, cookie_value):
        """保存 Cookie（简单混淆存储）"""
        config = self._load_config()
        if cookie_value:
            config["steam_cookie_encoded"] = base64.b64encode(cookie_value.encode()).decode()
        else:
            config.pop("steam_cookie_encoded", None)
        self._save_config(config)

    def _clear_saved_cookie(self):
        """清除已保存的 Cookie"""
        config = self._load_config()
        config.pop("steam_cookie_encoded", None)
        self._save_config(config)

    # ==================== IGDB API 相关函数 ====================
    def _get_igdb_credentials(self):
        """获取已保存的 IGDB API 凭证"""
        config = self._load_config()
        client_id = config.get("igdb_client_id", "")
        encoded_secret = config.get("igdb_client_secret_encoded", "")
        client_secret = ""
        if encoded_secret:
            try:
                client_secret = base64.b64decode(encoded_secret.encode()).decode()
            except:
                pass
        return client_id, client_secret

    def _save_igdb_credentials(self, client_id, client_secret):
        """保存 IGDB API 凭证（Client Secret 简单混淆存储）"""
        config = self._load_config()
        config["igdb_client_id"] = client_id
        if client_secret:
            config["igdb_client_secret_encoded"] = base64.b64encode(client_secret.encode()).decode()
        else:
            config.pop("igdb_client_secret_encoded", None)
        self._save_config(config)

    def _clear_igdb_credentials(self):
        """清除 IGDB API 凭证"""
        config = self._load_config()
        config.pop("igdb_client_id", None)
        config.pop("igdb_client_secret_encoded", None)
        config.pop("igdb_access_token", None)
        config.pop("igdb_token_expires_at", None)
        self._save_config(config)

    def _get_igdb_access_token(self, force_refresh=False):
        """获取 IGDB API 的访问令牌（带缓存）"""
        client_id, client_secret = self._get_igdb_credentials()
        if not client_id or not client_secret:
            return None, "未配置 IGDB API 凭证"
        
        config = self._load_config()
        cached_token = config.get("igdb_access_token", "")
        expires_at = config.get("igdb_token_expires_at", 0)
        
        # 检查缓存的令牌是否仍然有效（提前 300 秒过期）
        current_time = int(time.time())
        if not force_refresh and cached_token and expires_at > current_time + 300:
            return cached_token, None
        
        # 请求新的访问令牌
        token_url = f"https://id.twitch.tv/oauth2/token?client_id={client_id}&client_secret={client_secret}&grant_type=client_credentials"
        
        try:
            req = urllib.request.Request(token_url, method='POST')
            with urllib.request.urlopen(req, timeout=15, context=self.ssl_context) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            
            access_token = data.get("access_token", "")
            expires_in = data.get("expires_in", 0)
            
            if not access_token:
                return None, "获取访问令牌失败：响应中无 access_token"
            
            # 缓存令牌
            config["igdb_access_token"] = access_token
            config["igdb_token_expires_at"] = current_time + expires_in
            self._save_config(config)
            
            return access_token, None
            
        except urllib.error.HTTPError as e:
            return None, f"HTTP 错误 {e.code}：获取 IGDB 令牌失败"
        except urllib.error.URLError as e:
            return None, f"网络错误：{str(e.reason)}"
        except Exception as e:
            return None, f"获取令牌失败：{str(e)}"

    def _fetch_igdb_genres(self, progress_callback=None):
        """获取 IGDB 游戏类型列表"""
        client_id, _ = self._get_igdb_credentials()
        access_token, error = self._get_igdb_access_token()
        
        if error:
            return [], error
        
        if progress_callback:
            progress_callback(0, 0, "正在获取游戏类型列表...", "")
        
        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        
        # 获取所有游戏类型
        url = "https://api.igdb.com/v4/genres"
        body = "fields id,name,slug; limit 100;"
        
        try:
            req = urllib.request.Request(url, data=body.encode('utf-8'), headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=20, context=self.ssl_context) as resp:
                genres = json.loads(resp.read().decode('utf-8'))
            
            # 按名称排序
            genres.sort(key=lambda x: x.get('name', ''))
            return genres, None
            
        except urllib.error.HTTPError as e:
            return [], f"HTTP 错误 {e.code}：获取类型列表失败"
        except urllib.error.URLError as e:
            return [], f"网络错误：{str(e.reason)}"
        except Exception as e:
            return [], f"获取失败：{str(e)}"

    # ==================== IGDB 本地缓存 ====================
    
    IGDB_CACHE_EXPIRY_DAYS = 7  # 缓存有效期（天）
    
    def _get_igdb_cache_path(self):
        """获取 IGDB 缓存文件路径（与全局配置文件同目录）"""
        return os.path.join(os.path.expanduser("~"), ".steam_toolbox_igdb_cache.json")
    
    def _load_igdb_cache(self):
        """加载 IGDB 缓存"""
        path = self._get_igdb_cache_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def _save_igdb_cache(self, cache):
        """保存 IGDB 缓存"""
        path = self._get_igdb_cache_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        except:
            pass
    
    def _get_igdb_genre_cache(self, genre_id):
        """获取某个类型的缓存数据，返回 (steam_ids, cached_at_timestamp) 或 (None, None)"""
        cache = self._load_igdb_cache()
        genre_key = str(genre_id)
        if genre_key in cache:
            entry = cache[genre_key]
            return entry.get("steam_ids", []), entry.get("cached_at", 0)
        return None, None
    
    def _set_igdb_genre_cache(self, genre_id, steam_ids):
        """写入某个类型的缓存数据"""
        cache = self._load_igdb_cache()
        cache[str(genre_id)] = {
            "steam_ids": steam_ids,
            "cached_at": time.time(),
        }
        self._save_igdb_cache(cache)
    
    def _is_igdb_cache_valid(self, cached_at):
        """判断缓存是否仍然有效"""
        if not cached_at:
            return False
        age_seconds = time.time() - cached_at
        return age_seconds < self.IGDB_CACHE_EXPIRY_DAYS * 86400
    
    def _get_igdb_cache_summary(self):
        """获取缓存摘要信息，用于 UI 显示
        
        Returns:
            dict: {'total_genres': int, 'total_games': int, 'oldest_at': float, 'newest_at': float}
                  如果无缓存则返回 None
        """
        cache = self._load_igdb_cache()
        if not cache:
            return None
        total_genres = len(cache)
        total_games = sum(len(entry.get("steam_ids", [])) for entry in cache.values())
        timestamps = [entry.get("cached_at", 0) for entry in cache.values() if entry.get("cached_at")]
        if not timestamps:
            return None
        return {
            'total_genres': total_genres,
            'total_games': total_games,
            'oldest_at': min(timestamps),
            'newest_at': max(timestamps),
        }
    
    def _clear_igdb_genre_cache(self):
        """清除所有 IGDB 缓存"""
        path = self._get_igdb_cache_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass
    
    # ==================== IGDB API 请求 ====================
    
    def _igdb_api_request(self, url, body, headers):
        """发送 IGDB API 请求，自动处理速率限制和重试"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, data=body.encode('utf-8'), headers=headers, method='POST')
                with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                    return json.loads(resp.read().decode('utf-8')), None
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(1.5)
                    continue
                return None, f"HTTP 错误 {e.code}"
            except urllib.error.URLError as e:
                return None, f"网络错误：{str(e.reason)}"
            except Exception as e:
                return None, f"请求失败：{str(e)}"
        return None, "达到最大重试次数（速率限制）"

    def _fetch_igdb_games_by_genre(self, genre_id, genre_name, progress_callback=None, force_refresh=False):
        """根据类型 ID 获取该类型下所有游戏的 Steam AppID
        
        优先使用本地缓存，缓存过期或 force_refresh=True 时才从 API 获取。
        采用两步法：
        1. 查询 /v4/games 端点，按 genre 过滤，获取所有符合条件的 game ID
           使用 cursor-based pagination（where id > last_id）绕开 offset 10000 上限
        2. 批量查询 /v4/external_games 端点，获取这些游戏的 Steam AppID
        获取完成后自动写入本地缓存。
        """
        # === 检查本地缓存 ===
        if not force_refresh:
            cached_ids, cached_at = self._get_igdb_genre_cache(genre_id)
            if cached_ids is not None and self._is_igdb_cache_valid(cached_at):
                if progress_callback:
                    age_hours = (time.time() - cached_at) / 3600
                    progress_callback(len(cached_ids), len(cached_ids),
                        f"使用本地缓存", f"{genre_name}: {len(cached_ids)} 个游戏（缓存于 {age_hours:.0f} 小时前）")
                return cached_ids, None
        
        # === 从 API 获取 ===
        client_id, _ = self._get_igdb_credentials()
        access_token, error = self._get_igdb_access_token()
        
        if error:
            return [], error
        
        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }
        
        # ===== 第一步：从 /v4/games 获取所有符合类型的游戏 ID =====
        all_game_ids = []
        last_id = 0
        limit = 500
        
        while True:
            if progress_callback:
                progress_callback(len(all_game_ids), 0,
                    f"第1步：检索 {genre_name} 类型游戏...",
                    f"已发现 {len(all_game_ids)} 个游戏")
            
            body = (f"fields id; "
                    f"where genres = [{genre_id}] & version_parent = null & id > {last_id}; "
                    f"sort id asc; limit {limit};")
            
            results, err = self._igdb_api_request("https://api.igdb.com/v4/games", body, headers)
            
            if err:
                return [], f"获取游戏列表失败：{err}"
            
            if not results:
                break
            
            for item in results:
                gid = item.get('id')
                if gid:
                    all_game_ids.append(gid)
                    last_id = gid
            
            if len(results) < limit:
                break
            
            time.sleep(0.28)
        
        if not all_game_ids:
            # 即使结果为空也缓存，避免反复请求
            self._set_igdb_genre_cache(genre_id, [])
            return [], None
        
        # ===== 第二步：批量查询 external_games 获取 Steam AppID =====
        all_steam_ids = []
        steam_id_set = set()
        batch_size = 200
        total_batches = (len(all_game_ids) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            if progress_callback:
                progress_callback(len(steam_id_set), len(all_game_ids),
                    f"第2步：查询 Steam ID...",
                    f"进度 {batch_idx+1}/{total_batches}，已匹配 {len(steam_id_set)} 个")
            
            batch = all_game_ids[batch_idx * batch_size : (batch_idx + 1) * batch_size]
            game_ids_str = ",".join(str(gid) for gid in batch)
            
            body = (f"fields uid,game; "
                    f"where category = 1 & game = ({game_ids_str}); "
                    f"limit 500;")
            
            results, err = self._igdb_api_request("https://api.igdb.com/v4/external_games", body, headers)
            
            if err:
                continue
            
            if results:
                for item in results:
                    uid = item.get('uid', '')
                    if uid and uid.isdigit():
                        steam_id = int(uid)
                        if steam_id not in steam_id_set:
                            steam_id_set.add(steam_id)
                            all_steam_ids.append(steam_id)
            
            time.sleep(0.28)
        
        # === 写入本地缓存 ===
        self._set_igdb_genre_cache(genre_id, all_steam_ids)
        
        return all_steam_ids, None

    def load_json(self):
        if not self.json_path or not os.path.exists(self.json_path):
            messagebox.showerror("错误", f"找不到 {self.json_name}\n请确保已选择有效的 Steam 账号。")
            return None
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("读取错误", f"解析失败: {e}")
            return None

    def save_json(self, data, create_backup=True, backup_description=""):
        """保存 JSON 数据到原文件
        
        Args:
            data: 要保存的数据
            create_backup: 是否在保存前创建备份
            backup_description: 备份描述
        """
        if not self.json_path:
            messagebox.showerror("错误", "未选择账号，无法保存。")
            return False
        
        # 创建备份
        if create_backup and self.backup_manager:
            backup_path = self.backup_manager.create_backup(description=backup_description)
            if backup_path:
                backup_info = f"\n\n已自动备份至:\n{os.path.basename(backup_path)}"
            else:
                backup_info = "\n\n⚠️ 备份创建失败"
        else:
            backup_info = ""
        
        # 写入原文件（使用原子写入）
        tmp_path = self.json_path + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            
            # 原子替换
            if os.path.exists(self.json_path):
                os.replace(tmp_path, self.json_path)
            else:
                os.rename(tmp_path, self.json_path)
            
            messagebox.showinfo("成功", f"文件已保存：\n{os.path.basename(self.json_path)}{backup_info}")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"无法写入文件: {e}")
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
            return False

    def _sanitize_filename(self, name):
        """清洗文件名，替换系统禁止的特殊字符"""
        return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

    def _get_static_collections(self, data):
        """获取所有收藏夹（含动态）及其 entry 引用，按字母排序"""
        return self._get_all_collections_with_refs(data)
    
    def _get_all_collections_with_refs(self, data):
        """获取所有收藏夹（含动态收藏夹）及其 entry 引用，按字母排序"""
        collections = []
        for entry in data:
            key = entry[0]
            meta = entry[1]
            if key.startswith("user-collections."):
                if meta.get("is_deleted") is True or "value" not in meta:
                    continue
                try:
                    val_obj = json.loads(meta['value'])
                    is_dynamic = "filterSpec" in val_obj
                    icon = "🔍" if is_dynamic else "📁"
                    collections.append({
                        "entry_ref": entry,
                        "id": val_obj.get("id"),
                        "name": val_obj.get("name"),
                        "added": val_obj.get("added", []),
                        "is_dynamic": is_dynamic,
                        "display_name": f"{icon} {val_obj.get('name', '未命名')}"
                    })
                except Exception:
                    continue
        collections.sort(key=lambda c: (c.get('name') or '').lower())
        return collections

    def _get_all_collections_ordered(self, data):
        """获取所有收藏夹（按字母顺序排序，与 Steam 客户端一致）"""
        collections = []
        for entry in data:
            key = entry[0]
            meta = entry[1]
            if key.startswith("user-collections."):
                if meta.get("is_deleted") is True or "value" not in meta:
                    continue
                try:
                    val_obj = json.loads(meta['value'])
                    is_dynamic = "filterSpec" in val_obj
                    col_info = {
                        "id": val_obj.get("id"),
                        "name": val_obj.get("name", "未命名"),
                        "added": val_obj.get("added", []),
                        "removed": val_obj.get("removed", []),
                        "is_dynamic": is_dynamic
                    }
                    if is_dynamic:
                        col_info["filterSpec"] = val_obj.get("filterSpec")
                    collections.append(col_info)
                except Exception:
                    continue
        collections.sort(key=lambda c: c['name'].lower())
        return collections

    def _extract_ids_from_html(self, html_text):
        """核心提取逻辑：从 HTML 中提取 AppID"""
        search_area = html_text
        list_start = html_text.find('id="RecommendationsRows"')
        if list_start == -1:
            list_start = html_text.find('class="creator_grid_ctn"')
        
        if list_start != -1:
            footer_start = html_text.find('id="footer"', list_start)
            search_area = html_text[list_start : (footer_start if footer_start != -1 else len(html_text))]

        raw_matches = re.findall(r'data-ds-appid="([\d,]+)"', search_area)
        all_ids = []
        for m in raw_matches:
            if ',' in m:
                all_ids.extend(m.split(','))
            else:
                all_ids.append(m)
        
        return list(dict.fromkeys([int(aid) for aid in all_ids if aid.isdigit()]))

    def _extract_page_name_from_html(self, html_text, url_hint=""):
        """从 HTML 中智能提取页面名称（带类型前缀）"""
        type_name_cn = "列表"
        if url_hint:
            page_type, _ = self._extract_steam_list_info(url_hint)
            type_names = {
                "curator": "鉴赏家",
                "publisher": "发行商",
                "developer": "开发商",
                "franchise": "系列",
                "genre": "类型",
                "category": "分类",
            }
            type_name_cn = type_names.get(page_type, "列表")
        
        if "curator" in html_text.lower() or "鉴赏家" in html_text:
            type_name_cn = "鉴赏家"
        elif "publisher" in html_text.lower():
            type_name_cn = "发行商"
        elif "developer" in html_text.lower():
            type_name_cn = "开发商"
        
        name = None
        match = re.search(r'class="curator_name".*?><a.*?>(.*?)</a>', html_text, re.S)
        if match:
            name = match.group(1).strip()
        
        if not name:
            match = re.search(r'<title>(.*?)</title>', html_text, re.I)
            if match:
                title = match.group(1)
                title = re.sub(r'\s*[-–—]\s*Steam.*$', '', title, flags=re.I)
                title = re.sub(r'\s*on Steam.*$', '', title, flags=re.I)
                title = re.sub(r'^Steam 鉴赏家：', '', title)
                title = re.sub(r'^Steam Curator:\s*', '', title, flags=re.I)
                name = title.strip()
        
        if name:
            return f"{type_name_cn}：{name}"
        return f"{type_name_cn}：未知"
    
    def _extract_curator_name(self, html_text):
        """从 HTML 中智能提取鉴赏家名称（保持向后兼容）"""
        return self._extract_page_name_from_html(html_text)

    def _extract_steam_list_info(self, url_or_id):
        """从 URL 或直接输入中提取 Steam 列表页面信息"""
        text = url_or_id.strip()
        
        if text.isdigit():
            return ("curator", text)
        
        patterns = [
            (r'/curator/(\d+)', "curator"),
            (r'/publisher/([^/?#]+)', "publisher"),
            (r'/developer/([^/?#]+)', "developer"),
            (r'/franchise/([^/?#]+)', "franchise"),
            (r'/genre/([^/?#]+)', "genre"),
            (r'/category/([^/?#]+)', "category"),
        ]
        
        for pattern, page_type in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (page_type, match.group(1))
        
        return (None, None)

    def _fetch_steam_list(self, page_type, identifier, progress_callback=None, login_cookies=None):
        """通过 Steam API 自动获取列表页面的所有游戏"""
        type_names = {
            "curator": "鉴赏家",
            "publisher": "发行商",
            "developer": "开发商",
            "franchise": "系列",
            "genre": "类型",
            "category": "分类",
        }
        type_name_cn = type_names.get(page_type, "列表")
        
        base_cookies = "birthtime=283993201; wants_mature_content=1; mature_content=1; lastagecheckage=1-0-1979; steamCountry=US%7C0"
        has_login = login_cookies is not None and len(login_cookies.strip()) > 0
        
        if has_login:
            cookies = f"{login_cookies}; {base_cookies}"
        else:
            cookies = base_cookies
        
        if page_type in ("curator", "publisher", "developer"):
            return self._fetch_curator_style_api(page_type, identifier, type_name_cn, cookies, has_login, progress_callback)
        else:
            return self._fetch_generic_list(page_type, identifier, type_name_cn, cookies, has_login, progress_callback)
    
    def _fetch_curator_style_api(self, page_type, identifier, type_name_cn, cookies, has_login, progress_callback=None):
        """统一的 ajaxgetfilteredrecommendations API 抓取"""
        from urllib.parse import unquote
        
        page_url = f"https://store.steampowered.com/{page_type}/{identifier}/"
        curator_id = None
        page_name = None
        
        headers_html = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cookie': cookies,
        }
        
        if page_type == "curator":
            curator_id = identifier
            if progress_callback:
                progress_callback(0, 0, "正在验证鉴赏家页面...", "正在连接 Steam 商店...")
            try:
                req = urllib.request.Request(page_url, headers=headers_html)
                with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                    html_content = resp.read().decode('utf-8')
                
                name_patterns = [
                    r'class="curator_name"[^>]*>.*?<a[^>]*>(.*?)</a>',
                    r'<title>Steam 鉴赏家：([^<]+?)</title>',
                    r'<title>([^<]+?)(?:\s*[-–—]\s*Steam)?</title>',
                ]
                for pattern in name_patterns:
                    match = re.search(pattern, html_content, re.S | re.I)
                    if match:
                        extracted = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                        extracted = extracted.replace('&amp;', '&').replace('&quot;', '"')
                        if extracted and len(extracted) < 100:
                            page_name = extracted
                            break
                            
            except urllib.error.HTTPError:
                pass
            except Exception:
                pass
        else:
            if progress_callback:
                progress_callback(0, 0, "正在获取页面信息...", f"正在访问 {page_type}/{identifier} ...")
            
            try:
                req = urllib.request.Request(page_url, headers=headers_html)
                with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                    html_content = resp.read().decode('utf-8')
                
                clanid_match = re.search(r'curator_clanid[=:][\s"\']*(\d+)', html_content)
                if clanid_match:
                    curator_id = clanid_match.group(1)
                
                name_patterns = [
                    r'class="curator_name"[^>]*>.*?<a[^>]*>(.*?)</a>',
                    r'<title>(?:Steam (?:Publisher|Developer):\s*)?([^<]+?)(?:\s*[-–—]\s*Steam)?</title>',
                ]
                for pattern in name_patterns:
                    match = re.search(pattern, html_content, re.S | re.I)
                    if match:
                        extracted = re.sub(r'<[^>]+>', '', match.group(1)).strip()
                        extracted = extracted.replace('&amp;', '&').replace('&quot;', '"')
                        if extracted and len(extracted) < 100:
                            page_name = extracted
                            break
                            
            except urllib.error.HTTPError as e:
                return [], None, f"HTTP 错误 {e.code}：无法访问该{type_name_cn}页面。", has_login
            except Exception as e:
                return [], None, f"获取页面失败：{str(e)}", has_login
        
        if not curator_id:
            return [], None, f"无法从该{type_name_cn}页面提取 curator ID。", has_login
        
        base_url = f"https://store.steampowered.com/curator/{curator_id}/ajaxgetfilteredrecommendations/"
        
        lang_configs = [
            ("schinese", "zh-CN,zh;q=0.9,en;q=0.8", "简体中文"),
            ("english", "en-US,en;q=0.9", "English"),
            ("japanese", "ja,en;q=0.8", "日本語"),
            ("tchinese", "zh-TW,zh;q=0.9,en;q=0.8", "繁體中文"),
            ("koreana", "ko,en;q=0.8", "한국어"),
        ]
        
        all_unique_ids = set()
        max_total = 0
        
        for lang_idx, (lang_code, accept_lang, lang_display) in enumerate(lang_configs):
            headers_api = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': accept_lang,
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': page_url,
                'Cookie': cookies,
            }
            
            start = 0
            count = 100
            total_count = None
            lang_page = 0
            
            if progress_callback:
                progress_callback(
                    len(all_unique_ids), max_total,
                    f"已获取 {len(all_unique_ids)} 个",
                    f"🌐 扫描语言 [{lang_idx+1}/{len(lang_configs)}]：{lang_display} — 正在连接..."
                )
            
            while True:
                url = f"{base_url}?start={start}&count={count}&l={lang_code}"
                lang_page += 1
                
                try:
                    req = urllib.request.Request(url, headers=headers_api)
                    with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                        data = json.loads(resp.read().decode('utf-8'))
                    
                    if not data.get('success'):
                        break
                    
                    if total_count is None:
                        total_count = int(data.get('total_count', 0))
                        if total_count == 0:
                            break
                        if total_count > max_total:
                            max_total = total_count
                    
                    html_chunk = data.get('results_html', '')
                    new_in_page = 0
                    if html_chunk:
                        chunk_ids = re.findall(r'data-ds-appid="(\d+)"', html_chunk)
                        for aid in chunk_ids:
                            aid_int = int(aid)
                            if aid_int not in all_unique_ids:
                                new_in_page += 1
                            all_unique_ids.add(aid_int)
                        
                        if page_name is None:
                            name_match = re.search(r'class="curator_name"[^>]*>.*?<a[^>]*>(.*?)</a>', html_chunk, re.S)
                            if name_match:
                                page_name = re.sub(r'<[^>]+>', '', name_match.group(1)).strip()
                    
                    if progress_callback:
                        total_pages = (total_count + count - 1) // count if total_count else "?"
                        progress_callback(
                            len(all_unique_ids), max_total,
                            f"已获取 {len(all_unique_ids)} 个",
                            f"🌐 [{lang_idx+1}/{len(lang_configs)}] {lang_display} — 第 {lang_page}/{total_pages} 页（本页新增 {new_in_page}，共 {len(chunk_ids) if html_chunk else 0} 条）"
                        )
                    
                    start += count
                    if start >= total_count or not html_chunk:
                        break
                    
                    time.sleep(0.1)
                        
                except Exception:
                    break
            
            if progress_callback:
                progress_callback(
                    len(all_unique_ids), max_total if max_total else len(all_unique_ids),
                    f"已获取 {len(all_unique_ids)} 个",
                    f"✅ {lang_display} 扫描完成 — 当前共 {len(all_unique_ids)} 个唯一游戏"
                )
            
            time.sleep(0.2)
        
        if not all_unique_ids:
            return [], None, f"该{type_name_cn}没有任何游戏，或标识符无效。\n请检查 URL 是否正确。", has_login
        
        unique_ids = list(all_unique_ids)
        
        if page_name:
            display_name = f"{type_name_cn}：{page_name}"
        else:
            display_name = f"{type_name_cn}：{unquote(identifier)}"
        
        return unique_ids, display_name, None, has_login
    
    def _fetch_generic_list(self, page_type, identifier, type_name_cn, cookies, has_login, progress_callback=None):
        """通过通用方式抓取发行商/开发商/系列等页面的游戏列表"""
        from urllib.parse import unquote
        
        base_url = f"https://store.steampowered.com/{page_type}/{identifier}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cookie': cookies,
        }
        
        all_unique_ids = set()
        page_name = None
        
        if progress_callback:
            progress_callback(0, 0, "正在获取页面...", f"正在连接 {page_type}/{identifier} ...")
        
        try:
            req = urllib.request.Request(base_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                html_content = resp.read().decode('utf-8')
            
            name_patterns = [
                r'<div class="curator_name"[^>]*>.*?<a[^>]*>(.*?)</a>',
                r'<div class="page_title_area[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>',
                r'<h2 class="pageheader">(.*?)</h2>',
                r'<title>([^<]+?)(?:\s*[-–—]\s*Steam|\s*on Steam)?</title>',
            ]
            
            for pattern in name_patterns:
                match = re.search(pattern, html_content, re.S | re.I)
                if match:
                    extracted_name = match.group(1).strip()
                    extracted_name = re.sub(r'<[^>]+>', '', extracted_name)
                    extracted_name = extracted_name.replace('&amp;', '&').replace('&quot;', '"')
                    if extracted_name and len(extracted_name) < 100:
                        page_name = extracted_name
                        break
            
            if not page_name:
                page_name = unquote(identifier).replace('%20', ' ').replace('+', ' ')
            
            ids = self._extract_ids_from_html(html_content)
            for aid in ids:
                all_unique_ids.add(aid)
            
            if progress_callback:
                progress_callback(len(all_unique_ids), len(all_unique_ids), "已获取主页面",
                                  f"📄 主页面提取了 {len(ids)} 个游戏，正在检查分页...")
            
            page = 2
            while True:
                ajax_url = f"{base_url}?page={page}"
                try:
                    if progress_callback:
                        progress_callback(len(all_unique_ids), len(all_unique_ids), f"正在获取第 {page} 页",
                                          f"📄 正在加载第 {page} 页...")
                    
                    req = urllib.request.Request(ajax_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=15, context=self.ssl_context) as resp:
                        page_html = resp.read().decode('utf-8')
                    
                    page_ids = self._extract_ids_from_html(page_html)
                    if not page_ids or all(aid in all_unique_ids for aid in page_ids):
                        break
                    
                    new_count = sum(1 for aid in page_ids if aid not in all_unique_ids)
                    for aid in page_ids:
                        all_unique_ids.add(aid)
                    
                    if progress_callback:
                        progress_callback(len(all_unique_ids), len(all_unique_ids), f"已获取第 {page} 页",
                                          f"📄 第 {page} 页新增 {new_count} 个游戏，当前共 {len(all_unique_ids)} 个")
                    
                    page += 1
                    time.sleep(0.3)
                    
                    if page > 50:
                        break
                        
                except Exception:
                    break
                    
        except urllib.error.HTTPError as e:
            return [], None, f"HTTP 错误 {e.code}：无法访问该页面。", has_login
        except Exception as e:
            return [], None, f"获取失败：{str(e)}", has_login
        
        if not all_unique_ids:
            return [], None, f"该{type_name_cn}页面没有找到任何游戏。", has_login
        
        unique_ids = list(all_unique_ids)
        display_name = f"{type_name_cn}：{page_name}"
        
        return unique_ids, display_name, None, has_login

    def _extract_ids_from_steamdb_html(self, html_text):
        """从 SteamDB 页面源代码中提取 AppID"""
        tbody_match = re.search(r'<tbody.*?>(.*?)</tbody>', html_text, re.DOTALL)
        if not tbody_match:
            return []
        return [int(aid) for aid in re.findall(r'data-appid="(\d+)"', tbody_match.group(1))]

    def _perform_incremental_update(self, data, target_entry, new_ids_from_src, raw_name):
        """核心增量更新逻辑：主收藏夹追加 + 生成两个差异备份文件夹
        
        Returns:
            (added_count, removed_count, total_count, is_updated)
            如果没有新增任何游戏，is_updated 为 False，此时不会做任何修改
        """
        val_obj = json.loads(target_entry[1]['value'])
        old_ids = val_obj.get("added", [])
        
        old_set = set(old_ids)
        src_set = set(new_ids_from_src)
        
        added_list = [aid for aid in new_ids_from_src if aid not in old_set]
        removed_list = [aid for aid in old_ids if aid not in src_set]
        
        # 如果没有新增任何游戏，不做任何操作
        if not added_list:
            return 0, len(removed_list), len(old_ids), False
        
        # 有新增，执行更新
        val_obj['added'] = old_ids + added_list
        clean_name = raw_name.replace(self.induce_suffix, "").strip()
        val_obj['name'] = f"{clean_name}{self.induce_suffix}"
        target_entry[1]['value'] = json.dumps(val_obj, ensure_ascii=False, separators=(',', ':'))
        target_entry[1]['timestamp'] = int(time.time())
        target_entry[1]['version'] = self._next_version(data)
        target_entry[1].setdefault('conflictResolutionMethod', 'custom')
        target_entry[1].setdefault('strMethodId', 'union-collections')
        
        # 创建辅助收藏夹
        self._add_static_collection(data, f"{clean_name} - 比旧版多的", added_list)
        if removed_list:
            self._add_static_collection(data, f"{clean_name} - 比旧版少的", removed_list)
            
        return len(added_list), len(removed_list), len(val_obj['added']), True

    def _perform_replace_update(self, data, target_entry, new_ids):
        """替换式更新：直接用新 ID 列表替换目标收藏夹的内容
        
        Returns:
            (old_count, new_count)
        """
        val_obj = json.loads(target_entry[1]['value'])
        old_count = len(val_obj.get("added", []))
        
        val_obj['added'] = new_ids
        clean_name = val_obj.get('name', '').replace(self.induce_suffix, "").strip()
        val_obj['name'] = f"{clean_name}{self.induce_suffix}"
        target_entry[1]['value'] = json.dumps(val_obj, ensure_ascii=False, separators=(',', ':'))
        target_entry[1]['timestamp'] = int(time.time())
        target_entry[1]['version'] = self._next_version(data)
        target_entry[1].setdefault('conflictResolutionMethod', 'custom')
        target_entry[1].setdefault('strMethodId', 'union-collections')
        
        return old_count, len(new_ids)

    # --- 收藏夹导出/导入（两种格式） ---
    
    def _export_collections_appid_list(self, collections):
        """格式一：导出选中收藏夹的去重 AppID 列表（一行一个）
        动态收藏夹只导出其 added 列表。"""
        seen = set()
        unique_ids = []
        for col in collections:
            for aid in col.get('added', []):
                if aid not in seen:
                    seen.add(aid)
                    unique_ids.append(aid)
        return unique_ids
    
    def _export_collections_structured(self, collections):
        """格式二：导出选中收藏夹的完整结构化 JSON
        包含名称、类型、appid、动态逻辑等。"""
        export_data = {
            "format": "steam_collections_structured",
            "version": 1,
            "exported_at": datetime.now().isoformat(),
            "collections": []
        }
        for col in collections:
            entry = {
                "name": col.get("name", "未命名"),
                "is_dynamic": col.get("is_dynamic", False),
                "added": col.get("added", []),
                "removed": col.get("removed", []),
            }
            if col.get("is_dynamic") and col.get("filterSpec"):
                entry["filterSpec"] = col["filterSpec"]
            export_data["collections"].append(entry)
        return export_data
    
    def _import_collections_appid_list(self, file_path, data):
        """格式一：导入一行一个 AppID 的列表文件，创建一个新收藏夹"""
        file_title = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, 'r', encoding='utf-8') as f:
            app_ids = [int(line.strip()) for line in f if line.strip().isdigit()]
        if not app_ids:
            return None, "文件中没有有效的 AppID。"
        self._add_static_collection(data, file_title, app_ids)
        return len(app_ids), None
    
    def _import_collections_structured(self, file_path, data):
        """格式二：导入结构化 JSON 文件，还原多个收藏夹（含动态逻辑）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            import_data = json.load(f)
        
        if import_data.get("format") != "steam_collections_structured":
            return None, "文件格式不匹配：缺少 format 标识。"
        
        imported_cols = import_data.get("collections", [])
        if not imported_cols:
            return None, "文件中没有收藏夹数据。"
        
        count = 0
        for col in imported_cols:
            name = col.get("name", "导入的收藏夹")
            is_dynamic = col.get("is_dynamic", False)
            added = col.get("added", [])
            removed = col.get("removed", [])
            
            if is_dynamic and "filterSpec" in col:
                # 还原动态收藏夹
                col_id = f"uc-{secrets.token_hex(4)}"
                storage_key = f"user-collections.{col_id}"
                val_obj = {
                    "id": col_id,
                    "name": name + self.induce_suffix,
                    "added": added,
                    "removed": removed,
                    "filterSpec": col["filterSpec"]
                }
                new_entry = [storage_key, {
                    "key": storage_key,
                    "timestamp": int(time.time()),
                    "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')),
                    "version": self._next_version(data),
                    "conflictResolutionMethod": "custom",
                    "strMethodId": "union-collections"
                }]
                data.append(new_entry)
            else:
                # 静态收藏夹
                self._add_static_collection(data, name.replace(self.induce_suffix, "").strip(), added)
            count += 1
        
        return count, None

    # --- 1. 批量导入 ---
    def import_from_txt(self):
        """批量导入：选择 TXT（多个 AppID 列表）或 JSON（结构化收藏夹）"""
        fmt_win = tk.Toplevel()
        fmt_win.title("批量导入收藏夹")
        fmt_win.attributes("-topmost", True)
        fmt_win.resizable(False, False)
        
        tk.Label(fmt_win, text="请选择要导入的文件格式：",
                 font=("微软雅黑", 10), pady=10).pack(padx=20)
        
        def import_txt():
            fmt_win.destroy()
            paths = filedialog.askopenfilenames(
                initialdir=self.current_dir, title="选择 AppID 列表文件（TXT）",
                filetypes=[("Text files", "*.txt")])
            if not paths:
                return
            data = self.load_json()
            if data is None:
                return
            existing = self._get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            results = []
            for p in paths:
                count, err = self._import_collections_appid_list(p, data)
                fname = os.path.basename(p)
                if err:
                    results.append(f"❌ {fname}: {err}")
                else:
                    results.append(f"✅ {fname}: {count} 个 AppID")
            self._ui_mark_dirty(data)
            self._ui_refresh()
            messagebox.showinfo("导入完成",
                "导入结果：\n" + "\n".join(results) + "\n\n请点击「💾 储存更改」写入文件。")
        
        def import_json():
            fmt_win.destroy()
            path = filedialog.askopenfilename(
                initialdir=self.current_dir, title="选择结构化收藏夹文件（JSON）",
                filetypes=[("JSON files", "*.json")])
            if not path:
                return
            data = self.load_json()
            if data is None:
                return
            existing = self._get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            try:
                count, err = self._import_collections_structured(path, data)
                if err:
                    messagebox.showerror("导入失败", err)
                    return
                self._ui_mark_dirty(data)
                self._ui_refresh()
                messagebox.showinfo("导入完成",
                    f"✅ 已导入 {count} 个收藏夹。\n\n请点击「💾 储存更改」写入文件。")
            except json.JSONDecodeError:
                messagebox.showerror("导入失败", "文件不是有效的 JSON 格式。")
            except Exception as e:
                messagebox.showerror("导入失败", f"导入时出错：{e}")
        
        tk.Button(fmt_win, text="📄 导入 AppID 列表（TXT）\n文件名将成为收藏夹名称",
                  command=import_txt, font=("微软雅黑", 9), width=32, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📦 导入结构化数据（JSON）\n还原收藏夹名称及动态逻辑",
                  command=import_json, font=("微软雅黑", 9), width=32, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(0, 10))

    def _next_version(self, data):
        """扫描全部条目，返回下一个可用的全局版本号（字符串）"""
        max_ver = 0
        for entry in data:
            try:
                v = int(entry[1].get("version", "0"))
                if v > max_ver: max_ver = v
            except (ValueError, IndexError, TypeError):
                continue
        return str(max_ver + 1)

    def _add_static_collection(self, data, name, app_ids):
        col_id = f"uc-{secrets.token_hex(6)}"
        storage_key = f"user-collections.{col_id}"
        val_obj = {"id": col_id, "name": name + self.induce_suffix, "added": app_ids, "removed": []}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()), 
                    "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')),
                    "version": self._next_version(data),
                    "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}]
        data.append(new_entry)

    # --- 2. 批量导出 ---
    def export_static_collection(self):
        """批量导出：使用左侧勾选的收藏夹，三种格式可选"""
        selected = self._ui_get_selected()
        if not selected:
            messagebox.showwarning("提示", "请先在左侧勾选要导出的收藏夹。")
            return
        
        fmt_win = tk.Toplevel()
        fmt_win.title("批量导出收藏夹")
        fmt_win.attributes("-topmost", True)
        fmt_win.resizable(False, False)
        
        tk.Label(fmt_win, text=f"已选中 {len(selected)} 个收藏夹，请选择导出格式：",
                 font=("微软雅黑", 10), pady=10).pack(padx=20)
        
        def export_merged_appid():
            fmt_win.destroy()
            unique_ids = self._export_collections_appid_list(selected)
            if not unique_ids:
                messagebox.showwarning("提示", "选中的收藏夹没有可导出的 AppID。")
                return
            save_path = filedialog.asksaveasfilename(
                initialdir=self.current_dir, title="保存合并 AppID 列表",
                defaultextension=".txt", initialfile="merged_appids.txt",
                filetypes=[("Text files", "*.txt")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    for aid in unique_ids:
                        f.write(f"{aid}\n")
                messagebox.showinfo("✅ 导出成功",
                    f"已导出 {len(unique_ids)} 个去重 AppID。\n（来自 {len(selected)} 个收藏夹）")
        
        def export_multiple_txt():
            fmt_win.destroy()
            dest_dir = filedialog.askdirectory(initialdir=self.current_dir, title="选择保存导出文件的文件夹")
            if not dest_dir:
                return
            count = 0
            for col in selected:
                safe_name = self._sanitize_filename(col['name'])
                # 动态收藏夹只导出额外添加的 appid
                app_ids = col.get('added', [])
                if not app_ids:
                    continue
                with open(os.path.join(dest_dir, f"{safe_name}.txt"), 'w', encoding='utf-8') as f:
                    for aid in app_ids:
                        f.write(f"{aid}\n")
                count += 1
            messagebox.showinfo("✅ 导出成功",
                f"共导出 {count} 个 TXT 文件到：\n{dest_dir}")
        
        def export_structured_json():
            fmt_win.destroy()
            export_data = self._export_collections_structured(selected)
            save_path = filedialog.asksaveasfilename(
                initialdir=self.current_dir, title="保存收藏夹结构化数据",
                defaultextension=".json", initialfile="exported_collections.json",
                filetypes=[("JSON files", "*.json")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("✅ 导出成功",
                    f"已导出 {len(selected)} 个收藏夹的完整结构。\n（含名称、分类信息及动态逻辑）")
        
        tk.Button(fmt_win, text="📄 合并为单个 AppID 列表（TXT）\n所有选中收藏夹的 AppID 去重合并",
                  command=export_merged_appid, font=("微软雅黑", 9), width=36, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📁 导出为多个 TXT 文件\n每个收藏夹一个文件，动态收藏夹仅导出额外添加部分",
                  command=export_multiple_txt, font=("微软雅黑", 9), width=36, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(0, 5))
        tk.Button(fmt_win, text="📦 导出为结构化数据（JSON）\n含名称、分类、动态逻辑，可用于完整还原",
                  command=export_structured_json, font=("微软雅黑", 9), width=36, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(0, 10))

    # --- 3. 批量更新 ---
    def update_static_collection(self):
        """批量更新：选择来源格式（TXT 或 JSON），然后一屏映射所有来源到目标收藏夹"""
        fmt_win = tk.Toplevel()
        fmt_win.title("批量更新收藏夹")
        fmt_win.attributes("-topmost", True)
        fmt_win.resizable(False, False)
        
        tk.Label(fmt_win, text="请选择用于更新的来源文件格式：",
                 font=("微软雅黑", 10), pady=10).pack(padx=20)
        
        def update_from_txt():
            fmt_win.destroy()
            txt_paths = filedialog.askopenfilenames(
                initialdir=self.current_dir, title="选择 AppID 列表 (TXT)",
                filetypes=[("Text files", "*.txt")])
            if not txt_paths:
                return
            data = self.load_json()
            if data is None:
                return
            all_cols = self._get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            
            sources = {}
            for p in txt_paths:
                file_title = os.path.splitext(os.path.basename(p))[0]
                with open(p, 'r', encoding='utf-8') as f:
                    ids = [int(line.strip()) for line in f if line.strip().isdigit()]
                sources[file_title] = {"name": file_title, "ids": ids}
            
            existing = self._get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            
            def on_done():
                self._ui_mark_dirty(data)
                self._ui_refresh()
            
            self._show_batch_update_mapping(data, all_cols, sources, on_done)
        
        def update_from_json():
            fmt_win.destroy()
            path = filedialog.askopenfilename(
                initialdir=self.current_dir, title="选择结构化收藏夹文件（JSON）",
                filetypes=[("JSON files", "*.json")])
            if not path:
                return
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    import_data = json.load(f)
                if import_data.get("format") != "steam_collections_structured":
                    messagebox.showerror("格式错误", "文件不是有效的结构化收藏夹文件。")
                    return
                src_cols = import_data.get("collections", [])
                if not src_cols:
                    messagebox.showerror("无数据", "文件中没有收藏夹数据。")
                    return
            except json.JSONDecodeError:
                messagebox.showerror("格式错误", "文件不是有效的 JSON。")
                return
            except Exception as e:
                messagebox.showerror("读取失败", f"读取文件出错：{e}")
                return
            
            data = self.load_json()
            if data is None:
                return
            all_cols = self._get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            
            existing = self._get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            
            sources = {}
            for i, src in enumerate(src_cols):
                key = src.get("name", f"收藏夹 {i + 1}")
                sources[key] = {"name": key, "ids": src.get("added", [])}
            
            def on_done():
                self._ui_mark_dirty(data)
                self._ui_refresh()
            
            self._show_batch_update_mapping(data, all_cols, sources, on_done)
        
        tk.Button(fmt_win, text="📄 从 TXT 文件更新\n选择多个 AppID 列表文件",
                  command=update_from_txt, font=("微软雅黑", 9), width=32, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📦 从 JSON 文件更新\n使用结构化收藏夹数据",
                  command=update_from_json, font=("微软雅黑", 9), width=32, height=3,
                  justify=tk.LEFT).pack(padx=20, pady=(0, 10))
    
    def _show_batch_update_mapping(self, data, all_cols, sources, on_done, parent_to_close=None, saved_mappings_key=None):
        """通用的批量更新映射界面：一屏选择所有来源到目标收藏夹+更新模式"""
        up_win = tk.Toplevel()
        up_win.title("批量更新收藏夹")
        up_win.attributes("-topmost", True)
        
        tk.Label(up_win, text="请为每个来源选择目标收藏夹和更新模式：",
                 font=("微软雅黑", 10, "bold")).pack(pady=(15, 10))
        
        mapping_frame = tk.Frame(up_win)
        mapping_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 10))
        
        target_names = ["（跳过）"] + [c['display_name'] for c in all_cols]
        mode_options = ["增量", "替换"]
        combo_vars = {}
        
        # 加载上次保存的映射选择
        saved_mappings = {}
        if saved_mappings_key:
            config = self._load_config()
            saved_mappings = config.get(saved_mappings_key, {})
        
        max_target_len = max(len(n) for n in target_names) if target_names else 20
        
        def _create_row(parent, key, d):
            row_frame = tk.Frame(parent)
            row_frame.pack(fill=tk.X, pady=5)
            tk.Label(row_frame, text=f"📦 {d['name']} ({len(d['ids'])} 个)",
                     font=("微软雅黑", 9), anchor=tk.W).pack(side=tk.LEFT)
            tk.Label(row_frame, text="→", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=10)
            combo = ttk.Combobox(row_frame, values=target_names,
                                  width=max(30, max_target_len + 2), state="readonly")
            # 尝试恢复上次的选择
            last_sel = saved_mappings.get(key, "")
            if last_sel and last_sel in target_names:
                combo.set(last_sel)
            else:
                combo.set("（跳过）")
            combo.pack(side=tk.LEFT)
            mode_combo = ttk.Combobox(row_frame, values=mode_options, width=6, state="readonly")
            mode_combo.set("增量")
            mode_combo.pack(side=tk.LEFT, padx=(5, 0))
            combo_vars[key] = (combo, mode_combo)
            return row_frame
        
        if len(sources) <= 8:
            for key, d in sources.items():
                _create_row(mapping_frame, key, d)
        else:
            canvas = tk.Canvas(mapping_frame, height=300)
            scrollbar = ttk.Scrollbar(mapping_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas)
            scrollable_frame.bind("<Configure>",
                                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            def _on_mw(event):
                if event.delta:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                elif event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")
            for w in (canvas, scrollable_frame, up_win):
                w.bind("<MouseWheel>", _on_mw)
                w.bind("<Button-4>", _on_mw)
                w.bind("<Button-5>", _on_mw)
            for key, d in sources.items():
                row = _create_row(scrollable_frame, key, d)
                row.bind("<MouseWheel>", _on_mw)
                row.bind("<Button-4>", _on_mw)
                row.bind("<Button-5>", _on_mw)
            scrollable_frame.update_idletasks()
            canvas.config(width=scrollable_frame.winfo_reqwidth())
        
        def confirm_update():
            update_count = 0
            skipped_count = 0
            results = []
            
            # 保存当前的映射选择以便下次使用
            if saved_mappings_key:
                config = self._load_config()
                current_mappings = {}
                for key, (combo, _) in combo_vars.items():
                    sel = combo.get()
                    if sel != "（跳过）":
                        current_mappings[key] = sel
                config[saved_mappings_key] = current_mappings
                self._save_config(config)
            
            for key, (combo, mode_combo) in combo_vars.items():
                selected_display = combo.get()
                if selected_display == "（跳过）":
                    continue
                target = None
                for c in all_cols:
                    if c['display_name'] == selected_display:
                        target = c
                        break
                if not target:
                    continue
                source_data = sources[key]
                mode = mode_combo.get()
                if mode == "替换":
                    old_count, new_count = self._perform_replace_update(
                        data, target['entry_ref'], source_data['ids'])
                    results.append(f"🔄 {source_data['name']} → {target['name']}\n   替换: {old_count} → {new_count}")
                    update_count += 1
                else:
                    a, r, t, updated = self._perform_incremental_update(
                        data, target['entry_ref'], source_data['ids'], target['name'])
                    if updated:
                        results.append(f"✅ {source_data['name']} → {target['name']}\n   新增: {a}, 移除: {r}, 总计: {t}")
                        update_count += 1
                    else:
                        results.append(f"⏭️ {source_data['name']} → {target['name']}\n   已是最新，跳过")
                        skipped_count += 1
            if update_count > 0:
                result_text = "\n".join(results)
                messagebox.showinfo("更新完成",
                    f"已更新 {update_count} 个收藏夹，跳过 {skipped_count} 个：\n\n{result_text}" + self.disclaimer)
                up_win.destroy()
                if parent_to_close:
                    parent_to_close.destroy()
                on_done()
            elif skipped_count > 0:
                result_text = "\n".join(results)
                messagebox.showinfo("全部已是最新",
                    f"所有选中的收藏夹都已是最新。\n\n{result_text}")
                up_win.destroy()
            else:
                messagebox.showwarning("提示", "未选择任何目标收藏夹。")
        
        btn_row = tk.Frame(up_win)
        btn_row.pack(pady=15)
        tk.Button(btn_row, text="✅ 确认更新", command=confirm_update, width=15).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_row, text="取消", command=up_win.destroy, width=10).pack(side=tk.LEFT, padx=10)
    
    def _show_update_target_dialog(self, data, all_cols, new_ids, source_name, index, total, on_next):
        """单来源更新的快捷入口，内部调用 _show_batch_update_mapping"""
        sources = {source_name: {"name": source_name, "ids": new_ids}}
        self._show_batch_update_mapping(data, all_cols, sources, on_next)


    # --- 4. 动态好友同步 ---
    def open_friend_sync_ui(self):
        data = self.load_json()
        if data is None: return
        sync_win = tk.Toplevel(); sync_win.title("批量同步 Steam 用户游戏库"); sync_win.attributes("-topmost", True)
        tk.Label(sync_win, text="1. 请输入对方的 Steam 好友代码（每行一个）", font=("微软雅黑", 10, "bold")).pack(pady=(15,0))
        codes_text = tk.Text(sync_win, height=8, width=60); codes_text.pack(padx=20, pady=5)
        tk.Label(sync_win, text="2. 生成的收藏夹名称 (每行一个)", font=("微软雅黑", 10, "bold")).pack(pady=(10,0))
        names_text = tk.Text(sync_win, height=8, width=60); names_text.pack(padx=20, pady=5)
        def generate_default_names():
            raw_ids = re.findall(r'\d+', codes_text.get("1.0", tk.END))
            names_text.delete("1.0", tk.END)
            for rid in raw_ids: names_text.insert(tk.END, f"好友代码 [{rid}]\n")
        def commit_import():
            codes = re.findall(r'\d+', codes_text.get("1.0", tk.END))
            names = [n.strip() for n in names_text.get("1.0", tk.END).strip().split('\n') if n.strip()]
            for i, cid in enumerate(codes):
                cname = names[i] if i < len(names) else f"好友代码 [{cid}]"
                self._add_dynamic_collection(data, cname, cid)
            if codes: self.save_json(data, backup_description="同步好友游戏库"); sync_win.destroy()
        btn_frame = tk.Frame(sync_win); btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="✨ 生成默认名称", command=generate_default_names, width=18, height=2).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="开始导入", command=commit_import, width=18, height=2).pack(side=tk.LEFT, padx=10)

    def _add_dynamic_collection(self, data, name, friend_code):
        col_id = f"uc-{secrets.token_hex(4)}"
        storage_key = f"user-collections.{col_id}"
        filter_groups = [{"rgOptions": [], "bAcceptUnion": False} for _ in range(9)]
        filter_groups[0]["bAcceptUnion"] = True; filter_groups[6]["rgOptions"] = [int(friend_code)]
        val_obj = {"id": col_id, "name": name + self.induce_suffix, "added": [], "removed": [], "filterSpec": {"nFormatVersion": 2, "strSearchText": "", "filterGroups": filter_groups, "setSuggestions": {}}}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()),
                    "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')),
                    "version": self._next_version(data),
                    "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}]
        data.append(new_entry)

    # --- 5. 选择来源入口 ---
    def open_source_selection(self):
        sel_win = tk.Toplevel(); sel_win.title("从其他来源获取 Steam 游戏列表"); sel_win.resizable(False, False); sel_win.attributes("-topmost", True)
        tk.Label(sel_win, text="请选择获取 AppID 的来源渠道：", font=("微软雅黑", 10), pady=15).pack(padx=30)
        def _make_color_btn(parent, text, bg, command):
            lbl = tk.Label(parent, text=text, font=("微软雅黑", 11), bg=bg, fg="white",
                           padx=20, pady=12, cursor="hand2", relief=tk.RAISED, bd=1)
            lbl.pack(pady=5, padx=30, fill=tk.X)
            lbl.bind("<Enter>", lambda e: lbl.config(relief=tk.GROOVE))
            lbl.bind("<Leave>", lambda e: lbl.config(relief=tk.RAISED))
            lbl.bind("<Button-1>", lambda e: command())
            return lbl
        _make_color_btn(sel_win, "🏆 从 Steam 列表页面获取（鉴赏家/发行商等）", "#5b9bd5", lambda: [sel_win.destroy(), self.curator_sync_ui()])
        _make_color_btn(sel_win, "📊 从 SteamDB 列表页面处获取", "#e86c2c", lambda: [sel_win.destroy(), self.steamdb_sync_ui()])
        tk.Frame(sel_win, height=10).pack()

    # --- 鉴赏家/发行商/开发商等列表界面 ---
    def curator_sync_ui(self):
        data = self.load_json()
        if data is None: return
        cur_win = tk.Toplevel(); cur_win.title("同步 Steam 列表页面"); cur_win.attributes("-topmost", True)
        
        fetched_ids = []
        fetched_name = tk.StringVar(value="")
        
        tk.Label(cur_win, text="使用指南：\n1. 在下方输入框粘贴 Steam 列表页面的 URL（支持鉴赏家、发行商、开发商、系列等）。\n2. 点击「开始获取」，程序将自动抓取游戏列表。\n3. 获取完成后，选择导入、导出或更新操作。",
                 justify=tk.LEFT, font=("微软雅黑", 9), wraplength=450).pack(padx=20, pady=(15, 5))
        
        url_frame = tk.Frame(cur_win); url_frame.pack(fill=tk.X, padx=20, pady=(5, 0))
        tk.Label(url_frame, text="Steam 列表 URL：", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        url_entry = tk.Entry(url_frame, width=40, font=("微软雅黑", 9))
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        url_entry.insert(0, "https://store.steampowered.com/curator/44791597/")
        
        ex_frame = tk.Frame(cur_win); ex_frame.pack(fill=tk.X, padx=20, pady=(3, 0))
        tk.Label(ex_frame, text="示例：", font=("微软雅黑", 8), fg="gray").pack(side=tk.LEFT)
        def set_url(url):
            url_entry.delete(0, tk.END); url_entry.insert(0, url)
        tk.Button(ex_frame, text="鉴赏家", fg="blue", relief=tk.FLAT, font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/curator/44791597/")).pack(side=tk.LEFT, padx=3)
        tk.Button(ex_frame, text="发行商", fg="blue", relief=tk.FLAT, font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/publisher/Devolver%20Digital")).pack(side=tk.LEFT, padx=3)
        tk.Button(ex_frame, text="开发商", fg="blue", relief=tk.FLAT, font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/developer/Valve")).pack(side=tk.LEFT, padx=3)
        tk.Button(ex_frame, text="🌐 浏览器打开", fg="gray", relief=tk.FLAT, font=("微软雅黑", 8),
                  command=lambda: webbrowser.open(url_entry.get().strip())).pack(side=tk.RIGHT)
        
        # Cookie 状态显示（使用全局配置的 Cookie）
        saved_cookie = self._get_saved_cookie()
        cookie_status_frame = tk.Frame(cur_win)
        cookie_status_frame.pack(fill=tk.X, padx=20, pady=(8, 0))
        
        if saved_cookie:
            tk.Label(cookie_status_frame, text="🔐 已配置登录态 Cookie，可获取完整列表", 
                     font=("微软雅黑", 9), fg="green").pack(anchor=tk.W)
        else:
            tk.Label(cookie_status_frame, text="⚠️ 未配置登录态 Cookie，可能无法获取完整内容列表", 
                     font=("微软雅黑", 9), fg="orange").pack(anchor=tk.W)
            tk.Label(cookie_status_frame, text="     → 可在主界面「🔑 管理 Cookie」中配置", 
                     font=("微软雅黑", 8), fg="#888").pack(anchor=tk.W)
        
        status_var = tk.StringVar(value="尚未获取数据。")
        status_label = tk.Label(cur_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray")
        status_label.pack(padx=20, pady=(8, 0), anchor=tk.W)
        
        progress_bar = ttk.Progressbar(cur_win, length=400, mode='indeterminate')
        progress_bar.pack(padx=20, pady=(4, 0), fill=tk.X)
        progress_bar.pack_forget()
        
        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(cur_win, textvariable=detail_var, font=("微软雅黑", 8), fg="#888")
        detail_label.pack(padx=20, anchor=tk.W)
        detail_label.pack_forget()
        
        login_hint = tk.Label(cur_win, text="⚠️ 未提供登录态 Cookie，可能无法获取完整内容列表", 
                              font=("微软雅黑", 8), fg="red")
        if not saved_cookie:
            login_hint.pack(padx=20, anchor=tk.W)
        
        is_fetching = [False]
        
        def do_fetch():
            nonlocal fetched_ids
            if is_fetching[0]:
                return
            
            url_text = url_entry.get().strip()
            page_type, identifier = self._extract_steam_list_info(url_text)
            if not page_type or not identifier:
                messagebox.showwarning("错误", "无法识别 Steam 列表页面。\n请输入有效的 URL（支持鉴赏家、发行商、开发商、系列等）。")
                return
            
            is_fetching[0] = True
            fetch_btn.config(bg="#999999", cursor="wait")
            status_var.set("正在连接 Steam...")
            status_label.config(fg="gray")
            cur_win.update()
            
            login_cookies = None
            cookie_val = self._get_saved_cookie()
            if cookie_val:
                login_cookies = f"steamLoginSecure={cookie_val}"
            
            def update_progress(fetched, total, phase_info="", detail_info=""):
                def _up():
                    phase_str = f" ({phase_info})" if phase_info else ""
                    status_var.set(f"正在获取: 已发现 {fetched} 个游戏{phase_str}...")
                    if detail_info:
                        detail_var.set(detail_info)
                    cur_win.update_idletasks()
                cur_win.after(0, _up)
            
            def fetch_thread():
                nonlocal fetched_ids
                
                def show_progress():
                    progress_bar.pack(padx=20, pady=(4, 0), fill=tk.X)
                    detail_label.pack(padx=20, anchor=tk.W)
                    progress_bar.start(15)
                cur_win.after(0, show_progress)
                
                ids, name, error, has_login = self._fetch_steam_list(page_type, identifier, update_progress, login_cookies)
                
                def update_ui():
                    is_fetching[0] = False
                    fetch_btn.config(bg="#4a90d9", cursor="hand2")
                    progress_bar.stop()
                    progress_bar.pack_forget()
                    detail_label.pack_forget()
                    detail_var.set("")
                    if error:
                        status_var.set(f"❌ {error}")
                        status_label.config(fg="red")
                    else:
                        fetched_ids.clear()
                        fetched_ids.extend(ids)
                        fetched_name.set(name if name else f"Steam 列表")
                        login_str = "🔐 已登录" if has_login else "⚠️ 未登录"
                        status_var.set(f"✅ 成功获取 {len(ids)} 个游戏！({login_str})")
                        status_label.config(fg="green")
                        if has_login:
                            login_hint.pack_forget()
                
                cur_win.after(0, update_ui)
            
            threading.Thread(target=fetch_thread, daemon=True).start()
        
        fetch_btn = tk.Label(cur_win, text="📥 开始获取", font=("微软雅黑", 10, "bold"),
                             bg="#4a90d9", fg="white", padx=20, pady=8, cursor="hand2", relief=tk.RAISED, bd=1)
        fetch_btn.pack(pady=10)
        fetch_btn.bind("<Enter>", lambda e: fetch_btn.config(relief=tk.GROOVE) if not is_fetching[0] else None)
        fetch_btn.bind("<Leave>", lambda e: fetch_btn.config(relief=tk.RAISED))
        fetch_btn.bind("<Button-1>", lambda e: do_fetch())
        
        # 手动模式
        manual_expanded = tk.BooleanVar(value=False)
        manual_frame = tk.Frame(cur_win); manual_frame.pack(fill=tk.X, padx=20, pady=(5, 0))
        
        def toggle_manual():
            if manual_expanded.get():
                manual_content.pack_forget()
                toggle_btn.config(text="▶ 手动模式（备用）")
                manual_expanded.set(False)
            else:
                manual_content.pack(fill=tk.X, pady=5)
                toggle_btn.config(text="▼ 手动模式（备用）")
                manual_expanded.set(True)
        
        toggle_btn = tk.Button(manual_frame, text="▶ 手动模式（备用）", command=toggle_manual,
                               relief=tk.FLAT, font=("微软雅黑", 9), fg="#666", cursor="hand2")
        toggle_btn.pack(anchor=tk.W)
        
        manual_content = tk.Frame(manual_frame)
        
        tk.Label(manual_content, text="若自动获取失败，可手动操作：\n1. 打开 Steam 列表页面，划到底加载全部游戏。\n2. 按 F12 打开控制台，执行下方指令复制 HTML。\n3. 粘贴到文本框，点击「使用手动输入」。", 
                 justify=tk.LEFT, font=("微软雅黑", 8), fg="#666").pack(anchor=tk.W)
        
        js_cmd = "copy(document.documentElement.outerHTML)"
        def copy_js():
            cur_win.clipboard_clear(); cur_win.clipboard_append(js_cmd)
            messagebox.showinfo("成功", "指令已复制到剪贴板！\n请去浏览器控制台粘贴执行。")
        tk.Button(manual_content, text="📋 复制控制台指令", command=copy_js, font=("微软雅黑", 8)).pack(anchor=tk.W, pady=2)
        
        html_text_box = tk.Text(manual_content, height=5, width=55, font=("微软雅黑", 8))
        html_text_box.pack(fill=tk.X, pady=2)
        
        def use_manual():
            nonlocal fetched_ids
            raw_html = html_text_box.get("1.0", tk.END)
            ids = self._extract_ids_from_html(raw_html)
            if not ids:
                messagebox.showwarning("错误", "未能提取到任何 AppID。")
                return
            fetched_ids.clear()
            fetched_ids.extend(ids)
            fetched_name.set(self._extract_curator_name(raw_html))
            status_var.set(f"✅ 从手动输入中提取了 {len(ids)} 个游戏！")
            status_label.config(fg="green")
        
        tk.Button(manual_content, text="📤 使用手动输入", command=use_manual, font=("微软雅黑", 8)).pack(anchor=tk.W, pady=2)

        btn_frame = tk.Frame(cur_win); btn_frame.pack(pady=15)
        
        def check_data():
            if not fetched_ids:
                messagebox.showwarning("错误", "请先获取数据！\n点击「开始获取」按钮。")
                return False
            return True
        
        def do_create():
            if not check_data(): return
            name = simpledialog.askstring("新建收藏夹", "请输入收藏夹名称：", initialvalue=fetched_name.get())
            if name: 
                self._add_static_collection(data, name, list(fetched_ids))
                self.save_json(data, backup_description=f"从 Steam 列表创建收藏夹: {name}")
                messagebox.showinfo("录入成功", f"已建立新收藏夹。本次共录入 {len(fetched_ids)} 个 AppID。" + self.disclaimer)
                cur_win.destroy()

        def do_export():
            if not check_data(): return
            name = simpledialog.askstring("导出设置", "请输入生成的 TXT 文件名：", initialvalue=self._sanitize_filename(fetched_name.get()))
            if not name: return
            save_path = filedialog.asksaveasfilename(initialdir=self.current_dir, title="保存 AppID 列表", defaultextension=".txt", 
                                                     initialfile=f"{self._sanitize_filename(name)}.txt", filetypes=[("Text files", "*.txt")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    for aid in fetched_ids: f.write(f"{aid}\n")
                messagebox.showinfo("成功", f"已成功导出 {len(fetched_ids)} 个 AppID。" + self.disclaimer)

        def do_update():
            if not check_data(): return
            all_cols = self._get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            sources = {fetched_name.get() or "Steam 列表": {"name": fetched_name.get() or "Steam 列表", "ids": list(fetched_ids)}}
            def on_done():
                self.save_json(data, backup_description=f"从 Steam 列表更新收藏夹")
                cur_win.destroy()
            self._show_batch_update_mapping(data, all_cols, sources, on_done, parent_to_close=cur_win)

        tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export, width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15).pack(side=tk.LEFT, padx=5)

    # --- 个人推荐分类界面（Steam250 + 鉴赏家精选） ---
    def _fetch_steam250_ids(self, url, progress_callback=None):
        """从 Steam250 页面提取 AppID 列表"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        }
        
        if progress_callback:
            progress_callback(0, 0, "正在连接 Steam250...", "")
        
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20, context=self.ssl_context) as resp:
                html_content = resp.read().decode('utf-8')
            
            if progress_callback:
                progress_callback(0, 0, "正在解析页面...", "")
            
            raw_ids = re.findall(r'store\.steampowered\.com/app/(\d+)', html_content)
            
            unique_ids = []
            for aid in raw_ids:
                if aid not in unique_ids:
                    unique_ids.append(aid)
            
            app_ids = [int(aid) for aid in unique_ids[:250]]
            
            if not app_ids:
                return [], "未能从页面提取到任何 AppID。页面结构可能已变化。"
            
            return app_ids, None
            
        except urllib.error.HTTPError as e:
            return [], f"HTTP 错误 {e.code}：无法访问 Steam250。"
        except urllib.error.URLError as e:
            return [], f"网络错误：{str(e.reason)}"
        except Exception as e:
            return [], f"提取失败：{str(e)}"
    
    def personal_recommend_ui(self):
        """个人推荐分类界面：Steam250 排行榜 + 鉴赏家精选"""
        data = self.load_json()
        if data is None: return
        
        fetched_data = {}  # key: source_key, value: {'ids': [...], 'name': '...'}
        
        rec_win = tk.Toplevel()
        rec_win.title("从推荐来源获取")
        rec_win.attributes("-topmost", True)
        
        # 使用指南（明确说明勾选后的文字会成为收藏夹名称）
        guide_frame = tk.Frame(rec_win)
        guide_frame.pack(fill=tk.X, padx=20, pady=(15, 5))
        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=3, bg=rec_win.cget("bg"), relief=tk.FLAT, wrap=tk.WORD)
        guide_text.tag_config("red", foreground="red", font=("微软雅黑", 9, "bold"))
        guide_text.insert(tk.END, "使用指南：\n1. 勾选要获取的来源（可多选），")
        guide_text.insert(tk.END, "勾选框后面的文字将成为收藏夹名称", "red")
        guide_text.insert(tk.END, "。\n2. 直接点击下方的导入、导出或更新按钮，程序会自动获取数据并执行操作。")
        guide_text.config(state=tk.DISABLED)
        guide_text.pack(fill=tk.X)
        
        # ===== 数据源定义 =====
        # Steam250 排行榜（固定三个 + 动态年份）
        steam250_fixed_sources = [
            ("steam250_top250", "steam250", "https://steam250.com/top250", "前 250 优秀游戏"),
            ("steam250_hidden_gems", "steam250", "https://steam250.com/hidden_gems", "前 250 优秀小众游戏"),
            ("steam250_most_played", "steam250", "https://steam250.com/most_played", "前 250 优秀热门游戏"),
        ]
        
        # 鉴赏家精选
        curator_sources = [
            ("curator_indie_fest", "curator", "https://store.steampowered.com/curator/44791597/", "🏆 独立游戏节"),
            ("curator_thinky", "curator", "https://store.steampowered.com/curator/45228984-Thinky-Awards/", "📖 Thinky Games 数据库"),
            ("curator_moe_award", "curator", "https://store.steampowered.com/curator/45502290/", "🏆 萌系遊戲大賞"),
            ("curator_bishojo_award", "curator", "https://store.steampowered.com/curator/45531216/", "🏆 美少女游戏大赏"),
        ]
        
        check_vars = {}
        year_check_vars = {}  # 专门存储年份选项
        
        # ===== Steam250 区域 =====
        s250_frame = tk.LabelFrame(rec_win, text="📊 Steam250 排行榜", font=("微软雅黑", 10, "bold"), padx=10, pady=5)
        s250_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        
        # 固定的三个排行榜
        for key, src_type, url, name in steam250_fixed_sources:
            var = tk.BooleanVar(value=False)
            check_vars[key] = (var, src_type, url, name)
            tk.Checkbutton(s250_frame, text=name, variable=var, font=("微软雅黑", 9)).pack(anchor=tk.W)
        
        # 年度榜单区域（支持多选年份）
        year_frame = tk.Frame(s250_frame)
        year_frame.pack(fill=tk.X, pady=(5, 0))
        
        tk.Label(year_frame, text="📅 年度榜单：", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        
        # 生成最近几年的选项（从当前年份往前推 5 年）
        from datetime import datetime
        current_year = datetime.now().year
        available_years = list(range(current_year, current_year - 6, -1))  # 如 [2026, 2025, 2024, 2023, 2022, 2021]
        
        year_inner_frame = tk.Frame(year_frame)
        year_inner_frame.pack(side=tk.LEFT, padx=(5, 0))
        
        for year in available_years:
            var = tk.BooleanVar(value=False)
            key = f"steam250_{year}"
            url = f"https://steam250.com/{year}"
            name = f"前 250 优秀游戏（{year} 年度）"
            year_check_vars[key] = (var, "steam250", url, name, year)
            tk.Checkbutton(year_inner_frame, text=str(year), variable=var, font=("微软雅黑", 9)).pack(side=tk.LEFT)
        
        # ===== 全选按钮区域 =====
        select_all_frame = tk.Frame(rec_win)
        select_all_frame.pack(fill=tk.X, padx=20, pady=(5, 0))
        
        def select_all_s250():
            for k, v in check_vars.items():
                if k.startswith("steam250"):
                    v[0].set(True)
            for k, v in year_check_vars.items():
                v[0].set(True)
        
        def deselect_all_s250():
            for k, v in check_vars.items():
                if k.startswith("steam250"):
                    v[0].set(False)
            for k, v in year_check_vars.items():
                v[0].set(False)
        
        tk.Button(select_all_frame, text="☑️ 全选 Steam250", command=select_all_s250, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(select_all_frame, text="☐ 取消全选 Steam250", command=deselect_all_s250, font=("微软雅黑", 8)).pack(side=tk.LEFT)
        
        # ===== 鉴赏家精选区域 =====
        curator_frame = tk.LabelFrame(rec_win, text="🎮 鉴赏家精选", font=("微软雅黑", 10, "bold"), padx=10, pady=5)
        curator_frame.pack(fill=tk.X, padx=20, pady=5)
        
        for key, src_type, url, name in curator_sources:
            var = tk.BooleanVar(value=False)
            check_vars[key] = (var, src_type, url, name)
            cb = tk.Checkbutton(curator_frame, text=name, variable=var, font=("微软雅黑", 9))
            cb.pack(anchor=tk.W)
        
        # 鉴赏家全选按钮
        curator_btn_frame = tk.Frame(curator_frame)
        curator_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        def select_all_curator():
            for k, v in check_vars.items():
                if k.startswith("curator"):
                    v[0].set(True)
        
        def deselect_all_curator():
            for k, v in check_vars.items():
                if k.startswith("curator"):
                    v[0].set(False)
        
        tk.Button(curator_btn_frame, text="☑️ 全选鉴赏家", command=select_all_curator, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(curator_btn_frame, text="☐ 取消全选鉴赏家", command=deselect_all_curator, font=("微软雅黑", 8)).pack(side=tk.LEFT)
        
        # 提示信息
        tk.Label(curator_frame, text="💡 鉴赏家列表会使用多语言扫描以获取完整数据", 
                 font=("微软雅黑", 8), fg="#666").pack(anchor=tk.W, pady=(5, 0))
        
        # Cookie 状态提示
        cookie_status_frame = tk.Frame(curator_frame)
        cookie_status_frame.pack(fill=tk.X, pady=(3, 0))
        
        saved_cookie = self._get_saved_cookie()
        if saved_cookie:
            tk.Label(cookie_status_frame, text="🔐 已配置登录态 Cookie，可获取完整列表", 
                     font=("微软雅黑", 8), fg="green").pack(anchor=tk.W)
        else:
            tk.Label(cookie_status_frame, text="⚠️ 未配置登录态 Cookie，可能无法获取完整列表", 
                     font=("微软雅黑", 8), fg="orange").pack(anchor=tk.W)
            tk.Label(cookie_status_frame, text="     → 可在主界面「🔑 管理登录态 Cookie」中配置", 
                     font=("微软雅黑", 8), fg="#888").pack(anchor=tk.W)
        
        # ===== IGDB 游戏类型分类区域 =====
        igdb_check_vars = {}  # 存储 IGDB 类型的勾选状态
        igdb_genres_cache = []  # 缓存已加载的类型列表
        
        igdb_frame = tk.LabelFrame(rec_win, text="🏷️ 游戏类型分类（IGDB）", font=("微软雅黑", 10, "bold"), padx=10, pady=5)
        igdb_frame.pack(fill=tk.X, padx=20, pady=5)
        
        # IGDB 凭证状态
        igdb_status_frame = tk.Frame(igdb_frame)
        igdb_status_frame.pack(fill=tk.X, pady=(0, 5))
        
        igdb_client_id, igdb_client_secret = self._get_igdb_credentials()
        igdb_configured = bool(igdb_client_id and igdb_client_secret)
        
        if igdb_configured:
            igdb_status_label = tk.Label(igdb_status_frame, text="🔐 已配置 IGDB API 凭证", 
                                        font=("微软雅黑", 8), fg="green")
        else:
            igdb_status_label = tk.Label(igdb_status_frame, text="⚠️ 未配置 IGDB API 凭证，无法使用此功能", 
                                        font=("微软雅黑", 8), fg="orange")
        igdb_status_label.pack(side=tk.LEFT)
        
        if not igdb_configured:
            tk.Label(igdb_status_frame, text=" → 可在主界面「🎮 管理 IGDB API 凭证」中配置", 
                     font=("微软雅黑", 8), fg="#888").pack(side=tk.LEFT)
        
        # 类型列表容器（使用 Canvas 支持滚动）
        igdb_list_container = tk.Frame(igdb_frame)
        igdb_list_container.pack(fill=tk.X, pady=(5, 0))
        
        igdb_canvas = tk.Canvas(igdb_list_container, height=120, highlightthickness=1, highlightbackground="#ccc")
        igdb_scrollbar = ttk.Scrollbar(igdb_list_container, orient=tk.VERTICAL, command=igdb_canvas.yview)
        igdb_scrollable_frame = tk.Frame(igdb_canvas)
        
        igdb_scrollable_frame.bind(
            "<Configure>",
            lambda e: igdb_canvas.configure(scrollregion=igdb_canvas.bbox("all"))
        )
        
        igdb_canvas.create_window((0, 0), window=igdb_scrollable_frame, anchor="nw")
        igdb_canvas.configure(yscrollcommand=igdb_scrollbar.set)
        
        igdb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        igdb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 鼠标滚轮绑定
        def _igdb_mousewheel(event):
            igdb_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        igdb_canvas.bind("<MouseWheel>", _igdb_mousewheel)
        igdb_scrollable_frame.bind("<MouseWheel>", _igdb_mousewheel)
        
        # 初始提示
        igdb_placeholder = tk.Label(igdb_scrollable_frame, text="点击「加载类型列表」获取可用的游戏类型", 
                                   font=("微软雅黑", 9), fg="#888")
        igdb_placeholder.pack(pady=20)
        
        # 加载类型列表函数
        def load_igdb_genres():
            if not igdb_configured:
                messagebox.showwarning("提示", "请先在主界面配置 IGDB API 凭证。")
                return
            
            # 清空现有内容
            for widget in igdb_scrollable_frame.winfo_children():
                widget.destroy()
            
            tk.Label(igdb_scrollable_frame, text="正在加载游戏类型列表...", 
                    font=("微软雅黑", 9), fg="#888").pack(pady=20)
            rec_win.update()
            
            def fetch_genres_thread():
                genres, error = self._fetch_igdb_genres()
                
                def update_ui():
                    for widget in igdb_scrollable_frame.winfo_children():
                        widget.destroy()
                    
                    if error:
                        tk.Label(igdb_scrollable_frame, text=f"❌ 加载失败：{error}", 
                                font=("微软雅黑", 9), fg="red").pack(pady=20)
                        return
                    
                    if not genres:
                        tk.Label(igdb_scrollable_frame, text="未找到游戏类型", 
                                font=("微软雅黑", 9), fg="#888").pack(pady=20)
                        return
                    
                    igdb_genres_cache.clear()
                    igdb_genres_cache.extend(genres)
                    igdb_check_vars.clear()
                    
                    # 创建多列布局（每行 3 个）
                    row_frame = None
                    for i, genre in enumerate(genres):
                        if i % 3 == 0:
                            row_frame = tk.Frame(igdb_scrollable_frame)
                            row_frame.pack(fill=tk.X, pady=1)
                        
                        genre_id = genre.get('id')
                        genre_name = genre.get('name', '未知')
                        key = f"igdb_genre_{genre_id}"
                        
                        var = tk.BooleanVar(value=False)
                        igdb_check_vars[key] = (var, "igdb_genre", genre_id, f"🏷️ {genre_name}")
                        
                        cb = tk.Checkbutton(row_frame, text=genre_name, variable=var, 
                                           font=("微软雅黑", 9), width=18, anchor=tk.W)
                        cb.pack(side=tk.LEFT, padx=2)
                    
                    # 更新滚动区域
                    igdb_scrollable_frame.update_idletasks()
                    igdb_canvas.configure(scrollregion=igdb_canvas.bbox("all"))
                
                rec_win.after(0, update_ui)
            
            threading.Thread(target=fetch_genres_thread, daemon=True).start()
        
        # IGDB 按钮区域
        igdb_btn_frame = tk.Frame(igdb_frame)
        igdb_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        tk.Button(igdb_btn_frame, text="📋 加载类型列表", command=load_igdb_genres, 
                 font=("微软雅黑", 8), state=tk.NORMAL if igdb_configured else tk.DISABLED).pack(side=tk.LEFT, padx=(0, 5))
        
        def select_all_igdb():
            for k, v in igdb_check_vars.items():
                v[0].set(True)
        
        def deselect_all_igdb():
            for k, v in igdb_check_vars.items():
                v[0].set(False)
        
        tk.Button(igdb_btn_frame, text="☑️ 全选类型", command=select_all_igdb, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(igdb_btn_frame, text="☐ 取消全选类型", command=deselect_all_igdb, font=("微软雅黑", 8)).pack(side=tk.LEFT, padx=(0, 5))
        
        def force_rescan_igdb():
            igdb_force_refresh[0] = True
            messagebox.showinfo("提示", "已设为重新扫描模式。\n\n下次点击「建立为新收藏夹」或「更新收藏夹」时，IGDB 类型数据将跳过本地缓存，从服务器重新获取。\n\n获取完成后会自动更新本地缓存。")
        
        tk.Button(igdb_btn_frame, text="🔄 重新扫描", command=force_rescan_igdb,
                 font=("微软雅黑", 8), state=tk.NORMAL if igdb_configured else tk.DISABLED).pack(side=tk.LEFT)
        
        # 缓存状态信息
        igdb_cache_var = tk.StringVar()
        igdb_cache_label = tk.Label(igdb_frame, textvariable=igdb_cache_var, font=("微软雅黑", 8), fg="#666")
        igdb_cache_label.pack(anchor=tk.W, pady=(3, 0))
        
        def refresh_igdb_cache_status():
            summary = self._get_igdb_cache_summary()
            if summary:
                age_hours = (time.time() - summary['newest_at']) / 3600
                if age_hours < 24:
                    age_str = f"{age_hours:.0f} 小时前"
                else:
                    age_str = f"{age_hours / 24:.1f} 天前"
                igdb_cache_var.set(f"💾 本地缓存：{summary['total_genres']} 个类型，共 {summary['total_games']} 个游戏（{age_str}更新）")
                igdb_cache_label.config(fg="#2e7d32")
            else:
                igdb_cache_var.set("💾 本地缓存：无（首次获取时将自动缓存，有效期 7 天）")
                igdb_cache_label.config(fg="#888")
        
        refresh_igdb_cache_status()
        
        # 提示信息
        tk.Label(igdb_frame, text="💡 游戏类型数据来自 IGDB（Internet Game Database），每个类型可能包含数千个游戏", 
                 font=("微软雅黑", 8), fg="#666").pack(anchor=tk.W, pady=(3, 0))
        
        # ===== 状态显示 =====
        status_var = tk.StringVar(value="请勾选要获取的来源，然后点击下方按钮。")
        status_label = tk.Label(rec_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray")
        status_label.pack(padx=20, pady=(10, 0), anchor=tk.W)
        
        # 进度条
        progress_bar = ttk.Progressbar(rec_win, length=400, mode='indeterminate')
        progress_bar.pack(padx=20, pady=(5, 0), fill=tk.X)
        progress_bar.pack_forget()
        
        # 详细状态
        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(rec_win, textvariable=detail_var, font=("微软雅黑", 8), fg="#888")
        detail_label.pack(padx=20, anchor=tk.W)
        detail_label.pack_forget()
        
        is_fetching = [False]
        igdb_force_refresh = [False]  # IGDB 强制重新扫描标记
        
        # ===== 核心：获取数据并执行后续操作 =====
        def fetch_and_execute(action_type, action_callback):
            """获取数据后执行指定操作
            action_type: 'create' | 'export' | 'update'
            action_callback: 获取完成后执行的回调函数
            """
            # 收集所有选中的来源（包括固定项和年份项）
            selected = [(k, v[1], v[2], v[3]) for k, v in check_vars.items() if v[0].get()]
            # 添加选中的年份
            for k, v in year_check_vars.items():
                if v[0].get():
                    selected.append((k, v[1], v[2], v[3]))  # key, src_type, url/genre_id, name
            # 添加选中的 IGDB 游戏类型
            for k, v in igdb_check_vars.items():
                if v[0].get():
                    selected.append((k, v[1], v[2], v[3]))  # key, src_type, genre_id, name
            
            if not selected:
                messagebox.showwarning("提示", "请至少勾选一个来源。")
                return
            
            if is_fetching[0]:
                return
            is_fetching[0] = True
            
            # 禁用按钮
            for btn in btn_widgets:
                btn.config(state=tk.DISABLED)
            
            def fetch_thread():
                fetched_data.clear()
                total = len(selected)
                
                # 显示进度条
                def show_progress():
                    progress_bar.pack(padx=20, pady=(5, 0), fill=tk.X)
                    detail_label.pack(padx=20, anchor=tk.W)
                    progress_bar.start(15)
                rec_win.after(0, show_progress)
                
                for i, (key, src_type, url_or_id, name) in enumerate(selected):
                    def update_status(msg, detail=""):
                        def _up():
                            status_var.set(msg)
                            if detail:
                                detail_var.set(detail)
                        rec_win.after(0, _up)
                    
                    update_status(f"正在获取 [{i+1}/{total}]: {name}...")
                    
                    if src_type == "steam250":
                        # Steam250 抓取
                        ids, error = self._fetch_steam250_ids(url_or_id)
                        if error:
                            update_status(f"❌ {name}: {error}")
                        else:
                            fetched_data[key] = {'ids': ids, 'name': name}
                            update_status(f"✅ {name}: 获取 {len(ids)} 个游戏")
                    
                    elif src_type == "curator":
                        # 鉴赏家抓取（使用现有的多语言扫描功能）
                        page_type, identifier = self._extract_steam_list_info(url_or_id)
                        if page_type and identifier:
                            def progress_cb(fetched, total_count, phase, detail):
                                update_status(f"正在获取 [{i+1}/{total}]: {name} ({phase})", detail)
                            
                            # 获取已保存的 Cookie
                            login_cookies = None
                            saved_cookie = self._get_saved_cookie()
                            if saved_cookie:
                                login_cookies = f"steamLoginSecure={saved_cookie}"
                            
                            ids, display_name, error, has_login = self._fetch_steam_list(
                                page_type, identifier, progress_cb, login_cookies
                            )
                            
                            if error:
                                update_status(f"❌ {name}: {error}")
                            else:
                                fetched_data[key] = {'ids': ids, 'name': name}
                                login_str = "🔐" if has_login else "⚠️"
                                update_status(f"✅ {name}: 获取 {len(ids)} 个游戏 {login_str}")
                        else:
                            update_status(f"❌ {name}: 无法解析 URL")
                    
                    elif src_type == "igdb_genre":
                        # IGDB 游戏类型抓取
                        genre_id = url_or_id
                        genre_name = name.replace("🏷️ ", "")  # 移除前缀用于显示
                        
                        def igdb_progress_cb(fetched, total_count, phase, detail):
                            update_status(f"正在获取 [{i+1}/{total}]: {name} ({phase})", detail)
                        
                        ids, error = self._fetch_igdb_games_by_genre(genre_id, genre_name, igdb_progress_cb, force_refresh=igdb_force_refresh[0])
                        
                        if error:
                            update_status(f"❌ {name}: {error}")
                        else:
                            fetched_data[key] = {'ids': ids, 'name': name}
                            # 检查是否来自缓存
                            cached_ids, cached_at = self._get_igdb_genre_cache(genre_id)
                            if not igdb_force_refresh[0] and cached_ids is not None and self._is_igdb_cache_valid(cached_at):
                                update_status(f"✅ {name}: {len(ids)} 个游戏（本地缓存）")
                            else:
                                update_status(f"✅ {name}: 获取 {len(ids)} 个游戏（已缓存）")
                    
                    time.sleep(0.3)
                
                def final_update():
                    is_fetching[0] = False
                    igdb_force_refresh[0] = False  # 重置强制刷新标记
                    progress_bar.stop()
                    progress_bar.pack_forget()
                    detail_label.pack_forget()
                    detail_var.set("")
                    
                    # 恢复按钮
                    for btn in btn_widgets:
                        btn.config(state=tk.NORMAL)
                    
                    # 刷新 IGDB 缓存状态显示
                    try:
                        refresh_igdb_cache_status()
                    except:
                        pass
                    
                    if fetched_data:
                        total_ids = sum(len(d['ids']) for d in fetched_data.values())
                        status_var.set(f"✅ 获取完成！共 {len(fetched_data)} 个来源，{total_ids} 个游戏。")
                        status_label.config(fg="green")
                        # 执行后续操作
                        action_callback()
                    else:
                        status_var.set("❌ 所有来源获取失败。")
                        status_label.config(fg="red")
                
                rec_win.after(0, final_update)
            
            threading.Thread(target=fetch_thread, daemon=True).start()
        
        # ===== 操作按钮 =====
        btn_frame = tk.Frame(rec_win)
        btn_frame.pack(pady=15)
        
        btn_widgets = []  # 存储按钮引用，用于禁用/启用
        
        def do_create():
            def create_action():
                # 创建名称编辑窗口，允许用户在导入前修改名称
                name_win = tk.Toplevel()
                name_win.title("确认收藏夹名称")
                name_win.attributes("-topmost", True)
                
                tk.Label(name_win, text="请确认或修改收藏夹名称：", 
                         font=("微软雅黑", 10, "bold")).pack(pady=(15, 10), padx=20)
                
                # 提示信息
                hint_text = tk.Text(name_win, font=("微软雅黑", 8), height=2, 
                                   bg=name_win.cget("bg"), relief=tk.FLAT, fg="#666")
                hint_text.insert(tk.END, "💡 修改下方文本框中的名称即可自定义收藏夹名称。\n程序会自动添加后缀「(删除这段字以触发云同步)」。")
                hint_text.config(state=tk.DISABLED)
                hint_text.pack(padx=20, fill=tk.X)
                
                # 名称编辑区域
                edit_frame = tk.Frame(name_win)
                edit_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
                
                # 使用 Canvas 支持滚动
                canvas = tk.Canvas(edit_frame, height=200)
                scrollbar = ttk.Scrollbar(edit_frame, orient="vertical", command=canvas.yview)
                scrollable_frame = tk.Frame(canvas)
                
                scrollable_frame.bind(
                    "<Configure>",
                    lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
                )
                
                canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
                canvas.configure(yscrollcommand=scrollbar.set)
                
                canvas.pack(side="left", fill="both", expand=True)
                scrollbar.pack(side="right", fill="y")
                
                # 为每个来源创建名称编辑项
                name_entries = {}
                for key, d in fetched_data.items():
                    row_frame = tk.Frame(scrollable_frame)
                    row_frame.pack(fill=tk.X, pady=3)
                    
                    tk.Label(row_frame, text=f"📦 {len(d['ids'])} 个游戏 →", 
                             font=("微软雅黑", 9), width=15, anchor=tk.E).pack(side=tk.LEFT)
                    
                    name_var = tk.StringVar(value=d['name'])
                    entry = tk.Entry(row_frame, textvariable=name_var, width=35, font=("微软雅黑", 9))
                    entry.pack(side=tk.LEFT, padx=5)
                    name_entries[key] = name_var
                
                def confirm_create():
                    # 使用用户编辑后的名称创建收藏夹
                    for key, d in fetched_data.items():
                        new_name = name_entries[key].get().strip()
                        if new_name:
                            self._add_static_collection(data, new_name, d['ids'])
                    self.save_json(data, backup_description="从个人推荐分类创建收藏夹")
                    messagebox.showinfo("成功", f"已创建 {len(fetched_data)} 个收藏夹。" + self.disclaimer)
                    name_win.destroy()
                    rec_win.destroy()
                
                btn_row = tk.Frame(name_win)
                btn_row.pack(pady=15)
                tk.Button(btn_row, text="✅ 确认创建", command=confirm_create, width=15).pack(side=tk.LEFT, padx=10)
                tk.Button(btn_row, text="取消", command=name_win.destroy, width=10).pack(side=tk.LEFT, padx=10)
            
            fetch_and_execute('create', create_action)
        
        def do_export():
            # 先选择目录，再获取数据
            dest_dir = filedialog.askdirectory(initialdir=self.current_dir, title="选择保存文件夹")
            if not dest_dir:
                return
            
            def export_action():
                for key, d in fetched_data.items():
                    safe_name = self._sanitize_filename(d['name'])
                    with open(os.path.join(dest_dir, f"{safe_name}.txt"), 'w', encoding='utf-8') as f:
                        for aid in d['ids']:
                            f.write(f"{aid}\n")
                messagebox.showinfo("成功", f"已导出 {len(fetched_data)} 个文件。")
            fetch_and_execute('export', export_action)
        
        def do_update():
            all_cols = self._get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            
            def update_action():
                sources = {}
                for key, d in fetched_data.items():
                    sources[key] = {"name": d['name'], "ids": d['ids']}
                
                def on_done():
                    self.save_json(data, backup_description="从个人推荐分类更新收藏夹")
                    rec_win.destroy()
                
                self._show_batch_update_mapping(data, all_cols, sources, on_done,
                                                 parent_to_close=rec_win,
                                                 saved_mappings_key="recommend_update_mappings")
            
            fetch_and_execute('update', update_action)

        
        # 按钮排列顺序遵守规范：[导入]、[导出]、[更新]
        btn1 = tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15)
        btn1.pack(side=tk.LEFT, padx=5)
        btn_widgets.append(btn1)
        
        btn2 = tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export, width=18)
        btn2.pack(side=tk.LEFT, padx=5)
        btn_widgets.append(btn2)
        
        btn3 = tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15)
        btn3.pack(side=tk.LEFT, padx=5)
        btn_widgets.append(btn3)

    # --- SteamDB 列表导入界面 ---
    def steamdb_sync_ui(self):
        data = self.load_json()
        if data is None: return

        merged_ids = []
        merge_stats = []

        db_win = tk.Toplevel(); db_win.title("从 SteamDB 列表页面获取游戏"); db_win.attributes("-topmost", True)

        tk.Label(db_win, text="使用指南：\n1. 在浏览器打开 SteamDB 列表页面，右键 →「另存为」保存完整网页源代码。\n2. 如需合并多个列表，重复保存即可。\n3. 点击下方按钮选择所有已保存的 HTML 文件。",
                 justify=tk.LEFT, font=("微软雅黑", 9), wraplength=500).pack(padx=20, pady=(15, 5))

        status_var = tk.StringVar(value="尚未选择文件。")
        status_label = tk.Label(db_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray"); status_label.pack(padx=20, anchor=tk.W)

        name_var = tk.StringVar(value="SteamDB List")
        name_frame = tk.Frame(db_win); name_frame.pack(fill=tk.X, padx=20, pady=(10, 0))
        tk.Label(name_frame, text="收藏夹 / 文件名称：", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        name_entry = tk.Entry(name_frame, textvariable=name_var, width=35, font=("微软雅黑", 9)); name_entry.pack(side=tk.LEFT, padx=5)

        def do_select_files():
            nonlocal merged_ids, merge_stats
            file_paths = filedialog.askopenfilenames(
                initialdir=self.current_dir, title="选择 SteamDB 源代码文件 (可多选)",
                filetypes=[("HTML files", "*.html"), ("Text files", "*.txt"), ("All files", "*.*")]
            )
            if not file_paths: return

            all_raw_ids = []
            merge_stats.clear()
            for path in file_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    page_ids = self._extract_ids_from_steamdb_html(content)
                    if page_ids:
                        all_raw_ids.extend(page_ids)
                        merge_stats.append(f"• {os.path.basename(path)}: {len(page_ids)} 个")
                    else:
                        merge_stats.append(f"• {os.path.basename(path)}: 未提取到 ID，已跳过")
                except Exception as e:
                    merge_stats.append(f"• {os.path.basename(path)}: 读取失败 ({e})")

            merged_ids.clear()
            merged_ids.extend(list(dict.fromkeys(all_raw_ids)))

            if merged_ids:
                status_var.set(f"✅ 已从 {len(file_paths)} 个文件中提取并合并 {len(merged_ids)} 个唯一 AppID（原始 {len(all_raw_ids)} 个）。")
                status_label.config(fg="green")
                if len(file_paths) == 1:
                    name_var.set(os.path.splitext(os.path.basename(file_paths[0]))[0])
            else:
                status_var.set("❌ 所选文件中均未提取到有效的 AppID。")
                status_label.config(fg="red")

        select_lbl = tk.Label(db_win, text="📂 选择 SteamDB HTML 文件（可多选合并）",
                  font=("微软雅黑", 10, "bold"), bg="#4a90d9", fg="white",
                  padx=15, pady=8, cursor="hand2", relief=tk.RAISED, bd=1)
        select_lbl.pack(pady=10)
        select_lbl.bind("<Enter>", lambda e: select_lbl.config(relief=tk.GROOVE))
        select_lbl.bind("<Leave>", lambda e: select_lbl.config(relief=tk.RAISED))
        select_lbl.bind("<Button-1>", lambda e: do_select_files())

        def do_create():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            name = simpledialog.askstring("新建收藏夹", "请输入收藏夹名称：", initialvalue=name_var.get())
            if name:
                self._add_static_collection(data, name, list(merged_ids)); self.save_json(data, backup_description=f"从 SteamDB 创建收藏夹: {name}")
                detail = '\n'.join(merge_stats)
                messagebox.showinfo("录入成功", f"已建立新收藏夹。本次共录入 {len(merged_ids)} 个 AppID。\n\n各文件明细：\n{detail}" + self.disclaimer)
                db_win.destroy()

        def do_export_txt():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            name = simpledialog.askstring("导出设置", "请输入生成的 TXT 文件名：", initialvalue=self._sanitize_filename(name_var.get()))
            if not name: return
            save_path = filedialog.asksaveasfilename(initialdir=self.current_dir, title="保存 AppID 列表", defaultextension=".txt",
                                                     initialfile=f"{self._sanitize_filename(name)}.txt", filetypes=[("Text files", "*.txt")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    for aid in merged_ids: f.write(f"{aid}\n")
                detail = '\n'.join(merge_stats)
                messagebox.showinfo("成功", f"已成功导出 {len(merged_ids)} 个 AppID。\n\n各文件明细：\n{detail}" + self.disclaimer)

        def do_update():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            all_cols = self._get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            sources = {"SteamDB 列表": {"name": "SteamDB 列表", "ids": list(merged_ids)}}
            def on_done():
                self.save_json(data, backup_description="从 SteamDB 更新收藏夹")
                db_win.destroy()
            self._show_batch_update_mapping(data, all_cols, sources, on_done, parent_to_close=db_win)

        btn_frame = tk.Frame(db_win); btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export_txt, width=18).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15).pack(side=tk.LEFT, padx=5)

    # ==================== 备份管理界面 ====================
    def open_backup_manager_ui(self):
        """打开备份管理界面"""
        if not self.backup_manager:
            messagebox.showerror("错误", "请先选择一个 Steam 账号。")
            return
        
        bk_win = tk.Toplevel()
        bk_win.title("管理收藏夹备份")
        bk_win.attributes("-topmost", True)
        
        # 当前账号信息
        account_frame = tk.Frame(bk_win, bg="#f0f0f0", pady=8)
        account_frame.pack(fill=tk.X)
        tk.Label(account_frame, text=f"📂 当前账号: {self.current_account['persona_name']} ({self.current_account['friend_code']})",
                 font=("微软雅黑", 10, "bold"), bg="#f0f0f0").pack(side=tk.LEFT, padx=15)
        
        # 当前文件信息
        current_frame = tk.LabelFrame(bk_win, text="📄 当前使用的文件", font=("微软雅黑", 10, "bold"), padx=10, pady=10)
        current_frame.pack(fill=tk.X, padx=15, pady=(10, 5))
        
        if os.path.exists(self.json_path):
            file_size = os.path.getsize(self.json_path)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(self.json_path))
            
            # 统计收藏夹数量
            try:
                data = self.load_json()
                statics = self._get_static_collections(data) if data else []
                col_count = len(statics)
            except:
                col_count = "?"
            
            info_text = f"路径: {self.json_path}\n大小: {file_size:,} 字节 | 修改时间: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')} | 收藏夹数: {col_count}"
            tk.Label(current_frame, text=info_text, font=("微软雅黑", 9), justify=tk.LEFT, wraplength=650).pack(anchor=tk.W)
        
        # 手动创建备份
        manual_frame = tk.Frame(bk_win)
        manual_frame.pack(fill=tk.X, padx=15, pady=5)
        
        desc_var = tk.StringVar(value="")
        tk.Label(manual_frame, text="备份描述（可选）:", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        desc_entry = tk.Entry(manual_frame, textvariable=desc_var, width=30, font=("微软雅黑", 9))
        desc_entry.pack(side=tk.LEFT, padx=5)
        
        def do_manual_backup():
            desc = desc_var.get().strip()
            backup_path = self.backup_manager.create_backup(description=desc if desc else "手动备份")
            if backup_path:
                messagebox.showinfo("成功", f"✅ 备份已创建:\n{os.path.basename(backup_path)}")
                refresh_backup_list()
            else:
                messagebox.showerror("错误", "❌ 备份创建失败。")
        
        tk.Button(manual_frame, text="💾 立即创建备份", command=do_manual_backup, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=10)
        
        # 备份列表
        list_frame = tk.LabelFrame(bk_win, text="📚 备份历史", font=("微软雅黑", 10, "bold"), padx=10, pady=10)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        # 表头
        columns = ("filename", "time", "size", "description")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        tree.heading("filename", text="文件名")
        tree.heading("time", text="创建时间")
        tree.heading("size", text="大小")
        tree.heading("description", text="描述")
        
        tree.column("filename", width=250)
        tree.column("time", width=140)
        tree.column("size", width=80)
        tree.column("description", width=180)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        def refresh_backup_list():
            for item in tree.get_children():
                tree.delete(item)
            
            backups = self.backup_manager.list_backups()
            for b in backups:
                size_str = f"{b['size']:,} B"
                if b['size'] > 1024:
                    size_str = f"{b['size']/1024:.1f} KB"
                tree.insert("", tk.END, values=(
                    b['filename'],
                    b['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
                    size_str,
                    b['description']
                ))
        
        refresh_backup_list()
        
        # 操作按钮
        btn_frame = tk.Frame(bk_win)
        btn_frame.pack(fill=tk.X, padx=15, pady=10)
        
        def get_selected_backup():
            selected = tree.selection()
            if not selected:
                messagebox.showwarning("提示", "请先选择一个备份。")
                return None
            item = tree.item(selected[0])
            return item['values'][0]  # filename
        
        def do_view_diff():
            filename = get_selected_backup()
            if not filename:
                return
            self._show_diff_window(filename)
        
        def do_restore():
            filename = get_selected_backup()
            if not filename:
                return
            if messagebox.askyesno("确认恢复", f"确定要恢复到此备份吗？\n\n{filename}\n\n当前文件将在恢复前自动备份。"):
                if self.backup_manager.restore_backup(filename):
                    messagebox.showinfo("成功", "✅ 已成功恢复备份！")
                    refresh_backup_list()
                else:
                    messagebox.showerror("错误", "❌ 恢复失败。")
        
        def do_delete():
            filename = get_selected_backup()
            if not filename:
                return
            if messagebox.askyesno("确认删除", f"确定要删除此备份吗？\n\n{filename}\n\n此操作不可恢复。"):
                if self.backup_manager.delete_backup(filename):
                    messagebox.showinfo("成功", "✅ 备份已删除。")
                    refresh_backup_list()
                else:
                    messagebox.showerror("错误", "❌ 删除失败。")
        
        tk.Button(btn_frame, text="🔍 查看差异", command=do_view_diff, width=12, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="⏪ 恢复此备份", command=do_restore, width=12, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🗑 删除备份", command=do_delete, width=12, font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🔄 刷新列表", command=refresh_backup_list, width=12, font=("微软雅黑", 9)).pack(side=tk.RIGHT, padx=5)
    
    def _show_diff_window(self, backup_filename):
        """显示备份与当前文件的差异详情"""
        diff_result = self.backup_manager.compare_with_current(backup_filename)
        
        if 'error' in diff_result:
            messagebox.showerror("错误", f"比较失败: {diff_result['error']}")
            return
        
        diff_win = tk.Toplevel()
        diff_win.title(f"差异对比: {backup_filename} ↔ 当前文件")
        diff_win.attributes("-topmost", True)
        
        # 摘要信息
        summary = diff_result['summary']
        summary_frame = tk.Frame(diff_win, bg="#e8f4f8", pady=10)
        summary_frame.pack(fill=tk.X)
        
        summary_text = f"📊 变化摘要:  新增 {summary['total_added']} 个收藏夹  |  删除 {summary['total_removed']} 个  |  修改 {summary['total_modified']} 个  |  未变 {summary['total_unchanged']} 个"
        tk.Label(summary_frame, text=summary_text, font=("微软雅黑", 10, "bold"), bg="#e8f4f8").pack()
        
        # 创建 Notebook 用于分类显示
        notebook = ttk.Notebook(diff_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # --- 新增的收藏夹 ---
        if diff_result['added_collections']:
            added_frame = tk.Frame(notebook)
            notebook.add(added_frame, text=f"➕ 新增 ({len(diff_result['added_collections'])})")
            
            added_text = tk.Text(added_frame, font=("微软雅黑", 9), wrap=tk.WORD)
            added_scroll = ttk.Scrollbar(added_frame, orient=tk.VERTICAL, command=added_text.yview)
            added_text.configure(yscrollcommand=added_scroll.set)
            added_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            added_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            added_text.tag_config("title", foreground="#2e7d32", font=("微软雅黑", 10, "bold"))
            added_text.tag_config("info", foreground="#666")
            
            for col in diff_result['added_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                added_text.insert(tk.END, f"• {col['name']}\n", "title")
                added_text.insert(tk.END, f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")
            
            added_text.config(state=tk.DISABLED)
        
        # --- 删除的收藏夹 ---
        if diff_result['removed_collections']:
            removed_frame = tk.Frame(notebook)
            notebook.add(removed_frame, text=f"➖ 删除 ({len(diff_result['removed_collections'])})")
            
            removed_text = tk.Text(removed_frame, font=("微软雅黑", 9), wrap=tk.WORD)
            removed_scroll = ttk.Scrollbar(removed_frame, orient=tk.VERTICAL, command=removed_text.yview)
            removed_text.configure(yscrollcommand=removed_scroll.set)
            removed_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            removed_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            removed_text.tag_config("title", foreground="#c62828", font=("微软雅黑", 10, "bold"))
            removed_text.tag_config("info", foreground="#666")
            
            for col in diff_result['removed_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                removed_text.insert(tk.END, f"• {col['name']}\n", "title")
                removed_text.insert(tk.END, f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")
            
            removed_text.config(state=tk.DISABLED)
        
        # --- 修改的收藏夹 ---
        if diff_result['modified_collections']:
            modified_frame = tk.Frame(notebook)
            notebook.add(modified_frame, text=f"✏️ 修改 ({len(diff_result['modified_collections'])})")
            
            modified_text = tk.Text(modified_frame, font=("微软雅黑", 9), wrap=tk.WORD)
            modified_scroll = ttk.Scrollbar(modified_frame, orient=tk.VERTICAL, command=modified_text.yview)
            modified_text.configure(yscrollcommand=modified_scroll.set)
            modified_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            modified_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            modified_text.tag_config("title", foreground="#1565c0", font=("微软雅黑", 10, "bold"))
            modified_text.tag_config("name_change", foreground="#6a1b9a")
            modified_text.tag_config("added", foreground="#2e7d32")
            modified_text.tag_config("removed", foreground="#c62828")
            modified_text.tag_config("info", foreground="#666")
            
            for col in diff_result['modified_collections']:
                # 收藏夹名称
                if col['name_changed']:
                    modified_text.insert(tk.END, f"• {col['old_name']} → {col['new_name']}\n", "name_change")
                else:
                    modified_text.insert(tk.END, f"• {col['new_name']}\n", "title")
                
                # 游戏数变化
                modified_text.insert(tk.END, f"   游戏数: {col['old_game_count']} → {col['new_game_count']}\n", "info")
                
                # 新增的游戏
                if col['added_games']:
                    added_preview = col['added_games'][:10]
                    modified_text.insert(tk.END, f"   ➕ 新增 {len(col['added_games'])} 个: ", "added")
                    modified_text.insert(tk.END, f"{', '.join(map(str, added_preview))}")
                    if len(col['added_games']) > 10:
                        modified_text.insert(tk.END, f" ... 等")
                    modified_text.insert(tk.END, "\n")
                
                # 移除的游戏
                if col['removed_games']:
                    removed_preview = col['removed_games'][:10]
                    modified_text.insert(tk.END, f"   ➖ 移除 {len(col['removed_games'])} 个: ", "removed")
                    modified_text.insert(tk.END, f"{', '.join(map(str, removed_preview))}")
                    if len(col['removed_games']) > 10:
                        modified_text.insert(tk.END, f" ... 等")
                    modified_text.insert(tk.END, "\n")
                
                modified_text.insert(tk.END, "\n")
            
            modified_text.config(state=tk.DISABLED)
        
        # --- 未变化的收藏夹 ---
        if diff_result['unchanged_collections']:
            unchanged_frame = tk.Frame(notebook)
            notebook.add(unchanged_frame, text=f"⚪ 未变 ({len(diff_result['unchanged_collections'])})")
            
            unchanged_text = tk.Text(unchanged_frame, font=("微软雅黑", 9), wrap=tk.WORD)
            unchanged_scroll = ttk.Scrollbar(unchanged_frame, orient=tk.VERTICAL, command=unchanged_text.yview)
            unchanged_text.configure(yscrollcommand=unchanged_scroll.set)
            unchanged_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            unchanged_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            unchanged_text.tag_config("title", foreground="#666", font=("微软雅黑", 9))
            unchanged_text.tag_config("info", foreground="#999")
            
            for col in diff_result['unchanged_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                unchanged_text.insert(tk.END, f"• {col['name']}\n", "title")
                unchanged_text.insert(tk.END, f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")
            
            unchanged_text.config(state=tk.DISABLED)
        
        # 关闭按钮
        tk.Button(diff_win, text="关闭", command=diff_win.destroy, width=10).pack(pady=10)

    # ==================== Cookie 管理界面 ====================
    def open_cookie_manager_ui(self):
        """打开全局 Cookie 管理界面"""
        cookie_win = tk.Toplevel()
        cookie_win.title("管理登录态 Cookie")
        cookie_win.attributes("-topmost", True)
        
        # 说明区域
        guide_frame = tk.Frame(cookie_win)
        guide_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=5, bg=cookie_win.cget("bg"), 
                            relief=tk.FLAT, wrap=tk.WORD)
        guide_text.tag_config("bold", font=("微软雅黑", 9, "bold"))
        guide_text.tag_config("orange", foreground="orange")
        guide_text.insert(tk.END, "Cookie 的用途：\n", "bold")
        guide_text.insert(tk.END, "配置 Steam 登录态 Cookie 后，从鉴赏家列表获取游戏时可以获得")
        guide_text.insert(tk.END, "完整的列表", "orange")
        guide_text.insert(tk.END, "。\n\n未配置 Cookie 时，部分被 Steam 限制的内容可能无法获取。")
        guide_text.config(state=tk.DISABLED)
        guide_text.pack(fill=tk.X)
        
        # 当前状态
        status_frame = tk.Frame(cookie_win)
        status_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        saved_cookie = self._get_saved_cookie()
        if saved_cookie:
            status_label = tk.Label(status_frame, text="🔐 当前状态：已配置 Cookie", 
                                   font=("微软雅黑", 10, "bold"), fg="green")
        else:
            status_label = tk.Label(status_frame, text="⚠️ 当前状态：未配置 Cookie", 
                                   font=("微软雅黑", 10, "bold"), fg="orange")
        status_label.pack(anchor=tk.W)
        
        # 获取方法说明
        help_frame = tk.LabelFrame(cookie_win, text="📖 获取 Cookie 的方法", 
                                   font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        help_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        help_text = """1. 用浏览器登录 store.steampowered.com
2. 按 F12 打开开发者工具
3. 切换到 Application（应用程序）标签页
4. 左侧找到 Cookies → store.steampowered.com
5. 找到 steamLoginSecure，复制其 Value 值"""
        
        tk.Label(help_frame, text=help_text, font=("微软雅黑", 9), justify=tk.LEFT).pack(anchor=tk.W)
        
        # Cookie 输入区域
        input_frame = tk.LabelFrame(cookie_win, text="🔑 输入 Cookie", 
                                    font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        input_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        cookie_var = tk.StringVar(value=saved_cookie)
        cookie_entry = tk.Entry(input_frame, textvariable=cookie_var, width=60, font=("微软雅黑", 9), show="•")
        cookie_entry.pack(fill=tk.X, pady=(0, 8))
        
        # 按钮行
        btn_frame = tk.Frame(input_frame)
        btn_frame.pack(fill=tk.X)
        
        def toggle_show():
            if cookie_entry.cget('show') == '•':
                cookie_entry.config(show='')
                show_btn.config(text="🙈 隐藏")
            else:
                cookie_entry.config(show='•')
                show_btn.config(text="👁 显示")
        
        def save_cookie():
            val = cookie_var.get().strip()
            if val:
                self._save_cookie(val)
                status_label.config(text="🔐 当前状态：已配置 Cookie", fg="green")
                messagebox.showinfo("保存成功", "✅ Cookie 已保存！\n\n此 Cookie 将用于所有鉴赏家列表的获取。")
            else:
                messagebox.showwarning("提示", "请先输入 Cookie 值。")
        
        def clear_cookie():
            if messagebox.askyesno("确认清除", "确定要清除已保存的 Cookie 吗？"):
                cookie_var.set("")
                self._clear_saved_cookie()
                status_label.config(text="⚠️ 当前状态：未配置 Cookie", fg="orange")
                messagebox.showinfo("已清除", "Cookie 已清除。")
        
        show_btn = tk.Button(btn_frame, text="👁 显示", command=toggle_show, font=("微软雅黑", 9), width=10)
        show_btn.pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(btn_frame, text="💾 保存 Cookie", command=save_cookie, font=("微软雅黑", 9), width=15).pack(side=tk.LEFT, padx=8)
        tk.Button(btn_frame, text="🗑 清除 Cookie", command=clear_cookie, font=("微软雅黑", 9), width=15).pack(side=tk.LEFT, padx=8)
        
        # 安全提示
        tk.Label(cookie_win, text="⚠️ Cookie 包含敏感信息，请勿分享配置文件给他人", 
                 font=("微软雅黑", 8), fg="red").pack(pady=(0, 15))

    # ==================== IGDB API 凭证管理界面 ====================
    def open_igdb_credentials_ui(self):
        """打开 IGDB API 凭证管理界面"""
        igdb_win = tk.Toplevel()
        igdb_win.title("管理 IGDB API 凭证")
        igdb_win.attributes("-topmost", True)
        
        # 说明区域
        guide_frame = tk.Frame(igdb_win)
        guide_frame.pack(fill=tk.X, padx=20, pady=(15, 10))
        
        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=4, bg=igdb_win.cget("bg"), 
                            relief=tk.FLAT, wrap=tk.WORD)
        guide_text.tag_config("bold", font=("微软雅黑", 9, "bold"))
        guide_text.tag_config("purple", foreground="#7c3aed")
        guide_text.insert(tk.END, "IGDB API 的用途：\n", "bold")
        guide_text.insert(tk.END, "配置 IGDB API 凭证后，可以按")
        guide_text.insert(tk.END, "游戏类型分类", "purple")
        guide_text.insert(tk.END, "获取游戏列表。\nIGDB（Internet Game Database）是一个综合性的游戏数据库，由 Twitch（Amazon）运营。")
        guide_text.config(state=tk.DISABLED)
        guide_text.pack(fill=tk.X)
        
        # 当前状态
        status_frame = tk.Frame(igdb_win)
        status_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        saved_id, saved_secret = self._get_igdb_credentials()
        if saved_id and saved_secret:
            status_label = tk.Label(status_frame, text="🔐 当前状态：已配置 IGDB API 凭证", 
                                   font=("微软雅黑", 10, "bold"), fg="green")
        else:
            status_label = tk.Label(status_frame, text="⚠️ 当前状态：未配置 IGDB API 凭证", 
                                   font=("微软雅黑", 10, "bold"), fg="orange")
        status_label.pack(anchor=tk.W)
        
        # 获取方法说明
        help_frame = tk.LabelFrame(igdb_win, text="📖 获取 IGDB API 凭证的方法", 
                                   font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        help_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        help_text = """1. 访问 https://dev.twitch.tv/console/apps 并登录 Twitch 账号
2. 点击「Register Your Application」注册一个应用
3. 名称随意，OAuth Redirect URLs 填写 http://localhost
4. 分类选择「Application Integration」
5. 创建后点击应用，复制 Client ID
6. 点击「New Secret」生成并复制 Client Secret"""
        
        tk.Label(help_frame, text=help_text, font=("微软雅黑", 9), justify=tk.LEFT).pack(anchor=tk.W)
        
        # 输入区域
        input_frame = tk.LabelFrame(igdb_win, text="🔑 输入 API 凭证", 
                                    font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        input_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        # Client ID
        id_row = tk.Frame(input_frame)
        id_row.pack(fill=tk.X, pady=(0, 5))
        tk.Label(id_row, text="Client ID:", font=("微软雅黑", 9), width=12, anchor=tk.E).pack(side=tk.LEFT)
        id_var = tk.StringVar(value=saved_id)
        id_entry = tk.Entry(id_row, textvariable=id_var, width=45, font=("微软雅黑", 9))
        id_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # Client Secret
        secret_row = tk.Frame(input_frame)
        secret_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(secret_row, text="Client Secret:", font=("微软雅黑", 9), width=12, anchor=tk.E).pack(side=tk.LEFT)
        secret_var = tk.StringVar(value=saved_secret)
        secret_entry = tk.Entry(secret_row, textvariable=secret_var, width=45, font=("微软雅黑", 9), show="•")
        secret_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # 按钮行
        btn_frame = tk.Frame(input_frame)
        btn_frame.pack(fill=tk.X)
        
        def toggle_show():
            if secret_entry.cget('show') == '•':
                secret_entry.config(show='')
                show_btn.config(text="🙈 隐藏")
            else:
                secret_entry.config(show='•')
                show_btn.config(text="👁 显示")
        
        def save_credentials():
            cid = id_var.get().strip()
            csecret = secret_var.get().strip()
            if cid and csecret:
                self._save_igdb_credentials(cid, csecret)
                status_label.config(text="🔐 当前状态：已配置 IGDB API 凭证", fg="green")
                messagebox.showinfo("保存成功", "✅ IGDB API 凭证已保存！\n\n现在可以使用「游戏类型分类」功能了。")
            else:
                messagebox.showwarning("提示", "请填写 Client ID 和 Client Secret。")
        
        def test_credentials():
            cid = id_var.get().strip()
            csecret = secret_var.get().strip()
            if not cid or not csecret:
                messagebox.showwarning("提示", "请先填写 Client ID 和 Client Secret。")
                return
            
            # 临时保存以便测试
            self._save_igdb_credentials(cid, csecret)
            
            # 测试获取令牌
            token, error = self._get_igdb_access_token(force_refresh=True)
            if error:
                messagebox.showerror("测试失败", f"❌ 无法获取访问令牌：\n\n{error}")
            else:
                messagebox.showinfo("测试成功", "✅ IGDB API 凭证有效！\n\n已成功获取访问令牌。")
                status_label.config(text="🔐 当前状态：已配置 IGDB API 凭证", fg="green")
        
        def clear_credentials():
            if messagebox.askyesno("确认清除", "确定要清除已保存的 IGDB API 凭证吗？"):
                id_var.set("")
                secret_var.set("")
                self._clear_igdb_credentials()
                status_label.config(text="⚠️ 当前状态：未配置 IGDB API 凭证", fg="orange")
                messagebox.showinfo("已清除", "IGDB API 凭证已清除。")
        
        show_btn = tk.Button(btn_frame, text="👁 显示", command=toggle_show, font=("微软雅黑", 9), width=8)
        show_btn.pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_frame, text="🔍 测试凭证", command=test_credentials, font=("微软雅黑", 9), width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="💾 保存凭证", command=save_credentials, font=("微软雅黑", 9), width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="🗑 清除凭证", command=clear_credentials, font=("微软雅黑", 9), width=12).pack(side=tk.LEFT, padx=5)
        
        # 安全提示
        tk.Label(igdb_win, text="⚠️ API 凭证包含敏感信息，请勿分享配置文件给他人", 
                 font=("微软雅黑", 8), fg="red").pack(pady=(0, 15))

    # ==================== 主界面 ====================
    def main_ui(self):
        """启动主界面（含账号选择）"""
        # 扫描账号
        self.accounts = SteamAccountScanner.scan_accounts()
        
        if not self.accounts:
            # 未找到账号，显示提示
            root = tk.Tk()
            root.title("Steam 库管理助手")
            root.resizable(False, False)
            
            tk.Label(root, text="❌ 未找到 Steam 账号", font=("微软雅黑", 14, "bold"), fg="red").pack(pady=20)
            tk.Label(root, text="请确保:\n1. Steam 已安装在默认路径\n2. 至少登录过一个 Steam 账号\n3. 账号目录中存在 cloud-storage-namespace-1.json 文件",
                     font=("微软雅黑", 10), justify=tk.LEFT).pack(padx=30, pady=10)
            
            # 手动选择路径
            def manual_select():
                path = filedialog.askopenfilename(
                    title="选择 cloud-storage-namespace-1.json 文件",
                    filetypes=[("JSON files", "*.json")]
                )
                if path and os.path.exists(path):
                    # 尝试从路径推断账号信息
                    match = re.search(r'userdata[/\\](\d+)[/\\]', path)
                    friend_code = match.group(1) if match else "unknown"
                    
                    self.accounts = [{
                        'friend_code': friend_code,
                        'userdata_path': os.path.dirname(os.path.dirname(os.path.dirname(path))),
                        'json_path': path,
                        'persona_name': f"手动选择 ({friend_code})",
                        'steam_path': "",
                    }]
                    root.destroy()
                    self._show_account_selector()
            
            tk.Button(root, text="📂 手动选择文件", command=manual_select, font=("微软雅黑", 10)).pack(pady=20)
            
            root.update_idletasks()
            cw, ch = root.winfo_reqwidth(), root.winfo_reqheight()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{cw}x{ch}+{int((sw-cw)/2)}+{int((sh-ch)/2)}")
            root.mainloop()
        elif len(self.accounts) == 1:
            # 只有一个账号，直接使用
            self.set_current_account(self.accounts[0])
            self._show_main_window()
        else:
            # 多个账号，显示选择界面
            self._show_account_selector()
    
    def _show_account_selector(self):
        """显示账号选择界面"""
        sel_root = tk.Tk()
        sel_root.title("选择 Steam 账号")
        sel_root.resizable(False, False)
        
        tk.Label(sel_root, text="🎮 检测到多个 Steam 账号", font=("微软雅黑", 12, "bold")).pack(pady=(20, 10))
        tk.Label(sel_root, text="请选择要管理的账号：", font=("微软雅黑", 10)).pack()
        
        list_frame = tk.Frame(sel_root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        listbox = tk.Listbox(list_frame, width=60, height=10, font=("微软雅黑", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        
        for acc in self.accounts:
            listbox.insert(tk.END, f"{acc['persona_name']} (好友代码: {acc['friend_code']})")
        
        if self.accounts:
            listbox.selection_set(0)
        
        def on_select():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择一个账号。")
                return
            self.set_current_account(self.accounts[selected[0]])
            sel_root.destroy()
            self._show_main_window()
        
        tk.Button(sel_root, text="✅ 确认选择", command=on_select, font=("微软雅黑", 10), width=15).pack(pady=15)
        
        sel_root.update_idletasks()
        cw, ch = sel_root.winfo_reqwidth(), sel_root.winfo_reqheight()
        sw, sh = sel_root.winfo_screenwidth(), sel_root.winfo_screenheight()
        sel_root.geometry(f"{cw}x{ch}+{int((sw-cw)/2)}+{int((sh-ch)/2)}")
        sel_root.mainloop()
    
    def _show_main_window(self):
        """显示主功能窗口"""
        root = tk.Tk()
        root.title("Steam 库管理助手")
        root.resizable(False, False)
        
        # ====== 待保存更改追踪 ======
        self._pending_data = None       # 待保存的 data 对象
        self._has_pending_changes = False
        self._original_col_ids = set()  # 导入前已有的收藏夹 ID，用于标红新增项
        
        def mark_dirty(data):
            """标记有未保存的更改"""
            self._pending_data = data
            self._has_pending_changes = True
            save_btn.config(state=tk.NORMAL)
            save_indicator.config(text="⚠️ 有未保存的更改", fg="orange")
        
        def commit_save():
            """储存更改：备份当前分类，写入新分类"""
            if not self._has_pending_changes or self._pending_data is None:
                messagebox.showinfo("提示", "没有需要保存的更改。")
                return
            result = self.save_json(self._pending_data, backup_description="储存收藏夹更改")
            if result:
                self._has_pending_changes = False
                self._pending_data = None
                self._original_col_ids.clear()
                save_btn.config(state=tk.DISABLED)
                save_indicator.config(text="✅ 所有更改已保存", fg="green")
                refresh_categories()
        
        def on_close():
            """关闭窗口时检查未保存更改"""
            if self._has_pending_changes:
                ans = messagebox.askyesnocancel("未保存的更改", "您有未保存的更改。\n\n是否在退出前保存？")
                if ans is None:  # 取消
                    return
                if ans:  # 是：保存后退出
                    commit_save()
            root.destroy()
        
        root.protocol("WM_DELETE_WINDOW", on_close)
        
        # ====== 当前账号信息（高亮显示） ======
        account_frame = tk.Frame(root, bg="#4a90d9", pady=10)
        account_frame.pack(fill=tk.X)
        
        acc_info = f"👤 {self.current_account['persona_name']}  |  好友代码: {self.current_account['friend_code']}"
        tk.Label(account_frame, text=acc_info, font=("微软雅黑", 11, "bold"), bg="#4a90d9", fg="white").pack(side=tk.LEFT, padx=15)
        
        if len(self.accounts) > 1:
            def switch_account():
                if self._has_pending_changes:
                    ans = messagebox.askyesnocancel("未保存的更改", "您有未保存的更改。\n\n是否在切换账号前保存？")
                    if ans is None:
                        return
                    if ans:
                        commit_save()
                root.destroy()
                self._show_account_selector()
            tk.Button(account_frame, text="🔄 切换账号", command=switch_account, font=("微软雅黑", 9)).pack(side=tk.RIGHT, padx=15)
        
        # ====== 主内容区（左侧收藏夹列表 + 右侧功能控制区） ======
        main_container = tk.Frame(root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # ====== 左侧：收藏夹列表面板（仿 Steam 侧边栏） ======
        left_panel = tk.Frame(main_container, bg="#f0f0f0", padx=10, pady=10)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0), pady=10)
        
        # 标题行：📂 当前收藏夹 + 💾 备份管理按钮 + 🔄 刷新按钮
        title_row = tk.Frame(left_panel, bg="#f0f0f0")
        title_row.pack(fill=tk.X)
        tk.Label(title_row, text="📂 当前收藏夹", font=("微软雅黑", 11, "bold"), bg="#f0f0f0").pack(side=tk.LEFT)
        ttk.Button(title_row, text="💾 备份", width=7, command=self.open_backup_manager_ui).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(title_row, text="🔄", width=3, command=lambda: refresh_categories()).pack(side=tk.RIGHT, padx=(5, 0))
        
        tk.Label(left_panel, text="（按字母顺序排列）", font=("微软雅黑", 9), fg="#666666", bg="#f0f0f0").pack(anchor=tk.W)
        
        # 全选控制行
        select_ctrl_row = tk.Frame(left_panel, bg="#f0f0f0")
        select_ctrl_row.pack(fill=tk.X, pady=(5, 0))
        select_all_var = tk.BooleanVar(value=False)
        
        def toggle_select_all():
            val = select_all_var.get()
            for var in checkbox_vars:
                var.set(val)
        
        tk.Checkbutton(select_ctrl_row, text="全选", variable=select_all_var, command=toggle_select_all,
                        bg="#f0f0f0", font=("微软雅黑", 9)).pack(side=tk.LEFT)
        
        # 选中计数
        selection_count_label = tk.Label(select_ctrl_row, text="", font=("微软雅黑", 8), fg="#888888", bg="#f0f0f0")
        selection_count_label.pack(side=tk.RIGHT)
        
        # 分类列表框架
        list_container = tk.Frame(left_panel, bg="#f0f0f0")
        list_container.pack(fill=tk.BOTH, expand=True, pady=(5, 5))
        
        # 使用 Canvas + Frame 实现滚动
        canvas = tk.Canvas(list_container, bg="#ffffff", width=220, height=380, highlightthickness=1, highlightbackground="#cccccc")
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#ffffff")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 让 scrollable_frame 宽度始终跟随 canvas 宽度，确保 fill=tk.X 和 side=tk.RIGHT 生效
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 鼠标滚轮绑定（兼容 macOS 触控板）
        def _on_mousewheel(event):
            if platform.system() == "Darwin":
                canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        # Linux 滚轮支持
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-3, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(3, "units"))
        
        # 收藏夹数据和复选框变量
        checkbox_vars = []
        current_collections = []
        
        def update_selection_count(*args):
            count = sum(1 for v in checkbox_vars if v.get())
            total = len(checkbox_vars)
            if count > 0:
                selection_count_label.config(text=f"已选 {count}/{total}")
            else:
                selection_count_label.config(text="")
            # 同步全选按钮状态
            if total > 0 and count == total:
                select_all_var.set(True)
            else:
                select_all_var.set(False)
        
        # 刷新分类列表的函数
        def refresh_categories():
            nonlocal checkbox_vars, current_collections
            # 清空现有内容
            for widget in scrollable_frame.winfo_children():
                widget.destroy()
            checkbox_vars.clear()
            current_collections.clear()
            select_all_var.set(False)
            selection_count_label.config(text="")
            
            # 有未保存的更改时，从 _pending_data 读取；否则从文件读取
            if self._has_pending_changes and self._pending_data is not None:
                data = self._pending_data
            else:
                data = self.load_json()
            if data is None:
                tk.Label(scrollable_frame, text="❌ 无法读取配置文件", font=("微软雅黑", 9), fg="red", bg="#ffffff", padx=10, pady=5).pack(anchor=tk.W)
                return
            
            collections = self._get_all_collections_ordered(data)
            current_collections.extend(collections)
            
            if not collections:
                empty_label = tk.Label(scrollable_frame, text="所有分类为空", font=("微软雅黑", 10), fg="#999999", bg="#ffffff", padx=10, pady=20)
                empty_label.pack(anchor=tk.CENTER, expand=True)
            else:
                for i, col in enumerate(collections):
                    # 创建每个分类的显示项
                    item_frame = tk.Frame(scrollable_frame, bg="#ffffff")
                    item_frame.pack(fill=tk.X, padx=2, pady=1)
                    
                    # 复选框
                    var = tk.BooleanVar(value=False)
                    var.trace_add("write", update_selection_count)
                    checkbox_vars.append(var)
                    
                    cb = tk.Checkbutton(item_frame, variable=var, bg="#ffffff", activebackground="#ffffff")
                    cb.pack(side=tk.LEFT)
                    
                    # 分类类型图标
                    icon = "📁" if not col['is_dynamic'] else "🔍"
                    
                    # 判定颜色：
                    #   红色 = 有未保存更改 且 该收藏夹是新增的（不在原始 ID 集合中）
                    #   蓝色 = 已保存，但名称尾部仍带有云同步后缀
                    #   默认黑色
                    col_id = col.get("id", "")
                    col_name = col.get("name", "")
                    is_new_unsaved = (self._has_pending_changes
                                      and self._original_col_ids
                                      and col_id not in self._original_col_ids)
                    has_sync_suffix = col_name.endswith(self.induce_suffix)
                    
                    if is_new_unsaved:
                        name_fg = "#cc0000"   # 红色：未保存的新增
                    elif has_sync_suffix and not self._has_pending_changes:
                        name_fg = "#1a6dcc"   # 蓝色：已保存但仍带后缀
                    else:
                        name_fg = "#000000"   # 默认黑色
                    
                    # 分类名称
                    name_text = f"{icon} {col_name}"
                    if len(name_text) > 20:
                        name_text = name_text[:18] + "..."
                    
                    name_label = tk.Label(item_frame, text=name_text, font=("微软雅黑", 9),
                                          bg="#ffffff", fg=name_fg, anchor=tk.W)
                    name_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    # 点击名称也可以切换选中状态
                    name_label.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))
                    
                    # 蓝色项添加提示：鼠标悬停时显示 tooltip
                    if has_sync_suffix and not self._has_pending_changes:
                        tip_text = "请在 Steam 内删去名称后缀以触发云同步"
                        name_label.bind("<Enter>", lambda e, lbl=name_label, t=tip_text: lbl.config(cursor="question_arrow"))
                        name_label.bind("<Leave>", lambda e, lbl=name_label: lbl.config(cursor=""))
                    
                    # 游戏数量（仅静态收藏夹显示数量，动态收藏夹显示额外添加数）
                    if not col['is_dynamic']:
                        count_label = tk.Label(item_frame, text=f"({len(col['added'])})", font=("微软雅黑", 8), fg="#888888", bg="#ffffff")
                        count_label.pack(side=tk.RIGHT)
                    elif col.get('added'):
                        count_label = tk.Label(item_frame, text=f"(+{len(col['added'])})", font=("微软雅黑", 8), fg="#aa88cc", bg="#ffffff")
                        count_label.pack(side=tk.RIGHT)
            
            # 蓝色后缀提示（保存后、有带后缀的收藏夹时显示）
            if not self._has_pending_changes:
                has_any_suffix = any(c.get("name", "").endswith(self.induce_suffix) for c in collections)
                if has_any_suffix:
                    save_indicator.config(text="🔵 蓝色项：请在 Steam 内删去后缀", fg="#1a6dcc")
            
            # 更新滚动区域
            scrollable_frame.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 获取当前选中的收藏夹
        def get_selected_collections():
            selected = []
            for i, var in enumerate(checkbox_vars):
                if var.get() and i < len(current_collections):
                    selected.append(current_collections[i])
            return selected
        
        # 暴露给右侧按钮方法使用
        self._ui_get_selected = get_selected_collections
        self._ui_mark_dirty = mark_dirty
        self._ui_refresh = refresh_categories
        
        # ====== 左侧底部：储存更改按钮 ======
        left_btn_frame = tk.Frame(left_panel, bg="#f0f0f0")
        left_btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        # 储存更改按钮 + 状态指示
        save_row = tk.Frame(left_btn_frame, bg="#f0f0f0")
        save_row.pack(fill=tk.X, pady=(2, 0))
        save_btn = ttk.Button(save_row, text="💾 储存更改", width=23, command=commit_save, state=tk.DISABLED)
        save_btn.pack(fill=tk.X)
        
        save_indicator = tk.Label(left_panel, text="", font=("微软雅黑", 8), bg="#f0f0f0")
        save_indicator.pack(anchor=tk.W)
        
        # 初始加载分类列表
        refresh_categories()
        
        # ====== 右侧：功能控制区 ======
        right_panel = tk.Frame(main_container)
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # ====== 操作守则 ======
        instruction_frame = tk.Frame(right_panel, pady=15, padx=35)
        instruction_frame.pack(fill=tk.X)
        
        t_top = tk.Text(instruction_frame, font=("微软雅黑", 10), height=8, bg=root.cget("bg"), relief=tk.FLAT, wrap=tk.WORD)
        t_top.tag_config("red", foreground="red", font=("微软雅黑", 10, "bold"))
        t_top.tag_config("green", foreground="green", font=("微软雅黑", 10, "bold"))
        
        t_top.insert(tk.END, "✅ 已自动定位到账号的收藏夹配置文件\n\n", "green")
        t_top.insert(tk.END, "操作守则：\n一、导入前请")
        t_top.insert(tk.END, "关闭", "red")
        t_top.insert(tk.END, " Steam；\n二、导入或更新后需点击左侧")
        t_top.insert(tk.END, "「💾 储存更改」", "red")
        t_top.insert(tk.END, "才会写入文件，程序会自动创建备份；\n三、为了上传云端，您必须")
        t_top.insert(tk.END, "在 Steam 内手动修改", "red")
        t_top.insert(tk.END, "新收藏，如删去自动添加的名称后缀等。")
        t_top.config(state=tk.DISABLED)
        t_top.pack(fill=tk.X)
        
        style = ttk.Style()
        style.configure("TButton", font=("微软雅黑", 11), padding=8)
        
        # ====== 功能按钮 ======
        row1_frame = tk.Frame(right_panel, padx=35)
        row1_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(row1_frame, text="📁 批量导入", width=15, command=self.import_from_txt).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(row1_frame, text="📤 批量导出", width=15, command=self.export_static_collection).pack(side=tk.LEFT, padx=10)
        ttk.Button(row1_frame, text="🔄 批量更新", width=15, command=self.update_static_collection).pack(side=tk.LEFT, padx=10)
        
        d_row1 = tk.Text(right_panel, font=("微软雅黑", 9), height=5, bg=root.cget("bg"), relief=tk.FLAT, padx=35)
        d_row1.tag_config("red", foreground="red")
        d_row1.insert(tk.END, "• 导入：支持 ")
        d_row1.insert(tk.END, "TXT（AppID 列表）", "red")
        d_row1.insert(tk.END, " 或 ")
        d_row1.insert(tk.END, "JSON（结构化收藏夹）", "red")
        d_row1.insert(tk.END, "。\n• 导出：需先在左侧勾选收藏夹，支持合并 TXT / 多个 TXT / JSON 三种格式。\n")
        d_row1.insert(tk.END, "• 更新：支持增量更新（追加 + 差异记录）或替换更新（直接覆盖）两种模式。")
        d_row1.config(state=tk.DISABLED)
        d_row1.pack(fill=tk.X, pady=5)

        ttk.Button(right_panel, text="👥 批量同步 Steam 用户游戏库", width=53, command=self.open_friend_sync_ui).pack(pady=(5,0))
        d4 = tk.Text(right_panel, font=("微软雅黑", 9), height=2, bg=root.cget("bg"), relief=tk.FLAT, padx=35)
        d4.tag_config("red", foreground="red")
        d4.insert(tk.END, "• 对方必须")
        d4.insert(tk.END, "公开", "red")
        d4.insert(tk.END, "了库。好友代码可在其 SteamDB 页面获取。")
        d4.config(state=tk.DISABLED)
        d4.pack(fill=tk.X, pady=5)

        # ====== 两个并列的来源按钮（居中） ======
        source_row = tk.Frame(right_panel)
        source_row.pack(fill=tk.X, pady=(5, 0))
        source_inner = tk.Frame(source_row)
        source_inner.pack(anchor=tk.CENTER)
        ttk.Button(source_inner, text="⭐ 从推荐来源获取", width=25, command=self.personal_recommend_ui).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(source_inner, text="🌐 从其他来源获取", width=25, command=self.open_source_selection).pack(side=tk.LEFT)
        
        d5 = tk.Text(right_panel, font=("微软雅黑", 9), height=4, bg=root.cget("bg"), relief=tk.FLAT, padx=35)
        d5.tag_config("purple", foreground="#7c3aed")
        d5.tag_config("blue", foreground="#5b9bd5")
        d5.insert(tk.END, "• 推荐来源：")
        d5.insert(tk.END, "Steam250 排行榜", "purple")
        d5.insert(tk.END, " + ")
        d5.insert(tk.END, "精选鉴赏家", "purple")
        d5.insert(tk.END, " + ")
        d5.insert(tk.END, "游戏类型分类（IGDB）", "purple")
        d5.insert(tk.END, "\n")
        d5.insert(tk.END, "• 其他来源：")
        d5.insert(tk.END, "Steam 列表页面", "blue")
        d5.insert(tk.END, "（鉴赏家/发行商）、")
        d5.insert(tk.END, "SteamDB", "blue")
        d5.config(state=tk.DISABLED)
        d5.pack(fill=tk.X, pady=(5, 10))
        
        # ====== Cookie 和 IGDB API 并排 ======
        config_row = tk.Frame(right_panel)
        config_row.pack(fill=tk.X, pady=(5, 0))
        config_inner = tk.Frame(config_row)
        config_inner.pack(anchor=tk.CENTER)
        ttk.Button(config_inner, text="🔑 管理 Cookie", width=25, command=self.open_cookie_manager_ui).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(config_inner, text="🎮 管理 IGDB API", width=25, command=self.open_igdb_credentials_ui).pack(side=tk.LEFT)
        
        d_config = tk.Text(right_panel, font=("微软雅黑", 9), height=3, bg=root.cget("bg"), relief=tk.FLAT, padx=35)
        d_config.tag_config("orange", foreground="orange")
        d_config.tag_config("purple", foreground="#7c3aed")
        d_config.insert(tk.END, "• Cookie：获取")
        d_config.insert(tk.END, "完整的鉴赏家列表", "orange")
        d_config.insert(tk.END, "（含各种内容）。\n")
        d_config.insert(tk.END, "• IGDB API：按")
        d_config.insert(tk.END, "游戏类型分类", "purple")
        d_config.insert(tk.END, "获取游戏列表。")
        d_config.config(state=tk.DISABLED)
        d_config.pack(fill=tk.X, pady=(5, 20))
        
        root.update_idletasks()
        cw, ch = root.winfo_reqwidth(), root.winfo_reqheight()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{cw}x{ch}+{int((sw-cw)/2)}+{int((sh-ch)/2)}")
        root.mainloop()


if __name__ == "__main__":
    app = SteamToolbox()
    app.main_ui()
