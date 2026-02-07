import os
import platform
import re


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
