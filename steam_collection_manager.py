import json
import os
import re
import shutil
from datetime import datetime


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