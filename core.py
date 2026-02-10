import base64
import json
import os
import re
import secrets
import shutil
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime
from json import JSONDecodeError
from tkinter import messagebox

from account_manager import SteamAccount
from local_storage import BackupManager


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """禁止自动重定向，以便检测 302 等重定向响应"""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # 返回 None 表示不跟随重定向


class SteamToolboxCore:
    """核心类，UI 无关"""

    def __init__(self, account: SteamAccount):
        self.current_account: SteamAccount = account  # 当前选中的账号

        # 这些属性会在选择账号后设置
        self.backup_manager = BackupManager(self.current_account.storage_path)  # 备份管理器

        # 数据目录（统一存放配置和缓存）
        self.data_dir = os.path.join(os.path.expanduser("~"), ".steam_toolbox")
        os.makedirs(self.data_dir, exist_ok=True)
        self.global_config_path = os.path.join(self.data_dir, "config.json")

        # 迁移旧版文件（从主目录散落文件 → 统一目录）
        self.migrate_old_files()

        self.induce_suffix = "(删除这段字以触发云同步)"
        self.disclaimer = f"\n\n(若其中包含未拥有的游戏、重复条目或是 DLC，会导致 Steam 收藏夹内显示的数目偏少。)"

        # SSL 上下文（解决 macOS 证书问题）
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE


    def migrate_old_files(self):
        """将旧版散落在主目录的文件迁移到统一数据目录"""
        home = os.path.expanduser("~")
        migrations = [
            (".steam_toolbox_config.json", "config.json"),
            (".steam_toolbox_igdb_cache.json", "igdb_cache.json"),
        ]
        for old_name, new_name in migrations:
            old_path = os.path.join(home, old_name)
            new_path = os.path.join(self.data_dir, new_name)
            if os.path.exists(old_path) and not os.path.exists(new_path):
                try:
                    shutil.move(old_path, new_path)
                except:
                    pass

    @staticmethod
    def next_version(data):
        """扫描全部条目，返回下一个可用的全局版本号（字符串）"""
        max_ver = 0
        for entry in data:
            try:
                v = int(entry[1].get("version", "0"))
                if v > max_ver: max_ver = v
            except (ValueError, IndexError, TypeError):
                continue
        return str(max_ver + 1)

    def add_static_collection(self, data, name, app_ids):
        col_id = f"uc-{secrets.token_hex(6)}"
        storage_key = f"user-collections.{col_id}"
        val_obj = {"id": col_id, "name": name + self.induce_suffix, "added": app_ids, "removed": []}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()),
                                   "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')),
                                   "version": self.next_version(data),
                                   "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}]
        data.append(new_entry)

    def load_config(self):
        """加载全局配置文件"""
        if os.path.exists(self.global_config_path):
            try:
                with open(self.global_config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_config(self, config):
        """保存全局配置文件"""
        try:
            with open(self.global_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass

    def get_saved_cookie(self):
        """获取已保存的 Cookie（简单混淆存储）"""
        config = self.load_config()
        encoded = config.get("steam_cookie_encoded", "")
        if encoded:
            try:
                return base64.b64decode(encoded.encode()).decode()
            except:
                pass
        return ""

    def save_cookie(self, cookie_value):
        """保存 Cookie（简单混淆存储）"""
        config = self.load_config()
        if cookie_value:
            config["steam_cookie_encoded"] = base64.b64encode(cookie_value.encode()).decode()
        else:
            config.pop("steam_cookie_encoded", None)
        self.save_config(config)

    def clear_saved_cookie(self):
        """清除已保存的 Cookie"""
        config = self.load_config()
        config.pop("steam_cookie_encoded", None)
        self.save_config(config)

    # ==================== IGDB 维度定义 ====================
    IGDB_DIMENSIONS = {
        "genres":              {"endpoint": "/v4/genres",              "game_field": "genres",              "icon": "🏷️", "name": "游戏类型",  "label": "🏷️ 类型"},
        "themes":              {"endpoint": "/v4/themes",              "game_field": "themes",              "icon": "🎭", "name": "游戏主题",  "label": "🎭 主题"},
        "keywords":            {"endpoint": "/v4/keywords",            "game_field": "keywords",            "icon": "🔑", "name": "关键词",    "label": "🔑 关键词"},
        "game_modes":          {"endpoint": "/v4/game_modes",          "game_field": "game_modes",          "icon": "🎮", "name": "游戏模式",  "label": "🎮 模式"},
        "player_perspectives": {"endpoint": "/v4/player_perspectives", "game_field": "player_perspectives", "icon": "👁",  "name": "视角",      "label": "👁 视角"},
        "franchises":          {"endpoint": "/v4/franchises",          "game_field": "franchises",          "icon": "📚", "name": "游戏系列",  "label": "📚 系列"},
    }

    # IGDB 网站 URL 路径映射（用于生成浏览链接）
    IGDB_URL_PATHS = {
        "genres": "genres",
        "themes": "themes",
        "keywords": "categories",
        "game_modes": "game_modes",
        "player_perspectives": "player_perspectives",
        "franchises": "franchises",
    }

    # 所有需要在 step2 批量查询的 game 字段（逗号拼接）
    IGDB_GAME_FIELDS = ",".join(dim["game_field"] for dim in IGDB_DIMENSIONS.values())

    # ==================== IGDB API 相关函数 ====================
    def get_igdb_credentials(self):
        """获取已保存的 IGDB API 凭证"""
        config = self.load_config()
        client_id = config.get("igdb_client_id", "")
        encoded_secret = config.get("igdb_client_secret_encoded", "")
        client_secret = ""
        if encoded_secret:
            try:
                client_secret = base64.b64decode(encoded_secret.encode()).decode()
            except:
                pass
        return client_id, client_secret

    def save_igdb_credentials(self, client_id, client_secret):
        """保存 IGDB API 凭证（Client Secret 简单混淆存储）"""
        config = self.load_config()
        config["igdb_client_id"] = client_id
        if client_secret:
            config["igdb_client_secret_encoded"] = base64.b64encode(client_secret.encode()).decode()
        else:
            config.pop("igdb_client_secret_encoded", None)
        self.save_config(config)

    def clear_igdb_credentials(self):
        """清除 IGDB API 凭证"""
        config = self.load_config()
        config.pop("igdb_client_id", None)
        config.pop("igdb_client_secret_encoded", None)
        config.pop("igdb_access_token", None)
        config.pop("igdb_token_expires_at", None)
        self.save_config(config)

    def get_igdb_access_token(self, force_refresh=False):
        """获取 IGDB API 的访问令牌（带缓存）"""
        client_id, client_secret = self.get_igdb_credentials()
        if not client_id or not client_secret:
            return None, "未配置 IGDB API 凭证"

        config = self.load_config()
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
            self.save_config(config)

            return access_token, None

        except urllib.error.HTTPError as e:
            return None, f"HTTP 错误 {e.code}：获取 IGDB 令牌失败"
        except urllib.error.URLError as e:
            return None, f"网络错误：{str(e.reason)}"
        except Exception as e:
            return None, f"获取令牌失败：{str(e)}"

    def fetch_igdb_dimension_list(self, dimension, progress_callback=None):
        """获取 IGDB 某个维度的条目列表（名称+ID）

        对于小维度（genres/themes/game_modes/player_perspectives）：全量拉取。
        对于大维度（keywords/franchises）：只拉取本地缓存中有数据的条目。

        Args:
            dimension: 维度名称，如 'genres', 'themes', 'keywords', ...
            progress_callback: 进度回调

        Returns:
            (list_of_items, error): items = [{'id': ..., 'name': ...}, ...]
        """
        dim_info = self.IGDB_DIMENSIONS.get(dimension)
        if not dim_info:
            return [], f"未知维度: {dimension}"

        client_id, _ = self.get_igdb_credentials()
        access_token, error = self.get_igdb_access_token()
        if error:
            return [], error

        if progress_callback:
            progress_callback(0, 0, f"正在获取{dim_info['name']}列表...", "")

        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

        url = f"https://api.igdb.com{dim_info['endpoint']}"

        # 大维度（keywords/franchises）：只查缓存中存在的 ID，避免拉取几万条无用数据
        is_large = dimension in ("keywords", "franchises")

        if is_large:
            cache = self.load_igdb_cache()
            dim_cache = cache.get(dimension, {})
            cached_ids = [k for k in dim_cache.keys() if isinstance(dim_cache.get(k), dict) and "steam_ids" in dim_cache[k]]
            if not cached_ids:
                return [], None

            all_items = []
            batch_size = 500
            total = len(cached_ids)
            for i in range(0, total, batch_size):
                batch = cached_ids[i:i + batch_size]
                ids_str = ",".join(batch)
                body = f"fields id,name,slug; where id = ({ids_str}); limit {batch_size};"
                try:
                    req = urllib.request.Request(url, data=body.encode('utf-8'), headers=headers, method='POST')
                    with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                        batch_items = json.loads(resp.read().decode('utf-8'))
                        all_items.extend(batch_items)
                except urllib.error.HTTPError as e:
                    return [], f"HTTP 错误 {e.code}：获取{dim_info['name']}列表失败"
                except urllib.error.URLError as e:
                    return [], f"网络错误：{str(e.reason)}"
                except Exception as e:
                    return [], f"获取失败：{str(e)}"

                if progress_callback:
                    progress_callback(min(i + batch_size, total), total,
                                      f"正在获取{dim_info['name']}名称...",
                                      f"{len(all_items)}/{total}")
                time.sleep(0.28)
        else:
            # 小维度：一次性全量拉取
            all_items = []
            offset = 0
            limit = 500
            while True:
                body = f"fields id,name,slug; limit {limit}; offset {offset}; sort name asc;"
                try:
                    req = urllib.request.Request(url, data=body.encode('utf-8'), headers=headers, method='POST')
                    with urllib.request.urlopen(req, timeout=30, context=self.ssl_context) as resp:
                        batch = json.loads(resp.read().decode('utf-8'))
                except urllib.error.HTTPError as e:
                    return [], f"HTTP 错误 {e.code}：获取{dim_info['name']}列表失败"
                except urllib.error.URLError as e:
                    return [], f"网络错误：{str(e.reason)}"
                except Exception as e:
                    return [], f"获取失败：{str(e)}"

                if not batch:
                    break
                all_items.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
                time.sleep(0.28)

        all_items.sort(key=lambda x: x.get('name', ''))
        return all_items, None

    def fetch_igdb_genres(self, progress_callback=None):
        """获取 IGDB 游戏类型列表（向后兼容）"""
        return self.fetch_igdb_dimension_list("genres", progress_callback)

    # ==================== IGDB 本地缓存 ====================

    IGDB_CACHE_EXPIRY_DAYS = 7  # 缓存有效期（天）

    def get_igdb_cache_path(self):
        """获取 IGDB 缓存文件路径"""
        return os.path.join(self.data_dir, "igdb_cache.json")

    def load_igdb_cache(self):
        """加载 IGDB 缓存"""
        path = self.get_igdb_cache_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_igdb_cache(self, cache):
        """保存 IGDB 缓存"""
        path = self.get_igdb_cache_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(cache, f, ensure_ascii=False)
        except:
            pass

    def get_igdb_dimension_cache(self, dimension, item_id):
        """获取某个维度下某个条目的缓存数据

        Args:
            dimension: 维度名称，如 'genres', 'themes', 'keywords', ...
            item_id: 条目 ID

        Returns:
            (steam_ids, cached_at_timestamp) 或 (None, None)
        """
        cache = self.load_igdb_cache()
        dim_data = cache.get(dimension, {})
        item_key = str(item_id)
        if item_key in dim_data:
            entry = dim_data[item_key]
            return entry.get("steam_ids", []), entry.get("cached_at", 0)
        return None, None

    def get_igdb_genre_cache(self, genre_id):
        """获取某个类型的缓存数据（向后兼容）"""
        return self.get_igdb_dimension_cache("genres", genre_id)

    def set_igdb_dimension_cache(self, dimension, item_id, steam_ids):
        """写入某个维度下某个条目的缓存数据"""
        cache = self.load_igdb_cache()
        if dimension not in cache:
            cache[dimension] = {}
        cache[dimension][str(item_id)] = {
            "steam_ids": steam_ids,
            "cached_at": time.time(),
        }
        self.save_igdb_cache(cache)

    def set_igdb_genre_cache(self, genre_id, steam_ids):
        """写入某个类型的缓存数据（向后兼容）"""
        self.set_igdb_dimension_cache("genres", genre_id, steam_ids)

    def is_igdb_cache_valid(self, cached_at):
        """判断缓存是否仍然有效"""
        if not cached_at:
            return False
        age_seconds = time.time() - cached_at
        return age_seconds < self.IGDB_CACHE_EXPIRY_DAYS * 86400

    def get_igdb_dimension_game_counts(self, dimension):
        """获取某维度下各条目的 Steam 游戏数量（从本地缓存读取）

        Args:
            dimension: 维度名称

        Returns:
            dict: {item_id(int): count(int)}，无缓存则返回空字典
        """
        cache = self.load_igdb_cache()
        dim_data = cache.get(dimension, {})
        if not isinstance(dim_data, dict):
            return {}
        result = {}
        for item_key, entry in dim_data.items():
            if isinstance(entry, dict) and "steam_ids" in entry:
                try:
                    result[int(item_key)] = len(entry["steam_ids"])
                except (ValueError, TypeError):
                    pass
        return result

    def get_igdb_cache_summary(self):
        """获取缓存摘要信息，用于 UI 显示

        Returns:
            dict: {'dimensions': {dim: {'count': int, 'games': int}}, 'total_steam_games': int,
                   'newest_at': float, 'is_full_dump': bool}
                  如果无缓存则返回 None
        """
        cache = self.load_igdb_cache()
        if not cache:
            return None

        meta = cache.get("_meta", {})
        is_full_dump = meta.get("type") == "full_dump"

        # 新格式：按维度分区
        dim_stats = {}
        all_timestamps = []
        total_items = 0

        for dim_name in self.IGDB_DIMENSIONS:
            dim_data = cache.get(dim_name, {})
            if not isinstance(dim_data, dict):
                continue
            count = len(dim_data)
            games = sum(len(entry.get("steam_ids", [])) for entry in dim_data.values() if isinstance(entry, dict))
            timestamps = [entry.get("cached_at", 0) for entry in dim_data.values()
                          if isinstance(entry, dict) and entry.get("cached_at")]
            if count > 0:
                dim_stats[dim_name] = {'count': count, 'games': games}
                total_items += count
                all_timestamps.extend(timestamps)

        # 兼容旧格式（无维度分区，genre_id 直接在顶层）
        if not dim_stats:
            old_entries = {k: v for k, v in cache.items() if k != "_meta" and isinstance(v, dict) and "steam_ids" in v}
            if old_entries:
                total_genres = len(old_entries)
                total_games = sum(len(entry.get("steam_ids", [])) for entry in old_entries.values())
                timestamps = [entry.get("cached_at", 0) for entry in old_entries.values() if entry.get("cached_at")]
                if not timestamps:
                    return None
                return {
                    'total_genres': total_genres,
                    'total_games': total_games,
                    'oldest_at': min(timestamps),
                    'newest_at': max(timestamps),
                    'is_full_dump': is_full_dump,
                    'total_steam_games': meta.get("total_steam_games", 0),
                    'dimensions': {'genres': {'count': total_genres, 'games': total_games}},
                }

        if not all_timestamps:
            return None

        return {
            'dimensions': dim_stats,
            'total_items': total_items,
            'oldest_at': min(all_timestamps) if all_timestamps else 0,
            'newest_at': max(all_timestamps) if all_timestamps else 0,
            'is_full_dump': is_full_dump,
            'total_steam_games': meta.get("total_steam_games", 0),
            # 向后兼容字段
            'total_genres': dim_stats.get('genres', {}).get('count', 0),
            'total_games': sum(d['games'] for d in dim_stats.values()),
        }

    def clear_igdb_genre_cache(self):
        """清除所有 IGDB 缓存"""
        path = self.get_igdb_cache_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass

    # ==================== IGDB API 请求 ====================

    def igdb_api_request(self, url, body, headers):
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

    def build_igdb_full_cache(self, progress_callback=None, cancel_flag=None):
        """下载 IGDB 中所有有 Steam 关联的游戏及其多维度分类信息，存入本地缓存。

        策略：先从 external_games 拉取所有 Steam 关联，再批量查 genres/themes/keywords 等。

        Args:
            progress_callback: fn(current, total, phase_str, detail_str)
            cancel_flag: list[bool]，cancel_flag[0]=True 时中止

        Returns:
            (genre_map, error): genre_map = {genre_id: [steam_app_ids]}（向后兼容），error = str | None
        """
        client_id, _ = self.get_igdb_credentials()
        access_token, error = self.get_igdb_access_token()
        if error:
            return {}, error

        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

        # ===== 预查询：获取 Steam 关联记录的最大 ID，用于估算进度 =====
        if progress_callback:
            progress_callback(0, 0, "正在估算数据量...", "")

        max_ext_id = 0
        body = "fields id; where external_game_source = 1; sort id desc; limit 1;"
        results, err = self.igdb_api_request(
            "https://api.igdb.com/v4/external_games", body, headers)
        if results:
            max_ext_id = results[0].get('id', 0)
        time.sleep(0.28)

        # ===== 第1步：遍历 external_games 获取所有 Steam 关联 =====
        game_to_steam = {}
        last_id = 0
        limit = 500

        while True:
            if cancel_flag and cancel_flag[0]:
                return {}, "用户取消"

            if progress_callback:
                step1_pct = (last_id / max_ext_id * 50) if max_ext_id > 0 else 0
                progress_callback(int(step1_pct), 100,
                                  "正在下载 Steam 游戏列表...",
                                  f"已获取 {len(game_to_steam)} 个游戏")

            body = (f"fields id,uid,game; "
                    f"where external_game_source = 1 & id > {last_id}; "
                    f"sort id asc; limit {limit};")

            results, err = self.igdb_api_request(
                "https://api.igdb.com/v4/external_games", body, headers)

            if err:
                return {}, f"下载 Steam 游戏列表失败：{err}"
            if not results:
                break

            for item in results:
                uid = item.get('uid', '')
                game_id = item.get('game')
                ext_id = item.get('id', 0)
                if uid and uid.isdigit() and game_id:
                    game_to_steam[int(game_id)] = int(uid)
                if ext_id > last_id:
                    last_id = ext_id

            if len(results) < limit:
                break
            time.sleep(0.28)

        if not game_to_steam:
            return {}, "未找到任何 Steam 游戏"

        # ===== 第2步：批量查询这些游戏的多维度分类信息 =====
        all_game_ids = list(game_to_steam.keys())
        # dim_maps: {dimension: {item_id: set of steam_app_ids}}
        dim_maps = {dim: {} for dim in self.IGDB_DIMENSIONS}
        batch_size = 500
        total_batches = (len(all_game_ids) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            if cancel_flag and cancel_flag[0]:
                return {}, "用户取消"

            if progress_callback:
                step2_pct = 50 + (batch_idx / total_batches * 50) if total_batches > 0 else 50
                progress_callback(int(step2_pct), 100,
                                  "正在下载游戏分类信息...",
                                  f"进度 {batch_idx + 1}/{total_batches}（共 {len(all_game_ids)} 个游戏）")

            batch = all_game_ids[batch_idx * batch_size: (batch_idx + 1) * batch_size]
            ids_str = ",".join(str(gid) for gid in batch)

            body = (f"fields id,{self.IGDB_GAME_FIELDS}; "
                    f"where id = ({ids_str}); "
                    f"limit {limit};")

            results, err = self.igdb_api_request(
                "https://api.igdb.com/v4/games", body, headers)

            if err:
                time.sleep(0.28)
                continue

            if results:
                for item in results:
                    gid = item.get('id')
                    if not gid or gid not in game_to_steam:
                        continue
                    steam_id = game_to_steam[gid]
                    # 遍历每个维度
                    for dim_name, dim_info in self.IGDB_DIMENSIONS.items():
                        field_name = dim_info['game_field']
                        item_ids = item.get(field_name, [])
                        if item_ids:
                            for item_id in item_ids:
                                dim_maps[dim_name].setdefault(item_id, set()).add(steam_id)

            time.sleep(0.28)

        # ===== 第3步：写入缓存 =====
        cache = {}
        now = time.time()

        for dim_name, dim_data in dim_maps.items():
            cache[dim_name] = {}
            for item_id, steam_ids_set in dim_data.items():
                cache[dim_name][str(item_id)] = {
                    "steam_ids": sorted(steam_ids_set),
                    "cached_at": now,
                }

        # 保存 game_to_steam 映射（供公司搜索等功能使用）
        cache["_game_to_steam"] = {str(k): v for k, v in game_to_steam.items()}

        dim_summary = ", ".join(f"{self.IGDB_DIMENSIONS[d]['name']} {len(dim_maps[d])}" for d in dim_maps if dim_maps[d])
        cache["_meta"] = {
            "type": "full_dump",
            "cached_at": now,
            "total_steam_games": len(game_to_steam),
            "dimensions": list(self.IGDB_DIMENSIONS.keys()),
        }
        self.save_igdb_cache(cache)

        if progress_callback:
            progress_callback(100, 100,
                              "✅ 下载完成",
                              f"共 {len(game_to_steam)} 个 Steam 游戏（{dim_summary}）")

        # 返回值保持 genre_map 形式以兼容旧调用
        result = {}
        for dim_name, dim_data in dim_maps.items():
            for item_id, sids in dim_data.items():
                if dim_name == "genres":
                    result[item_id] = sorted(sids)
        return result, None

    def fetch_igdb_games_by_dimension(self, dimension, item_id, item_name, progress_callback=None, force_refresh=False):
        """根据维度和条目 ID 获取该条目下所有游戏的 Steam AppID

        优先使用本地全量缓存。如果缓存不存在或已过期，则自动触发全量构建。

        Args:
            dimension: 维度名称，如 'genres', 'themes', 'keywords', ...
            item_id: 条目 ID
            item_name: 条目名称（用于显示）
        """
        if not force_refresh:
            cached_ids, cached_at = self.get_igdb_dimension_cache(dimension, item_id)
            if cached_ids is not None and self.is_igdb_cache_valid(cached_at):
                if progress_callback:
                    age_hours = (time.time() - cached_at) / 3600
                    progress_callback(len(cached_ids), len(cached_ids),
                                      f"使用本地缓存",
                                      f"{item_name}: {len(cached_ids)} 个游戏（缓存于 {age_hours:.0f} 小时前）")
                return cached_ids, None

            # 该条目无缓存，但全量缓存可能已构建（只是该条目确实没有 Steam 游戏）
            cache = self.load_igdb_cache()
            meta = cache.get("_meta", {})
            if meta.get("type") == "full_dump" and self.is_igdb_cache_valid(meta.get("cached_at", 0)):
                if progress_callback:
                    age_hours = (time.time() - meta["cached_at"]) / 3600
                    progress_callback(0, 0,
                                      f"使用本地缓存", f"{item_name}: 0 个 Steam 游戏（缓存于 {age_hours:.0f} 小时前）")
                return [], None

        # === 缓存不存在或已过期：触发下载 ===
        if progress_callback:
            progress_callback(0, 0, "本地数据不完整，正在从 IGDB 下载...", "首次下载约需 5-8 分钟")

        genre_map, error = self.build_igdb_full_cache(progress_callback)
        if error:
            return [], error

        # 从刚构建的缓存中返回结果
        cached_ids, _ = self.get_igdb_dimension_cache(dimension, item_id)
        return cached_ids if cached_ids else [], None

    def fetch_igdb_games_by_genre(self, genre_id, genre_name, progress_callback=None, force_refresh=False):
        """根据类型 ID 获取该类型下所有游戏的 Steam AppID（向后兼容）"""
        return self.fetch_igdb_games_by_dimension("genres", genre_id, genre_name, progress_callback, force_refresh)

    # ==================== IGDB 公司搜索 ====================

    def search_igdb_companies(self, query):
        """搜索 IGDB 公司（开发商/发行商）

        Args:
            query: 搜索关键词

        Returns:
            (list_of_companies, error): companies = [{'id': ..., 'name': ..., 'slug': ...}, ...]
        """
        if not query or len(query.strip()) < 2:
            return [], "搜索关键词至少 2 个字符"

        client_id, _ = self.get_igdb_credentials()
        access_token, error = self.get_igdb_access_token()
        if error:
            return [], error

        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

        body = f'fields id,name,slug; where name ~ *"{query.strip()}"*; limit 30;'
        results, err = self.igdb_api_request("https://api.igdb.com/v4/companies", body, headers)
        if err:
            return [], err

        return results or [], None

    def count_igdb_company_steam_games(self, company_ids):
        """批量统计多个公司各自关联的 Steam 游戏数量

        使用单次批量查询 involved_companies + 本地 game_to_steam 缓存，
        避免为每个公司单独发起 API 请求。

        Args:
            company_ids: 公司 ID 列表

        Returns:
            dict: {company_id: steam_game_count}
        """
        if not company_ids:
            return {}

        client_id, _ = self.get_igdb_credentials()
        access_token, error = self.get_igdb_access_token()
        if error:
            return {}

        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

        # 批量查询所有公司的 involved_companies
        company_games = {cid: set() for cid in company_ids}
        ids_str = ",".join(str(cid) for cid in company_ids)
        offset = 0
        limit = 500

        while True:
            body = (f"fields game,company; "
                    f"where company = ({ids_str}); "
                    f"limit {limit}; offset {offset};")
            results, err = self.igdb_api_request(
                "https://api.igdb.com/v4/involved_companies", body, headers)
            if err or not results:
                break
            for item in results:
                cid = item.get('company')
                gid = item.get('game')
                if cid and gid and cid in company_games:
                    company_games[cid].add(int(gid))
            if len(results) < limit:
                break
            offset += limit
            time.sleep(0.28)

        # 用本地缓存的 game_to_steam 映射计算 Steam 游戏数
        cache = self.load_igdb_cache()
        game_to_steam = cache.get("_game_to_steam", {})

        counts = {}
        for cid, game_ids in company_games.items():
            steam_count = sum(1 for gid in game_ids if game_to_steam.get(str(gid)))
            counts[cid] = steam_count

        return counts

    def fetch_igdb_games_by_company(self, company_id, company_name, progress_callback=None):
        """获取某公司关联的所有 Steam 游戏

        策略：查 involved_companies → 获取 game IDs → 用本地 game_to_steam 映射转换

        Args:
            company_id: IGDB 公司 ID
            company_name: 公司名称（用于显示）
            progress_callback: 进度回调

        Returns:
            (steam_ids, error)
        """
        client_id, _ = self.get_igdb_credentials()
        access_token, error = self.get_igdb_access_token()
        if error:
            return [], error

        headers = {
            'Client-ID': client_id,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        }

        if progress_callback:
            progress_callback(0, 0, f"正在查询 {company_name} 的游戏列表...", "")

        # 查询 involved_companies 获取该公司参与的所有游戏
        game_ids = set()
        offset = 0
        limit = 500

        while True:
            body = (f"fields game; "
                    f"where company = {company_id}; "
                    f"limit {limit}; offset {offset};")
            results, err = self.igdb_api_request(
                "https://api.igdb.com/v4/involved_companies", body, headers)

            if err:
                return [], f"查询公司游戏失败：{err}"
            if not results:
                break

            for item in results:
                gid = item.get('game')
                if gid:
                    game_ids.add(int(gid))

            if len(results) < limit:
                break
            offset += limit
            time.sleep(0.28)

        if not game_ids:
            return [], None

        if progress_callback:
            progress_callback(50, 100, f"正在匹配 Steam 游戏...", f"共 {len(game_ids)} 个 IGDB 游戏")

        # 尝试用本地 game_to_steam 映射
        cache = self.load_igdb_cache()
        game_to_steam = cache.get("_game_to_steam", {})

        steam_ids = set()
        unmapped_ids = []

        for gid in game_ids:
            steam_id = game_to_steam.get(str(gid))
            if steam_id:
                steam_ids.add(int(steam_id))
            else:
                unmapped_ids.append(gid)

        # 对于未映射的游戏，通过 API 查询 external_games
        if unmapped_ids:
            batch_size = 500
            for i in range(0, len(unmapped_ids), batch_size):
                batch = unmapped_ids[i:i + batch_size]
                ids_str = ",".join(str(gid) for gid in batch)
                body = (f"fields uid,game; "
                        f"where external_game_source = 1 & game = ({ids_str}); "
                        f"limit {batch_size};")
                results, err = self.igdb_api_request(
                    "https://api.igdb.com/v4/external_games", body, headers)
                if results:
                    for item in results:
                        uid = item.get('uid', '')
                        if uid and uid.isdigit():
                            steam_ids.add(int(uid))
                time.sleep(0.28)

        if progress_callback:
            progress_callback(100, 100, f"✅ 查询完成",
                              f"{company_name}: {len(steam_ids)} 个 Steam 游戏")

        return sorted(steam_ids), None

    def load_json(self):
        if not self.current_account.storage_path or not os.path.exists(self.current_account.storage_path):
            messagebox.showerror("错误", f"读取文件失败，请确保已选择有效的 Steam 账号。")
            return None
        try:
            with open(self.current_account.storage_path, 'r', encoding='utf-8') as f:
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
        if not self.current_account.storage_path:
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
        tmp_path = self.current_account.storage_path + ".tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

            # 原子替换
            if os.path.exists(self.current_account.storage_path):
                os.replace(tmp_path, self.current_account.storage_path)
            else:
                os.rename(tmp_path, self.current_account.storage_path)

            messagebox.showinfo("成功", f"文件已保存：\n{os.path.basename(self.current_account.storage_path)}{backup_info}")
            return True
        except Exception as e:
            messagebox.showerror("保存失败", f"无法写入文件: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
            return False


    @staticmethod
    def sanitize_filename(name):
        """清洗文件名，替换系统禁止的特殊字符"""
        return re.sub(r'[\\/*?:"<>|]', '_', name).strip()

    def get_static_collections(self, data):
        """获取所有收藏夹（含动态）及其 entry 引用，按字母排序"""
        return self.get_all_collections_with_refs(data)

    @staticmethod
    def get_all_collections_with_refs(data):
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

    @staticmethod
    def get_all_collections_ordered(data):
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

    @staticmethod
    def extract_ids_from_html(html_text):
        """核心提取逻辑：从 HTML 中提取 AppID"""
        search_area = html_text
        list_start = html_text.find('id="RecommendationsRows"')
        if list_start == -1:
            list_start = html_text.find('class="creator_grid_ctn"')

        if list_start != -1:
            footer_start = html_text.find('id="footer"', list_start)
            search_area = html_text[list_start: (footer_start if footer_start != -1 else len(html_text))]

        raw_matches = re.findall(r'data-ds-appid="([\d,]+)"', search_area)
        all_ids = []
        for m in raw_matches:
            if ',' in m:
                all_ids.extend(m.split(','))
            else:
                all_ids.append(m)

        return list(dict.fromkeys([int(aid) for aid in all_ids if aid.isdigit()]))

    def extract_page_name_from_html(self, html_text, url_hint=""):
        """从 HTML 中智能提取页面名称（带类型前缀）"""
        type_name_cn = "列表"
        if url_hint:
            page_type, _ = self.extract_steam_list_info(url_hint)
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

    def extract_curator_name(self, html_text):
        """从 HTML 中智能提取鉴赏家名称（保持向后兼容）"""
        return self.extract_page_name_from_html(html_text)

    @staticmethod
    def extract_steam_list_info(url_or_id):
        """从 URL 或直接输入中提取 Steam 列表页面信息"""
        text = url_or_id.strip()

        if text.isdigit():
            return "curator", text

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
                return page_type, match.group(1)

        return None, None

    def fetch_steam_list(self, page_type, identifier, progress_callback=None, login_cookies=None):
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
            return self.fetch_curator_style_api(page_type, identifier, type_name_cn, cookies, has_login,
                                                 progress_callback)
        else:
            return self.fetch_generic_list(page_type, identifier, type_name_cn, cookies, has_login, progress_callback)

    def fetch_curator_style_api(self, page_type, identifier, type_name_cn, cookies, has_login, progress_callback=None):
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
                    f"🌐 扫描语言 [{lang_idx + 1}/{len(lang_configs)}]：{lang_display} — 正在连接..."
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
                            f"🌐 [{lang_idx + 1}/{len(lang_configs)}] {lang_display} — 第 {lang_page}/{total_pages} 页（本页新增 {new_in_page}，共 {len(chunk_ids) if html_chunk else 0} 条）"
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

    def fetch_generic_list(self, page_type, identifier, type_name_cn, cookies, has_login, progress_callback=None):
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

            ids = self.extract_ids_from_html(html_content)
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

                    page_ids = self.extract_ids_from_html(page_html)
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

    @staticmethod
    def extract_ids_from_steamdb_html(html_text):
        """从 SteamDB 页面源代码中提取 AppID"""
        tbody_match = re.search(r'<tbody.*?>(.*?)</tbody>', html_text, re.DOTALL)
        if not tbody_match:
            return []
        return [int(aid) for aid in re.findall(r'data-appid="(\d+)"', tbody_match.group(1))]

    def perform_incremental_update(self, data, target_entry, new_ids_from_src, raw_name):
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
        target_entry[1]['version'] = self.next_version(data)
        target_entry[1].setdefault('conflictResolutionMethod', 'custom')
        target_entry[1].setdefault('strMethodId', 'union-collections')

        # 创建辅助收藏夹
        self.add_static_collection(data, f"{clean_name} - 比旧版多的", added_list)
        if removed_list:
            self.add_static_collection(data, f"{clean_name} - 比旧版少的", removed_list)

        return len(added_list), len(removed_list), len(val_obj['added']), True

    def perform_replace_update(self, data, target_entry, new_ids):
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
        target_entry[1]['version'] = self.next_version(data)
        target_entry[1].setdefault('conflictResolutionMethod', 'custom')
        target_entry[1].setdefault('strMethodId', 'union-collections')

        return old_count, len(new_ids)

    # --- 收藏夹导出/导入（两种格式） ---

    @staticmethod
    def export_collections_appid_list(collections):
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

    @staticmethod
    def export_collections_structured(collections):
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

    def import_collections_appid_list(self, file_path, data):
        """格式一：导入一行一个 AppID 的列表文件，创建一个新收藏夹"""
        file_title = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, 'r', encoding='utf-8') as f:
            app_ids = [int(line.strip()) for line in f if line.strip().isdigit()]
        if not app_ids:
            return None, "文件中没有有效的 AppID。"
        self.add_static_collection(data, file_title, app_ids)
        return len(app_ids), None

    def import_collections_structured(self, file_path, data):
        """格式二：导入结构化 JSON 文件，还原多个收藏夹（含动态逻辑）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
        except JSONDecodeError as e:
            return None, "文件不是有效的 JSON 格式。"

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
                    "version": self.next_version(data),
                    "conflictResolutionMethod": "custom",
                    "strMethodId": "union-collections"
                }]
                data.append(new_entry)
            else:
                # 静态收藏夹
                self.add_static_collection(data, name.replace(self.induce_suffix, "").strip(), added)
            count += 1

        return count, None

    def add_dynamic_collection(self, data, name, friend_code):
        col_id = f"uc-{secrets.token_hex(4)}"
        storage_key = f"user-collections.{col_id}"
        filter_groups = [{"rgOptions": [], "bAcceptUnion": False} for _ in range(9)]
        filter_groups[0]["bAcceptUnion"] = True
        filter_groups[6]["rgOptions"] = [int(friend_code)]
        val_obj = {"id": col_id, "name": name + self.induce_suffix, "added": [], "removed": [],
                   "filterSpec": {"nFormatVersion": 2, "strSearchText": "", "filterGroups": filter_groups,
                                  "setSuggestions": {}}}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()),
                                   "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')),
                                   "version": self.next_version(data),
                                   "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}]
        data.append(new_entry)

    def fetch_steam250_ids(self, url, progress_callback=None):
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


