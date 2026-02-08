import os
import platform
import re
from typing import Optional, Self, List

import vdf


class SteamAccount:
    """Steam 账号信息类

    Attributes:
        steam_id3_dir (str): Steam 用户数据目录（userdata\\steam_id3）
        storage_path (str): cloud-storage-namespace-1.json 文件路径
        steam_id3 (int): Steam ID3 号码 / Friend Code
        persona_name (str): 用户昵称
    """

    def __init__(self, steam_id3_dir: str, storage_path: str, steam_id3: int, persona_name: str):
        """SteamAccount 实例"""
        self.steam_id3_dir = steam_id3_dir
        self.storage_path = storage_path
        self.steam_id3 = steam_id3
        self.persona_name = persona_name


    def __hash__(self):
        return self.steam_id3


    def __repr__(self):
        return f"<SteamAccount {self.persona_name} ({self.steam_id3})>"

    @staticmethod
    def _get_persona_name(userdata_path: str, friend_code: str) -> str:
        """尝试从配置文件获取用户昵称"""
        # 尝试从 localconfig.vdf 获取
        localconfig_path = os.path.join(userdata_path, "config", "localconfig.vdf")
        if os.path.exists(localconfig_path):
            try:
                with open(localconfig_path, 'r', encoding='utf-8', errors='ignore') as f:
                    localconfig = vdf.load(f)
                    # print(localconfig)

                    persona_name = localconfig.get('UserLocalConfigStore', {}).get('friends', {}).get('PersonaName', '')
                    if persona_name:
                        return persona_name
            except OSError: # FileNotFoundError, PermissionError, etc. belongs to OSError ( general IO errors )
                pass

        return f"Steam 用户 {friend_code}"

    @classmethod
    def from_path(cls, steam_id3_dir: str) -> Optional[Self]:
        """从已确定的单个 userdata\\steam_id3 文件夹创建 SteamAccount 实例"""
        friend_code = os.path.basename(steam_id3_dir)
        if not friend_code.isdigit():
            return None

        storage_path = os.path.join(steam_id3_dir, "config", "cloudstorage", "cloud-storage-namespace-1.json")
        if not os.path.exists(storage_path):
            return None

        # 尝试获取用户名（从 localconfig.vdf）
        persona_name = cls._get_persona_name(steam_id3_dir, friend_code)

        return cls(
            steam_id3_dir=steam_id3_dir,
            storage_path=storage_path,
            steam_id3=int(friend_code),
            persona_name=persona_name
        )

    @classmethod
    def from_storage_json(cls, storage_json_path: str) -> Optional[Self]:
        """从 cloud-storage-namespace-1.json 文件创建 SteamAccount 实例"""
        if not os.path.exists(storage_json_path):
            return None

        match = re.search(r'userdata[\\/](\d+)[\\/]', storage_json_path)
        if not match:
            return None

        steam_id3 = match.group(1)
        steam_id3_dir = os.path.join(os.path.dirname(os.path.dirname(storage_json_path)), steam_id3)

        # 尝试获取用户名（从 localconfig.vdf）
        persona_name = cls._get_persona_name(steam_id3_dir, steam_id3)

        return cls(
            steam_id3_dir=steam_id3_dir,
            storage_path=storage_json_path,
            steam_id3=int(steam_id3),
            persona_name=persona_name
        )

class SteamDiscovery:
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
            except OSError:
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
            except ImportError | OSError:
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
    def scan_accounts() -> List[SteamAccount]:
        """扫描所有 Steam 账号

        Returns:
            list of dict: [{'friend_code': '123456', 'userdata_path': '/path/to/userdata/123456',
                           'json_path': '/path/to/cloud-storage-namespace-1.json', 'persona_name': '...'}]
        """
        accounts = set()
        steam_paths = SteamDiscovery.get_steam_paths()

        for steam_path in steam_paths:
            users_path = os.path.join(steam_path, "userdata")
            if not os.path.exists(users_path):
                continue

            # 遍历 userdata 下的所有文件夹（每个文件夹对应一个账号）
            try:
                for entry in os.scandir(users_path):
                    if not os.path.isdir(entry.path):
                        continue
                    account = SteamAccount.from_path(entry.path)
                    if account:
                        accounts.add(account) # since we use SteamID3 as hash, auto deduplication
            except PermissionError:
                continue

        return list(accounts)
