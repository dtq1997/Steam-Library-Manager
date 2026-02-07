import json
import os
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk, simpledialog

from core import SteamToolboxCore
from steam_account_manager import SteamAccountScanner


class SteamToolbox:
    def __init__(self):
        
        self.core = SteamToolboxCore()
        
        # ---

        self.induce_suffix = "(删除这段字以触发云同步)"
        self.disclaimer = f"\n\n(若其中包含未拥有的游戏、重复条目或是 DLC，会导致 Steam 收藏夹内显示的数目偏少。)"

    
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
                initialdir=self.core.current_dir, title="选择 AppID 列表文件（TXT）",
                filetypes=[("Text files", "*.txt")])
            if not paths:
                return
            data = self.core.load_json()
            if data is None:
                return
            existing = self.core.get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            results = []
            for p in paths:
                count, err = self.core.import_collections_appid_list(p, data)
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
                initialdir=self.core.current_dir, title="选择结构化收藏夹文件（JSON）",
                filetypes=[("JSON files", "*.json")])
            if not path:
                return
            data = self.core.load_json()
            if data is None:
                return
            existing = self.core.get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}
            try:
                count, err = self.core.import_collections_structured(path, data)
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
                  justify="left").pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📦 导入结构化数据（JSON）\n还原收藏夹名称及动态逻辑",
                  command=import_json, font=("微软雅黑", 9), width=32, height=3,
                  justify="left").pack(padx=20, pady=(0, 10))



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
            unique_ids = self.core.export_collections_appid_list(selected)
            if not unique_ids:
                messagebox.showwarning("提示", "选中的收藏夹没有可导出的 AppID。")
                return
            save_path = filedialog.asksaveasfilename(
                initialdir=self.core.current_dir, title="保存合并 AppID 列表",
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
            dest_dir = filedialog.askdirectory(initialdir=self.core.current_dir, title="选择保存导出文件的文件夹")
            if not dest_dir:
                return
            count = 0
            for col in selected:
                safe_name = self.core.sanitize_filename(col['name'])
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
            export_data = self.core.export_collections_structured(selected)
            save_path = filedialog.asksaveasfilename(
                initialdir=self.core.current_dir, title="保存收藏夹结构化数据",
                defaultextension=".json", initialfile="exported_collections.json",
                filetypes=[("JSON files", "*.json")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("✅ 导出成功",
                                    f"已导出 {len(selected)} 个收藏夹的完整结构。\n（含名称、分类信息及动态逻辑）")

        tk.Button(fmt_win, text="📄 合并为单个 AppID 列表（TXT）\n所有选中收藏夹的 AppID 去重合并",
                  command=export_merged_appid, font=("微软雅黑", 9), width=36, height=3,
                  justify="left").pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📁 导出为多个 TXT 文件\n每个收藏夹一个文件，动态收藏夹仅导出额外添加部分",
                  command=export_multiple_txt, font=("微软雅黑", 9), width=36, height=3,
                  justify="left").pack(padx=20, pady=(0, 5))
        tk.Button(fmt_win, text="📦 导出为结构化数据（JSON）\n含名称、分类、动态逻辑，可用于完整还原",
                  command=export_structured_json, font=("微软雅黑", 9), width=36, height=3,
                  justify="left").pack(padx=20, pady=(0, 10))

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
                initialdir=self.core.current_dir, title="选择 AppID 列表 (TXT)",
                filetypes=[("Text files", "*.txt")])
            if not txt_paths:
                return
            data = self.core.load_json()
            if data is None:
                return
            all_cols = self.core.get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return

            sources = {}
            for p in txt_paths:
                file_title = os.path.splitext(os.path.basename(p))[0]
                with open(p, 'r', encoding='utf-8') as f:
                    ids = [int(line.strip()) for line in f if line.strip().isdigit()]
                sources[file_title] = {"name": file_title, "ids": ids}

            existing = self.core.get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}

            def on_done():
                self._ui_mark_dirty(data)
                self._ui_refresh()

            self.protected_show_batch_update_mapping(data, all_cols, sources, on_done)

        def update_from_json():
            fmt_win.destroy()
            path = filedialog.askopenfilename(
                initialdir=self.core.current_dir, title="选择结构化收藏夹文件（JSON）",
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

            data = self.core.load_json()
            if data is None:
                return
            all_cols = self.core.get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return

            existing = self.core.get_all_collections_ordered(data)
            self._original_col_ids = {c['id'] for c in existing}

            sources = {}
            for i, src in enumerate(src_cols):
                key = src.get("name", f"收藏夹 {i + 1}")
                sources[key] = {"name": key, "ids": src.get("added", [])}

            def on_done():
                self._ui_mark_dirty(data)
                self._ui_refresh()

            self.protected_show_batch_update_mapping(data, all_cols, sources, on_done)

        tk.Button(fmt_win, text="📄 从 TXT 文件更新\n选择多个 AppID 列表文件",
                  command=update_from_txt, font=("微软雅黑", 9), width=32, height=3,
                  justify="left").pack(padx=20, pady=(5, 5))
        tk.Button(fmt_win, text="📦 从 JSON 文件更新\n使用结构化收藏夹数据",
                  command=update_from_json, font=("微软雅黑", 9), width=32, height=3,
                  justify="left").pack(padx=20, pady=(0, 10))

    def protected_show_batch_update_mapping(self, data, all_cols, sources, on_done, parent_to_close=None,
                                            saved_mappings_key=None):
        """通用的批量更新映射界面：一屏选择所有来源到目标收藏夹+更新模式"""
        up_win = tk.Toplevel()
        up_win.title("批量更新收藏夹")
        up_win.attributes("-topmost", True)

        tk.Label(up_win, text="请为每个来源选择目标收藏夹和更新模式：",
                 font=("微软雅黑", 10, "bold")).pack(pady=(15, 10))

        mapping_frame = tk.Frame(up_win)
        mapping_frame.pack(fill="both", expand=True, padx=30, pady=(0, 10))

        target_names = ["（跳过）"] + [c['display_name'] for c in all_cols]
        mode_options = ["增量", "替换"]
        combo_vars = {}

        # 加载上次保存的映射选择
        saved_mappings = {}
        if saved_mappings_key:
            config = self.core.load_config()
            saved_mappings = config.get(saved_mappings_key, {})

        max_target_len = max(len(n) for n in target_names) if target_names else 20

        def _create_row(parent, key, d):
            row_frame = tk.Frame(parent)
            row_frame.pack(fill="x", pady=5)
            tk.Label(row_frame, text=f"📦 {d['name']} ({len(d['ids'])} 个)",
                     font=("微软雅黑", 9), anchor="w").pack(side="left")
            tk.Label(row_frame, text="→", font=("微软雅黑", 9)).pack(side="left", padx=10)
            combo = ttk.Combobox(row_frame, values=target_names,
                                 width=max(30, max_target_len + 2), state="readonly")
            # 尝试恢复上次的选择
            last_sel = saved_mappings.get(key, "")
            if last_sel and last_sel in target_names:
                combo.set(last_sel)
            else:
                combo.set("（跳过）")
            combo.pack(side="left")
            mode_combo = ttk.Combobox(row_frame, values=mode_options, width=6, state="readonly")
            mode_combo.set("增量")
            mode_combo.pack(side="left", padx=(5, 0))
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
                config = self.core.load_config()
                current_mappings = {}
                for key, (combo, _) in combo_vars.items():
                    sel = combo.get()
                    if sel != "（跳过）":
                        current_mappings[key] = sel
                config[saved_mappings_key] = current_mappings
                self.core.save_config(config)

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
                    old_count, new_count = self.core.perform_replace_update(
                        data, target['entry_ref'], source_data['ids'])
                    results.append(f"🔄 {source_data['name']} → {target['name']}\n   替换: {old_count} → {new_count}")
                    update_count += 1
                else:
                    a, r, t, updated = self.core.perform_incremental_update(
                        data, target['entry_ref'], source_data['ids'], target['name'])
                    if updated:
                        results.append(
                            f"✅ {source_data['name']} → {target['name']}\n   新增: {a}, 移除: {r}, 总计: {t}")
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
        tk.Button(btn_row, text="✅ 确认更新", command=confirm_update, width=15).pack(side="left", padx=10)
        tk.Button(btn_row, text="取消", command=up_win.destroy, width=10).pack(side="left", padx=10)

    def protected_show_update_target_dialog(self, data, all_cols, new_ids, source_name, index, total, on_next):
        """单来源更新的快捷入口，内部调用 _show_batch_update_mapping"""
        sources = {source_name: {"name": source_name, "ids": new_ids}}
        self.protected_show_batch_update_mapping(data, all_cols, sources, on_next)

    # --- 4. 动态好友同步 ---
    def open_friend_sync_ui(self):
        data = self.core.load_json()
        if data is None: return
        sync_win = tk.Toplevel()
        sync_win.title("批量同步 Steam 用户游戏库")
        sync_win.attributes("-topmost", True)
        tk.Label(sync_win, text="1. 请输入对方的 Steam 好友代码（每行一个）", font=("微软雅黑", 10, "bold")).pack(
            pady=(15, 0))
        codes_text = tk.Text(sync_win, height=8, width=60)
        codes_text.pack(padx=20, pady=5)
        tk.Label(sync_win, text="2. 生成的收藏夹名称 (每行一个)", font=("微软雅黑", 10, "bold")).pack(pady=(10, 0))
        names_text = tk.Text(sync_win, height=8, width=60)
        names_text.pack(padx=20, pady=5)

        def generate_default_names():
            raw_ids = re.findall(r'\d+', codes_text.get("1.0", "end"))
            names_text.delete("1.0", "end")
            for rid in raw_ids: names_text.insert("end", f"好友代码 [{rid}]\n")

        def commit_import():
            codes = re.findall(r'\d+', codes_text.get("1.0", "end"))
            names = [n.strip() for n in names_text.get("1.0", "end").strip().split('\n') if n.strip()]
            for i, cid in enumerate(codes):
                cname = names[i] if i < len(names) else f"好友代码 [{cid}]"
                self.protected_add_dynamic_collection(data, cname, cid)
            if codes: self.core.save_json(data, backup_description="同步好友游戏库"); sync_win.destroy()

        btn_frame = tk.Frame(sync_win)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="✨ 生成默认名称", command=generate_default_names, width=18, height=2).pack(
            side="left", padx=10)
        tk.Button(btn_frame, text="开始导入", command=commit_import, width=18, height=2).pack(side="left", padx=10)

    def protected_add_dynamic_collection(self, data, name, friend_code):
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
                                   "version": self.core.next_version(data),
                                   "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}]
        data.append(new_entry)

    # --- 5. 选择来源入口 ---
    def open_source_selection(self):
        sel_win = tk.Toplevel()
        sel_win.title("从其他来源获取 Steam 游戏列表")
        sel_win.resizable(False, False)
        sel_win.attributes("-topmost", True)
        tk.Label(sel_win, text="请选择获取 AppID 的来源渠道：", font=("微软雅黑", 10), pady=15).pack(padx=30)

        def _make_color_btn(parent, text, bg, command):
            lbl = tk.Label(parent, text=text, font=("微软雅黑", 11), bg=bg, fg="white",
                           padx=20, pady=12, cursor="hand2", relief="raised", bd=1)
            lbl.pack(pady=5, padx=30, fill="x")
            lbl.bind("<Enter>", lambda e: lbl.config(relief="groove"))
            lbl.bind("<Leave>", lambda e: lbl.config(relief="raised"))
            lbl.bind("<Button-1>", lambda e: command())
            return lbl

        _make_color_btn(sel_win, "🏆 从 Steam 列表页面获取（鉴赏家/发行商等）", "#5b9bd5",
                        lambda: [sel_win.destroy(), self.curator_sync_ui()])
        _make_color_btn(sel_win, "📊 从 SteamDB 列表页面处获取", "#e86c2c",
                        lambda: [sel_win.destroy(), self.steamdb_sync_ui()])
        tk.Frame(sel_win, height=10).pack()

    # --- 鉴赏家/发行商/开发商等列表界面 ---
    def curator_sync_ui(self):
        data = self.core.load_json()
        if data is None: return
        cur_win = tk.Toplevel()
        cur_win.title("同步 Steam 列表页面")
        cur_win.attributes("-topmost", True)

        fetched_ids = []
        fetched_name = tk.StringVar(value="")

        tk.Label(cur_win,
                 text="使用指南：\n1. 在下方输入框粘贴 Steam 列表页面的 URL（支持鉴赏家、发行商、开发商、系列等）。\n2. 点击「开始获取」，程序将自动抓取游戏列表。\n3. 获取完成后，选择导入、导出或更新操作。",
                 justify="left", font=("微软雅黑", 9), wraplength=450).pack(padx=20, pady=(15, 5))

        url_frame = tk.Frame(cur_win)
        url_frame.pack(fill="x", padx=20, pady=(5, 0))
        tk.Label(url_frame, text="Steam 列表 URL：", font=("微软雅黑", 9)).pack(side="left")
        url_entry = tk.Entry(url_frame, width=40, font=("微软雅黑", 9))
        url_entry.pack(side="left", padx=5, fill="x", expand=True)
        url_entry.insert(0, "https://store.steampowered.com/curator/44791597/")

        ex_frame = tk.Frame(cur_win)
        ex_frame.pack(fill="x", padx=20, pady=(3, 0))
        tk.Label(ex_frame, text="示例：", font=("微软雅黑", 8), fg="gray").pack(side="left")

        def set_url(url):
            url_entry.delete(0, "end")
            url_entry.insert(0, url)

        tk.Button(ex_frame, text="鉴赏家", fg="blue", relief="flat", font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/curator/44791597/")).pack(side="left", padx=3)
        tk.Button(ex_frame, text="发行商", fg="blue", relief="flat", font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/publisher/Devolver%20Digital")).pack(
            side="left", padx=3)
        tk.Button(ex_frame, text="开发商", fg="blue", relief="flat", font=("微软雅黑", 8),
                  command=lambda: set_url("https://store.steampowered.com/developer/Valve")).pack(side="left", padx=3)
        tk.Button(ex_frame, text="🌐 浏览器打开", fg="gray", relief="flat", font=("微软雅黑", 8),
                  command=lambda: webbrowser.open(url_entry.get().strip())).pack(side="right")

        # Cookie 状态显示（使用全局配置的 Cookie）
        saved_cookie = self.core.get_saved_cookie()
        cookie_status_frame = tk.Frame(cur_win)
        cookie_status_frame.pack(fill="x", padx=20, pady=(8, 0))

        if saved_cookie:
            tk.Label(cookie_status_frame, text="🔐 已配置登录态 Cookie，可获取完整列表",
                     font=("微软雅黑", 9), fg="green").pack(anchor="w")
        else:
            tk.Label(cookie_status_frame, text="⚠️ 未配置登录态 Cookie，可能无法获取完整内容列表",
                     font=("微软雅黑", 9), fg="orange").pack(anchor="w")
            tk.Label(cookie_status_frame, text="     → 可在主界面「🔑 管理 Cookie」中配置",
                     font=("微软雅黑", 8), fg="#888").pack(anchor="w")

        status_var = tk.StringVar(value="尚未获取数据。")
        status_label = tk.Label(cur_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray")
        status_label.pack(padx=20, pady=(8, 0), anchor="w")

        progress_bar = ttk.Progressbar(cur_win, length=400, mode='indeterminate')
        progress_bar.pack(padx=20, pady=(4, 0), fill="x")
        progress_bar.pack_forget()

        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(cur_win, textvariable=detail_var, font=("微软雅黑", 8), fg="#888")
        detail_label.pack(padx=20, anchor="w")
        detail_label.pack_forget()

        login_hint = tk.Label(cur_win, text="⚠️ 未提供登录态 Cookie，可能无法获取完整内容列表",
                              font=("微软雅黑", 8), fg="red")
        if not saved_cookie:
            login_hint.pack(padx=20, anchor="w")

        is_fetching = [False]

        def do_fetch():
            nonlocal fetched_ids
            if is_fetching[0]:
                return

            url_text = url_entry.get().strip()
            page_type, identifier = self.core.extract_steam_list_info(url_text)
            if not page_type or not identifier:
                messagebox.showwarning("错误",
                                       "无法识别 Steam 列表页面。\n请输入有效的 URL（支持鉴赏家、发行商、开发商、系列等）。")
                return

            is_fetching[0] = True
            fetch_btn.config(bg="#999999", cursor="wait")
            status_var.set("正在连接 Steam...")
            status_label.config(fg="gray")
            cur_win.update()

            login_cookies = None
            cookie_val = self.core.get_saved_cookie()
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
                    progress_bar.pack(padx=20, pady=(4, 0), fill="x")
                    detail_label.pack(padx=20, anchor="w")
                    progress_bar.start(15)

                cur_win.after(0, show_progress)

                ids, name, error, has_login = self.core.fetch_steam_list(page_type, identifier, update_progress,
                                                                     login_cookies)

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
                             bg="#4a90d9", fg="white", padx=20, pady=8, cursor="hand2", relief="raised", bd=1)
        fetch_btn.pack(pady=10)
        fetch_btn.bind("<Enter>", lambda e: fetch_btn.config(relief="groove") if not is_fetching[0] else None)
        fetch_btn.bind("<Leave>", lambda e: fetch_btn.config(relief="raised"))
        fetch_btn.bind("<Button-1>", lambda e: do_fetch())

        # 手动模式
        manual_expanded = tk.BooleanVar(value=False)
        manual_frame = tk.Frame(cur_win)
        manual_frame.pack(fill="x", padx=20, pady=(5, 0))

        def toggle_manual():
            if manual_expanded.get():
                manual_content.pack_forget()
                toggle_btn.config(text="▶ 手动模式（备用）")
                manual_expanded.set(False)
            else:
                manual_content.pack(fill="x", pady=5)
                toggle_btn.config(text="▼ 手动模式（备用）")
                manual_expanded.set(True)

        toggle_btn = tk.Button(manual_frame, text="▶ 手动模式（备用）", command=toggle_manual,
                               relief="flat", font=("微软雅黑", 9), fg="#666", cursor="hand2")
        toggle_btn.pack(anchor="w")

        manual_content = tk.Frame(manual_frame)

        tk.Label(manual_content,
                 text="若自动获取失败，可手动操作：\n1. 打开 Steam 列表页面，划到底加载全部游戏。\n2. 按 F12 打开控制台，执行下方指令复制 HTML。\n3. 粘贴到文本框，点击「使用手动输入」。",
                 justify="left", font=("微软雅黑", 8), fg="#666").pack(anchor="w")

        js_cmd = "copy(document.documentElement.outerHTML)"

        def copy_js():
            cur_win.clipboard_clear()
            cur_win.clipboard_append(js_cmd)
            messagebox.showinfo("成功", "指令已复制到剪贴板！\n请去浏览器控制台粘贴执行。")

        tk.Button(manual_content, text="📋 复制控制台指令", command=copy_js, font=("微软雅黑", 8)).pack(anchor="w",
                                                                                                       pady=2)

        html_text_box = tk.Text(manual_content, height=5, width=55, font=("微软雅黑", 8))
        html_text_box.pack(fill="x", pady=2)

        def use_manual():
            nonlocal fetched_ids
            raw_html = html_text_box.get("1.0", "end")
            ids = self.core.extract_ids_from_html(raw_html)
            if not ids:
                messagebox.showwarning("错误", "未能提取到任何 AppID。")
                return
            fetched_ids.clear()
            fetched_ids.extend(ids)
            fetched_name.set(self.core.extract_curator_name(raw_html))
            status_var.set(f"✅ 从手动输入中提取了 {len(ids)} 个游戏！")
            status_label.config(fg="green")

        tk.Button(manual_content, text="📤 使用手动输入", command=use_manual, font=("微软雅黑", 8)).pack(anchor="w",
                                                                                                        pady=2)

        btn_frame = tk.Frame(cur_win)
        btn_frame.pack(pady=15)

        def check_data():
            if not fetched_ids:
                messagebox.showwarning("错误", "请先获取数据！\n点击「开始获取」按钮。")
                return False
            return True

        def do_create():
            if not check_data(): return
            name = simpledialog.askstring("新建收藏夹", "请输入收藏夹名称：", initialvalue=fetched_name.get())
            if name:
                self.core.add_static_collection(data, name, list(fetched_ids))
                self.core.save_json(data, backup_description=f"从 Steam 列表创建收藏夹: {name}")
                messagebox.showinfo("录入成功",
                                    f"已建立新收藏夹。本次共录入 {len(fetched_ids)} 个 AppID。" + self.disclaimer)
                cur_win.destroy()

        def do_export():
            if not check_data(): return
            name = simpledialog.askstring("导出设置", "请输入生成的 TXT 文件名：",
                                          initialvalue=self.core.sanitize_filename(fetched_name.get()))
            if not name: return
            save_path = filedialog.asksaveasfilename(initialdir=self.core.current_dir, title="保存 AppID 列表",
                                                     defaultextension=".txt",
                                                     initialfile=f"{self.core.sanitize_filename(name)}.txt",
                                                     filetypes=[("Text files", "*.txt")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    for aid in fetched_ids: f.write(f"{aid}\n")
                messagebox.showinfo("成功", f"已成功导出 {len(fetched_ids)} 个 AppID。" + self.disclaimer)

        def do_update():
            if not check_data(): return
            all_cols = self.core.get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            sources = {fetched_name.get() or "Steam 列表": {"name": fetched_name.get() or "Steam 列表",
                                                            "ids": list(fetched_ids)}}

            def on_done():
                self.core.save_json(data, backup_description=f"从 Steam 列表更新收藏夹")
                cur_win.destroy()

            self.protected_show_batch_update_mapping(data, all_cols, sources, on_done, parent_to_close=cur_win)

        tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15).pack(side="left", padx=5)
        tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export, width=18).pack(side="left", padx=5)
        tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15).pack(side="left", padx=5)

    # --- 个人推荐分类界面（Steam250 + 鉴赏家精选） ---
    def protected_fetch_steam250_ids(self, url, progress_callback=None):
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
            with urllib.request.urlopen(req, timeout=20, context=self.core.ssl_context) as resp:
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
        data = self.core.load_json()
        if data is None: return

        fetched_data = {}  # key: source_key, value: {'ids': [...], 'name': '...'}

        rec_win = tk.Toplevel()
        rec_win.title("从推荐来源获取")
        rec_win.attributes("-topmost", True)

        # 使用指南（明确说明勾选后的文字会成为收藏夹名称）
        guide_frame = tk.Frame(rec_win)
        guide_frame.pack(fill="x", padx=20, pady=(15, 5))
        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=3, bg=rec_win.cget("bg"), relief="flat",
                             wrap="word")
        guide_text.tag_config("red", foreground="red", font=("微软雅黑", 9, "bold"))
        guide_text.insert("end", "使用指南：\n1. 勾选要获取的来源（可多选），")
        guide_text.insert("end", "勾选框后面的文字将成为收藏夹名称", "red")
        guide_text.insert("end", "。\n2. 直接点击下方的导入、导出或更新按钮，程序会自动获取数据并执行操作。")
        guide_text.config(state="disabled")
        guide_text.pack(fill="x")

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
            ("curator_thinky", "curator", "https://store.steampowered.com/curator/45228984-Thinky-Awards/",
             "📖 Thinky Games 数据库"),
            ("curator_moe_award", "curator", "https://store.steampowered.com/curator/45502290/", "🏆 萌系遊戲大賞"),
            ("curator_bishojo_award", "curator", "https://store.steampowered.com/curator/45531216/",
             "🏆 美少女游戏大赏"),
        ]

        check_vars = {}
        year_check_vars = {}  # 专门存储年份选项

        # ===== Steam250 区域 =====
        s250_frame = tk.LabelFrame(rec_win, text="📊 Steam250 排行榜", font=("微软雅黑", 10, "bold"), padx=10, pady=5)
        s250_frame.pack(fill="x", padx=20, pady=(10, 5))

        # 固定的三个排行榜
        for key, src_type, url, name in steam250_fixed_sources:
            var = tk.BooleanVar(value=False)
            check_vars[key] = (var, src_type, url, name)
            tk.Checkbutton(s250_frame, text=name, variable=var, font=("微软雅黑", 9)).pack(anchor="w")

        # 年度榜单区域（支持多选年份）
        year_frame = tk.Frame(s250_frame)
        year_frame.pack(fill="x", pady=(5, 0))

        tk.Label(year_frame, text="📅 年度榜单：", font=("微软雅黑", 9)).pack(side="left")

        # 生成最近几年的选项（从当前年份往前推 5 年）
        from datetime import datetime
        current_year = datetime.now().year
        available_years = list(range(current_year, current_year - 6, -1))  # 如 [2026, 2025, 2024, 2023, 2022, 2021]

        year_inner_frame = tk.Frame(year_frame)
        year_inner_frame.pack(side="left", padx=(5, 0))

        for year in available_years:
            var = tk.BooleanVar(value=False)
            key = f"steam250_{year}"
            url = f"https://steam250.com/{year}"
            name = f"前 250 优秀游戏（{year} 年度）"
            year_check_vars[key] = (var, "steam250", url, name, year)
            tk.Checkbutton(year_inner_frame, text=str(year), variable=var, font=("微软雅黑", 9)).pack(side="left")

        # ===== 全选按钮区域 =====
        select_all_frame = tk.Frame(rec_win)
        select_all_frame.pack(fill="x", padx=20, pady=(5, 0))

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

        tk.Button(select_all_frame, text="☑️ 全选 Steam250", command=select_all_s250, font=("微软雅黑", 8)).pack(
            side="left", padx=(0, 5))
        tk.Button(select_all_frame, text="☐ 取消全选 Steam250", command=deselect_all_s250, font=("微软雅黑", 8)).pack(
            side="left")

        # ===== 鉴赏家精选区域 =====
        curator_frame = tk.LabelFrame(rec_win, text="🎮 鉴赏家精选", font=("微软雅黑", 10, "bold"), padx=10, pady=5)
        curator_frame.pack(fill="x", padx=20, pady=5)

        for key, src_type, url, name in curator_sources:
            var = tk.BooleanVar(value=False)
            check_vars[key] = (var, src_type, url, name)
            cb = tk.Checkbutton(curator_frame, text=name, variable=var, font=("微软雅黑", 9))
            cb.pack(anchor="w")

        # 鉴赏家全选按钮
        curator_btn_frame = tk.Frame(curator_frame)
        curator_btn_frame.pack(fill="x", pady=(5, 0))

        def select_all_curator():
            for k, v in check_vars.items():
                if k.startswith("curator"):
                    v[0].set(True)

        def deselect_all_curator():
            for k, v in check_vars.items():
                if k.startswith("curator"):
                    v[0].set(False)

        tk.Button(curator_btn_frame, text="☑️ 全选鉴赏家", command=select_all_curator, font=("微软雅黑", 8)).pack(
            side="left", padx=(0, 5))
        tk.Button(curator_btn_frame, text="☐ 取消全选鉴赏家", command=deselect_all_curator, font=("微软雅黑", 8)).pack(
            side="left")

        # 提示信息
        tk.Label(curator_frame, text="💡 鉴赏家列表会使用多语言扫描以获取完整数据",
                 font=("微软雅黑", 8), fg="#666").pack(anchor="w", pady=(5, 0))

        # Cookie 状态提示
        cookie_status_frame = tk.Frame(curator_frame)
        cookie_status_frame.pack(fill="x", pady=(3, 0))

        saved_cookie = self.core.get_saved_cookie()
        if saved_cookie:
            tk.Label(cookie_status_frame, text="🔐 已配置登录态 Cookie，可获取完整列表",
                     font=("微软雅黑", 8), fg="green").pack(anchor="w")
        else:
            tk.Label(cookie_status_frame, text="⚠️ 未配置登录态 Cookie，可能无法获取完整列表",
                     font=("微软雅黑", 8), fg="orange").pack(anchor="w")
            tk.Label(cookie_status_frame, text="     → 可在主界面「🔑 管理登录态 Cookie」中配置",
                     font=("微软雅黑", 8), fg="#888").pack(anchor="w")

        # ===== IGDB 游戏类型分类区域 =====
        igdb_check_vars = {}  # 存储 IGDB 类型的勾选状态
        igdb_genres_cache = []  # 缓存已加载的类型列表

        igdb_frame = tk.LabelFrame(rec_win, text="🏷️ 游戏类型分类（IGDB）", font=("微软雅黑", 10, "bold"), padx=10,
                                   pady=5)
        igdb_frame.pack(fill="x", padx=20, pady=5)

        # IGDB 凭证状态
        igdb_status_frame = tk.Frame(igdb_frame)
        igdb_status_frame.pack(fill="x", pady=(0, 5))

        igdb_client_id, igdb_client_secret = self.core.get_igdb_credentials()
        igdb_configured = bool(igdb_client_id and igdb_client_secret)

        if igdb_configured:
            igdb_status_label = tk.Label(igdb_status_frame, text="🔐 已配置 IGDB API 凭证",
                                         font=("微软雅黑", 8), fg="green")
        else:
            igdb_status_label = tk.Label(igdb_status_frame, text="⚠️ 未配置 IGDB API 凭证，无法使用此功能",
                                         font=("微软雅黑", 8), fg="orange")
        igdb_status_label.pack(side="left")

        if not igdb_configured:
            tk.Label(igdb_status_frame, text=" → 可在主界面「🎮 管理 IGDB API 凭证」中配置",
                     font=("微软雅黑", 8), fg="#888").pack(side="left")

        # 类型列表容器（使用 Canvas 支持滚动）
        igdb_list_container = tk.Frame(igdb_frame)
        igdb_list_container.pack(fill="x", pady=(5, 0))

        igdb_canvas = tk.Canvas(igdb_list_container, height=120, highlightthickness=1, highlightbackground="#ccc")
        igdb_scrollbar = ttk.Scrollbar(igdb_list_container, orient="vertical", command=igdb_canvas.yview)
        igdb_scrollable_frame = tk.Frame(igdb_canvas)

        igdb_scrollable_frame.bind(
            "<Configure>",
            lambda e: igdb_canvas.configure(scrollregion=igdb_canvas.bbox("all"))
        )

        igdb_canvas.create_window((0, 0), window=igdb_scrollable_frame, anchor="nw")
        igdb_canvas.configure(yscrollcommand=igdb_scrollbar.set)

        igdb_canvas.pack(side="left", fill="both", expand=True)
        igdb_scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮绑定
        def _igdb_mousewheel(event):
            igdb_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

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
                genres, error = self.core.fetch_igdb_genres()

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
                            row_frame.pack(fill="x", pady=1)

                        genre_id = genre.get('id')
                        genre_name = genre.get('name', '未知')
                        key = f"igdb_genre_{genre_id}"

                        var = tk.BooleanVar(value=False)
                        igdb_check_vars[key] = (var, "igdb_genre", genre_id, f"🏷️ {genre_name}")

                        cb = tk.Checkbutton(row_frame, text=genre_name, variable=var,
                                            font=("微软雅黑", 9), width=18, anchor="w")
                        cb.pack(side="left", padx=2)

                    # 更新滚动区域
                    igdb_scrollable_frame.update_idletasks()
                    igdb_canvas.configure(scrollregion=igdb_canvas.bbox("all"))

                rec_win.after(0, update_ui)

            threading.Thread(target=fetch_genres_thread, daemon=True).start()

        # IGDB 按钮区域
        igdb_btn_frame = tk.Frame(igdb_frame)
        igdb_btn_frame.pack(fill="x", pady=(5, 0))

        tk.Button(igdb_btn_frame, text="📋 加载类型列表", command=load_igdb_genres,
                  font=("微软雅黑", 8), state="normal" if igdb_configured else "disabled").pack(side="left",
                                                                                                padx=(0, 5))

        def select_all_igdb():
            for k, v in igdb_check_vars.items():
                v[0].set(True)

        def deselect_all_igdb():
            for k, v in igdb_check_vars.items():
                v[0].set(False)

        tk.Button(igdb_btn_frame, text="☑️ 全选类型", command=select_all_igdb, font=("微软雅黑", 8)).pack(side="left",
                                                                                                          padx=(0, 5))
        tk.Button(igdb_btn_frame, text="☐ 取消全选类型", command=deselect_all_igdb, font=("微软雅黑", 8)).pack(
            side="left", padx=(0, 5))

        def force_rescan_igdb():
            """从 IGDB 重新下载所有 Steam 游戏及分类数据"""
            if not igdb_configured:
                messagebox.showwarning("提示", "请先在主界面配置 IGDB API 凭证。")
                return

            if is_fetching[0]:
                messagebox.showwarning("提示", "正在执行其他操作，请稍候。")
                return

            if not messagebox.askyesno("重新下载 IGDB 数据",
                                       "将从 IGDB 重新下载所有 Steam 游戏及分类数据到本地。\n\n"
                                       "约需 5-8 分钟，期间请勿关闭窗口。\n\n"
                                       "确认开始？"):
                return

            is_fetching[0] = True
            for btn in btn_widgets:
                btn.config(state="disabled")

            cancel_flag = [False]

            def rebuild_thread():
                def progress_cb(current, total, phase, detail):
                    def _up():
                        status_var.set(phase)
                        detail_var.set(detail)
                        # 真进度条：total>0 表示已知总量
                        if total > 0:
                            progress_bar.config(mode='determinate', maximum=total)
                            progress_bar['value'] = current
                        else:
                            if str(progress_bar.cget('mode')) != 'indeterminate':
                                progress_bar.config(mode='indeterminate')
                                progress_bar.start(15)

                    rec_win.after(0, _up)

                def show():
                    progress_bar.config(mode='determinate', maximum=100, value=0)
                    progress_bar.pack(padx=20, pady=(5, 0), fill="x")
                    detail_label.pack(padx=20, anchor="w")

                rec_win.after(0, show)

                _, error = self.core.build_igdb_full_cache(progress_cb, cancel_flag)

                def done():
                    is_fetching[0] = False
                    progress_bar.stop()
                    progress_bar.pack_forget()
                    detail_label.pack_forget()
                    detail_var.set("")
                    for btn in btn_widgets:
                        btn.config(state="normal")
                    refresh_igdb_cache_status()
                    if error:
                        status_var.set(f"❌ 下载失败：{error}")
                    else:
                        status_var.set("✅ IGDB 数据下载完成！")

                rec_win.after(0, done)

            threading.Thread(target=rebuild_thread, daemon=True).start()

        tk.Button(igdb_btn_frame, text="🔄 重新下载 IGDB 数据", command=force_rescan_igdb,
                  font=("微软雅黑", 8), state="normal" if igdb_configured else "disabled").pack(side="left")

        # 缓存状态信息
        igdb_cache_var = tk.StringVar()
        igdb_cache_label = tk.Label(igdb_frame, textvariable=igdb_cache_var, font=("微软雅黑", 8), fg="#666")
        igdb_cache_label.pack(anchor="w", pady=(3, 0))

        def refresh_igdb_cache_status():
            summary = self.core.get_igdb_cache_summary()
            if summary:
                age_hours = (time.time() - summary['newest_at']) / 3600
                if age_hours < 24:
                    age_str = f"{age_hours:.0f} 小时前"
                else:
                    age_str = f"{age_hours / 24:.1f} 天前"
                if summary.get('is_full_dump'):
                    igdb_cache_var.set(
                        f"💾 已下载：{summary['total_steam_games']} 个 Steam 游戏，{summary['total_genres']} 个类型（{age_str}更新）")
                else:
                    igdb_cache_var.set(
                        f"💾 已缓存：{summary['total_genres']} 个类型，共 {summary['total_games']} 个游戏（{age_str}更新）")
                igdb_cache_label.config(fg="#2e7d32")
            else:
                igdb_cache_var.set("💾 尚未下载（首次使用时自动下载，约 5-8 分钟）")
                igdb_cache_label.config(fg="#888")

        refresh_igdb_cache_status()

        # 提示信息
        tk.Label(igdb_frame,
                 text="💡 首次使用时会自动从 IGDB 下载所有 Steam 游戏的分类数据（约 5-8 分钟），之后筛选均为本地秒查",
                 font=("微软雅黑", 8), fg="#666", wraplength=500, justify="left").pack(anchor="w", pady=(3, 0))

        # ===== 状态显示 =====
        status_var = tk.StringVar(value="请勾选要获取的来源，然后点击下方按钮。")
        status_label = tk.Label(rec_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray")
        status_label.pack(padx=20, pady=(10, 0), anchor="w")

        # 进度条
        progress_bar = ttk.Progressbar(rec_win, length=400, mode='indeterminate')
        progress_bar.pack(padx=20, pady=(5, 0), fill="x")
        progress_bar.pack_forget()

        # 详细状态
        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(rec_win, textvariable=detail_var, font=("微软雅黑", 8), fg="#888")
        detail_label.pack(padx=20, anchor="w")
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
                btn.config(state="disabled")

            def fetch_thread():
                fetched_data.clear()
                total = len(selected)

                # 显示进度条
                def show_progress():
                    progress_bar.pack(padx=20, pady=(5, 0), fill="x")
                    detail_label.pack(padx=20, anchor="w")
                    progress_bar.start(15)

                rec_win.after(0, show_progress)

                for i, (key, src_type, url_or_id, name) in enumerate(selected):
                    def update_status(msg, detail=""):
                        def _up():
                            status_var.set(msg)
                            if detail:
                                detail_var.set(detail)

                        rec_win.after(0, _up)

                    update_status(f"正在获取 [{i + 1}/{total}]: {name}...")

                    if src_type == "steam250":
                        # Steam250 抓取
                        ids, error = self.protected_fetch_steam250_ids(url_or_id)
                        if error:
                            update_status(f"❌ {name}: {error}")
                        else:
                            fetched_data[key] = {'ids': ids, 'name': name}
                            update_status(f"✅ {name}: 获取 {len(ids)} 个游戏")

                    elif src_type == "curator":
                        # 鉴赏家抓取（使用现有的多语言扫描功能）
                        page_type, identifier = self.core.extract_steam_list_info(url_or_id)
                        if page_type and identifier:
                            def progress_cb(fetched, total_count, phase, detail):
                                update_status(f"正在获取 [{i + 1}/{total}]: {name} ({phase})", detail)

                            # 获取已保存的 Cookie
                            login_cookies = None
                            saved_cookie = self.core.get_saved_cookie()
                            if saved_cookie:
                                login_cookies = f"steamLoginSecure={saved_cookie}"

                            ids, display_name, error, has_login = self.core.fetch_steam_list(
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
                            update_status(f"正在获取 [{i + 1}/{total}]: {name} ({phase})", detail)

                        ids, error = self.core.fetch_igdb_games_by_genre(genre_id, genre_name, igdb_progress_cb,
                                                                     force_refresh=igdb_force_refresh[0])

                        if error:
                            update_status(f"❌ {name}: {error}")
                        else:
                            fetched_data[key] = {'ids': ids, 'name': name}
                            # 检查是否来自缓存
                            cached_ids, cached_at = self.core.get_igdb_genre_cache(genre_id)
                            if not igdb_force_refresh[0] and cached_ids is not None and self.core.is_igdb_cache_valid(
                                    cached_at):
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
                        btn.config(state="normal")

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
                                    bg=name_win.cget("bg"), relief="flat", fg="#666")
                hint_text.insert("end",
                                 "💡 修改下方文本框中的名称即可自定义收藏夹名称。\n程序会自动添加后缀「(删除这段字以触发云同步)」。")
                hint_text.config(state="disabled")
                hint_text.pack(padx=20, fill="x")

                # 名称编辑区域
                edit_frame = tk.Frame(name_win)
                edit_frame.pack(fill="both", expand=True, padx=20, pady=10)

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
                    row_frame.pack(fill="x", pady=3)

                    tk.Label(row_frame, text=f"📦 {len(d['ids'])} 个游戏 →",
                             font=("微软雅黑", 9), width=15, anchor="e").pack(side="left")

                    name_var = tk.StringVar(value=d['name'])
                    entry = tk.Entry(row_frame, textvariable=name_var, width=35, font=("微软雅黑", 9))
                    entry.pack(side="left", padx=5)
                    name_entries[key] = name_var

                def confirm_create():
                    # 使用用户编辑后的名称创建收藏夹
                    for key, d in fetched_data.items():
                        new_name = name_entries[key].get().strip()
                        if new_name:
                            self.protected_add_static_collection(data, new_name, d['ids'])
                    self.core.save_json(data, backup_description="从个人推荐分类创建收藏夹")
                    messagebox.showinfo("成功", f"已创建 {len(fetched_data)} 个收藏夹。" + self.disclaimer)
                    name_win.destroy()
                    rec_win.destroy()

                btn_row = tk.Frame(name_win)
                btn_row.pack(pady=15)
                tk.Button(btn_row, text="✅ 确认创建", command=confirm_create, width=15).pack(side="left", padx=10)
                tk.Button(btn_row, text="取消", command=name_win.destroy, width=10).pack(side="left", padx=10)

            fetch_and_execute('create', create_action)

        def do_export():
            # 先选择目录，再获取数据
            dest_dir = filedialog.askdirectory(initialdir=self.core.current_dir, title="选择保存文件夹")
            if not dest_dir:
                return

            def export_action():
                for key, d in fetched_data.items():
                    safe_name = self.core.sanitize_filename(d['name'])
                    with open(os.path.join(dest_dir, f"{safe_name}.txt"), 'w', encoding='utf-8') as f:
                        for aid in d['ids']:
                            f.write(f"{aid}\n")
                messagebox.showinfo("成功", f"已导出 {len(fetched_data)} 个文件。")

            fetch_and_execute('export', export_action)

        def do_update():
            all_cols = self.core.get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return

            def update_action():
                sources = {}
                for key, d in fetched_data.items():
                    sources[key] = {"name": d['name'], "ids": d['ids']}

                def on_done():
                    self.core.save_json(data, backup_description="从个人推荐分类更新收藏夹")
                    rec_win.destroy()

                self.protected_show_batch_update_mapping(data, all_cols, sources, on_done,
                                                         parent_to_close=rec_win,
                                                         saved_mappings_key="recommend_update_mappings")

            fetch_and_execute('update', update_action)

        # 按钮排列顺序遵守规范：[导入]、[导出]、[更新]
        btn1 = tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15)
        btn1.pack(side="left", padx=5)
        btn_widgets.append(btn1)

        btn2 = tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export, width=18)
        btn2.pack(side="left", padx=5)
        btn_widgets.append(btn2)

        btn3 = tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15)
        btn3.pack(side="left", padx=5)
        btn_widgets.append(btn3)

    # --- SteamDB 列表导入界面 ---
    def steamdb_sync_ui(self):
        data = self.core.load_json()
        if data is None: return

        merged_ids = []
        merge_stats = []

        db_win = tk.Toplevel()
        db_win.title("从 SteamDB 列表页面获取游戏")
        db_win.attributes("-topmost", True)

        tk.Label(db_win,
                 text="使用指南：\n1. 在浏览器打开 SteamDB 列表页面，右键 →「另存为」保存完整网页源代码。\n2. 如需合并多个列表，重复保存即可。\n3. 点击下方按钮选择所有已保存的 HTML 文件。",
                 justify="left", font=("微软雅黑", 9), wraplength=500).pack(padx=20, pady=(15, 5))

        status_var = tk.StringVar(value="尚未选择文件。")
        status_label = tk.Label(db_win, textvariable=status_var, font=("微软雅黑", 9), fg="gray")
        status_label.pack(padx=20, anchor="w")

        name_var = tk.StringVar(value="SteamDB List")
        name_frame = tk.Frame(db_win)
        name_frame.pack(fill="x", padx=20, pady=(10, 0))
        tk.Label(name_frame, text="收藏夹 / 文件名称：", font=("微软雅黑", 9)).pack(side="left")
        name_entry = tk.Entry(name_frame, textvariable=name_var, width=35, font=("微软雅黑", 9))
        name_entry.pack(side="left", padx=5)

        def do_select_files():
            nonlocal merged_ids, merge_stats
            file_paths = filedialog.askopenfilenames(
                initialdir=self.core.current_dir, title="选择 SteamDB 源代码文件 (可多选)",
                filetypes=[("HTML files", "*.html"), ("Text files", "*.txt"), ("All files", "*.*")]
            )
            if not file_paths: return

            all_raw_ids = []
            merge_stats.clear()
            for path in file_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    page_ids = self.core.extract_ids_from_steamdb_html(content)
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
                status_var.set(
                    f"✅ 已从 {len(file_paths)} 个文件中提取并合并 {len(merged_ids)} 个唯一 AppID（原始 {len(all_raw_ids)} 个）。")
                status_label.config(fg="green")
                if len(file_paths) == 1:
                    name_var.set(os.path.splitext(os.path.basename(file_paths[0]))[0])
            else:
                status_var.set("❌ 所选文件中均未提取到有效的 AppID。")
                status_label.config(fg="red")

        select_lbl = tk.Label(db_win, text="📂 选择 SteamDB HTML 文件（可多选合并）",
                              font=("微软雅黑", 10, "bold"), bg="#4a90d9", fg="white",
                              padx=15, pady=8, cursor="hand2", relief="raised", bd=1)
        select_lbl.pack(pady=10)
        select_lbl.bind("<Enter>", lambda e: select_lbl.config(relief="groove"))
        select_lbl.bind("<Leave>", lambda e: select_lbl.config(relief="raised"))
        select_lbl.bind("<Button-1>", lambda e: do_select_files())

        def do_create():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            name = simpledialog.askstring("新建收藏夹", "请输入收藏夹名称：", initialvalue=name_var.get())
            if name:
                self.protected_add_static_collection(data, name, list(merged_ids))
                self.core.save_json(data, backup_description=f"从 SteamDB 创建收藏夹: {name}")
                detail = '\n'.join(merge_stats)
                messagebox.showinfo("录入成功",
                                    f"已建立新收藏夹。本次共录入 {len(merged_ids)} 个 AppID。\n\n各文件明细：\n{detail}" + self.disclaimer)
                db_win.destroy()

        def do_export_txt():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            name = simpledialog.askstring("导出设置", "请输入生成的 TXT 文件名：",
                                          initialvalue=self.core.sanitize_filename(name_var.get()))
            if not name: return
            save_path = filedialog.asksaveasfilename(initialdir=self.core.current_dir, title="保存 AppID 列表",
                                                     defaultextension=".txt",
                                                     initialfile=f"{self.core.sanitize_filename(name)}.txt",
                                                     filetypes=[("Text files", "*.txt")])
            if save_path:
                with open(save_path, 'w', encoding='utf-8') as f:
                    for aid in merged_ids: f.write(f"{aid}\n")
                detail = '\n'.join(merge_stats)
                messagebox.showinfo("成功",
                                    f"已成功导出 {len(merged_ids)} 个 AppID。\n\n各文件明细：\n{detail}" + self.disclaimer)

        def do_update():
            if not merged_ids: messagebox.showwarning("错误", "请先选择文件并提取 AppID。"); return
            all_cols = self.core.get_all_collections_with_refs(data)
            if not all_cols:
                messagebox.showwarning("提示", "未找到任何收藏夹。")
                return
            sources = {"SteamDB 列表": {"name": "SteamDB 列表", "ids": list(merged_ids)}}

            def on_done():
                self.core.save_json(data, backup_description="从 SteamDB 更新收藏夹")
                db_win.destroy()

            self.protected_show_batch_update_mapping(data, all_cols, sources, on_done, parent_to_close=db_win)

        btn_frame = tk.Frame(db_win)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="📁 建立为新收藏夹", command=do_create, width=15).pack(side="left", padx=5)
        tk.Button(btn_frame, text="📥 导出为 TXT 文件", command=do_export_txt, width=18).pack(side="left", padx=5)
        tk.Button(btn_frame, text="🔄️ 更新现有收藏夹", command=do_update, width=15).pack(side="left", padx=5)

    # ==================== 备份管理界面 ====================
    def open_backup_manager_ui(self):
        """打开备份管理界面"""
        if not self.core.backup_manager:
            messagebox.showerror("错误", "请先选择一个 Steam 账号。")
            return

        bk_win = tk.Toplevel()
        bk_win.title("管理收藏夹备份")
        bk_win.attributes("-topmost", True)

        # 当前账号信息
        account_frame = tk.Frame(bk_win, bg="#f0f0f0", pady=8)
        account_frame.pack(fill="x")
        tk.Label(account_frame,
                 text=f"📂 当前账号: {self.core.current_account['persona_name']} ({self.core.current_account['friend_code']})",
                 font=("微软雅黑", 10, "bold"), bg="#f0f0f0").pack(side="left", padx=15)

        # 当前文件信息
        current_frame = tk.LabelFrame(bk_win, text="📄 当前使用的文件", font=("微软雅黑", 10, "bold"), padx=10, pady=10)
        current_frame.pack(fill="x", padx=15, pady=(10, 5))

        if os.path.exists(self.core.json_path):
            file_size = os.path.getsize(self.core.json_path)
            file_mtime = datetime.fromtimestamp(os.path.getmtime(self.core.json_path))

            # 统计收藏夹数量
            try:
                data = self.core.load_json()
                statics = self.core.get_static_collections(data) if data else []
                col_count = len(statics)
            except:
                col_count = "?"

            info_text = f"路径: {self.core.json_path}\n大小: {file_size:,} 字节 | 修改时间: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')} | 收藏夹数: {col_count}"
            tk.Label(current_frame, text=info_text, font=("微软雅黑", 9), justify="left", wraplength=650).pack(
                anchor="w")

        # 手动创建备份
        manual_frame = tk.Frame(bk_win)
        manual_frame.pack(fill="x", padx=15, pady=5)

        desc_var = tk.StringVar(value="")
        tk.Label(manual_frame, text="备份描述（可选）:", font=("微软雅黑", 9)).pack(side="left")
        desc_entry = tk.Entry(manual_frame, textvariable=desc_var, width=30, font=("微软雅黑", 9))
        desc_entry.pack(side="left", padx=5)

        def do_manual_backup():
            desc = desc_var.get().strip()
            backup_path = self.core.backup_manager.create_backup(description=desc if desc else "手动备份")
            if backup_path:
                messagebox.showinfo("成功", f"✅ 备份已创建:\n{os.path.basename(backup_path)}")
                refresh_backup_list()
            else:
                messagebox.showerror("错误", "❌ 备份创建失败。")

        tk.Button(manual_frame, text="💾 立即创建备份", command=do_manual_backup, font=("微软雅黑", 9)).pack(side="left",
                                                                                                            padx=10)

        # 备份列表
        list_frame = tk.LabelFrame(bk_win, text="📚 备份历史", font=("微软雅黑", 10, "bold"), padx=10, pady=10)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

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

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def refresh_backup_list():
            for item in tree.get_children():
                tree.delete(item)

            backups = self.core.backup_manager.list_backups()
            for b in backups:
                size_str = f"{b['size']:,} B"
                if b['size'] > 1024:
                    size_str = f"{b['size'] / 1024:.1f} KB"
                tree.insert("", "end", values=(
                    b['filename'],
                    b['created_at'].strftime("%Y-%m-%d %H:%M:%S"),
                    size_str,
                    b['description']
                ))

        refresh_backup_list()

        # 操作按钮
        btn_frame = tk.Frame(bk_win)
        btn_frame.pack(fill="x", padx=15, pady=10)

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
                if self.core.backup_manager.restore_backup(filename):
                    messagebox.showinfo("成功", "✅ 已成功恢复备份！")
                    refresh_backup_list()
                else:
                    messagebox.showerror("错误", "❌ 恢复失败。")

        def do_delete():
            filename = get_selected_backup()
            if not filename:
                return
            if messagebox.askyesno("确认删除", f"确定要删除此备份吗？\n\n{filename}\n\n此操作不可恢复。"):
                if self.core.backup_manager.delete_backup(filename):
                    messagebox.showinfo("成功", "✅ 备份已删除。")
                    refresh_backup_list()
                else:
                    messagebox.showerror("错误", "❌ 删除失败。")

        tk.Button(btn_frame, text="🔍 查看差异", command=do_view_diff, width=12, font=("微软雅黑", 9)).pack(side="left",
                                                                                                           padx=5)
        tk.Button(btn_frame, text="⏪ 恢复此备份", command=do_restore, width=12, font=("微软雅黑", 9)).pack(side="left",
                                                                                                           padx=5)
        tk.Button(btn_frame, text="🗑 删除备份", command=do_delete, width=12, font=("微软雅黑", 9)).pack(side="left",
                                                                                                        padx=5)
        tk.Button(btn_frame, text="🔄 刷新列表", command=refresh_backup_list, width=12, font=("微软雅黑", 9)).pack(
            side="right", padx=5)

    def _show_diff_window(self, backup_filename):
        """显示备份与当前文件的差异详情"""
        diff_result = self.core.backup_manager.compare_with_current(backup_filename)

        if 'error' in diff_result:
            messagebox.showerror("错误", f"比较失败: {diff_result['error']}")
            return

        diff_win = tk.Toplevel()
        diff_win.title(f"差异对比: {backup_filename} ↔ 当前文件")
        diff_win.attributes("-topmost", True)

        # 摘要信息
        summary = diff_result['summary']
        summary_frame = tk.Frame(diff_win, bg="#e8f4f8", pady=10)
        summary_frame.pack(fill="x")

        summary_text = f"📊 变化摘要:  新增 {summary['total_added']} 个收藏夹  |  删除 {summary['total_removed']} 个  |  修改 {summary['total_modified']} 个  |  未变 {summary['total_unchanged']} 个"
        tk.Label(summary_frame, text=summary_text, font=("微软雅黑", 10, "bold"), bg="#e8f4f8").pack()

        # 创建 Notebook 用于分类显示
        notebook = ttk.Notebook(diff_win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- 新增的收藏夹 ---
        if diff_result['added_collections']:
            added_frame = tk.Frame(notebook)
            notebook.add(added_frame, text=f"➕ 新增 ({len(diff_result['added_collections'])})")

            added_text = tk.Text(added_frame, font=("微软雅黑", 9), wrap="word")
            added_scroll = ttk.Scrollbar(added_frame, orient="vertical", command=added_text.yview)
            added_text.configure(yscrollcommand=added_scroll.set)
            added_text.pack(side="left", fill="both", expand=True)
            added_scroll.pack(side="right", fill="y")

            added_text.tag_config("title", foreground="#2e7d32", font=("微软雅黑", 10, "bold"))
            added_text.tag_config("info", foreground="#666")

            for col in diff_result['added_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                added_text.insert("end", f"• {col['name']}\n", "title")
                added_text.insert("end", f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")

            added_text.config(state="disabled")

        # --- 删除的收藏夹 ---
        if diff_result['removed_collections']:
            removed_frame = tk.Frame(notebook)
            notebook.add(removed_frame, text=f"➖ 删除 ({len(diff_result['removed_collections'])})")

            removed_text = tk.Text(removed_frame, font=("微软雅黑", 9), wrap="word")
            removed_scroll = ttk.Scrollbar(removed_frame, orient="vertical", command=removed_text.yview)
            removed_text.configure(yscrollcommand=removed_scroll.set)
            removed_text.pack(side="left", fill="both", expand=True)
            removed_scroll.pack(side="right", fill="y")

            removed_text.tag_config("title", foreground="#c62828", font=("微软雅黑", 10, "bold"))
            removed_text.tag_config("info", foreground="#666")

            for col in diff_result['removed_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                removed_text.insert("end", f"• {col['name']}\n", "title")
                removed_text.insert("end", f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")

            removed_text.config(state="disabled")

        # --- 修改的收藏夹 ---
        if diff_result['modified_collections']:
            modified_frame = tk.Frame(notebook)
            notebook.add(modified_frame, text=f"✏️ 修改 ({len(diff_result['modified_collections'])})")

            modified_text = tk.Text(modified_frame, font=("微软雅黑", 9), wrap="word")
            modified_scroll = ttk.Scrollbar(modified_frame, orient="vertical", command=modified_text.yview)
            modified_text.configure(yscrollcommand=modified_scroll.set)
            modified_text.pack(side="left", fill="both", expand=True)
            modified_scroll.pack(side="right", fill="y")

            modified_text.tag_config("title", foreground="#1565c0", font=("微软雅黑", 10, "bold"))
            modified_text.tag_config("name_change", foreground="#6a1b9a")
            modified_text.tag_config("added", foreground="#2e7d32")
            modified_text.tag_config("removed", foreground="#c62828")
            modified_text.tag_config("info", foreground="#666")

            for col in diff_result['modified_collections']:
                # 收藏夹名称
                if col['name_changed']:
                    modified_text.insert("end", f"• {col['old_name']} → {col['new_name']}\n", "name_change")
                else:
                    modified_text.insert("end", f"• {col['new_name']}\n", "title")

                # 游戏数变化
                modified_text.insert("end", f"   游戏数: {col['old_game_count']} → {col['new_game_count']}\n", "info")

                # 新增的游戏
                if col['added_games']:
                    added_preview = col['added_games'][:10]
                    modified_text.insert("end", f"   ➕ 新增 {len(col['added_games'])} 个: ", "added")
                    modified_text.insert("end", f"{', '.join(map(str, added_preview))}")
                    if len(col['added_games']) > 10:
                        modified_text.insert("end", f" ... 等")
                    modified_text.insert("end", "\n")

                # 移除的游戏
                if col['removed_games']:
                    removed_preview = col['removed_games'][:10]
                    modified_text.insert("end", f"   ➖ 移除 {len(col['removed_games'])} 个: ", "removed")
                    modified_text.insert("end", f"{', '.join(map(str, removed_preview))}")
                    if len(col['removed_games']) > 10:
                        modified_text.insert("end", f" ... 等")
                    modified_text.insert("end", "\n")

                modified_text.insert("end", "\n")

            modified_text.config(state="disabled")

        # --- 未变化的收藏夹 ---
        if diff_result['unchanged_collections']:
            unchanged_frame = tk.Frame(notebook)
            notebook.add(unchanged_frame, text=f"⚪ 未变 ({len(diff_result['unchanged_collections'])})")

            unchanged_text = tk.Text(unchanged_frame, font=("微软雅黑", 9), wrap="word")
            unchanged_scroll = ttk.Scrollbar(unchanged_frame, orient="vertical", command=unchanged_text.yview)
            unchanged_text.configure(yscrollcommand=unchanged_scroll.set)
            unchanged_text.pack(side="left", fill="both", expand=True)
            unchanged_scroll.pack(side="right", fill="y")

            unchanged_text.tag_config("title", foreground="#666", font=("微软雅黑", 9))
            unchanged_text.tag_config("info", foreground="#999")

            for col in diff_result['unchanged_collections']:
                col_type = "🔄 动态" if col['is_dynamic'] else "📁 静态"
                unchanged_text.insert("end", f"• {col['name']}\n", "title")
                unchanged_text.insert("end", f"   {col_type} | 游戏数: {col['game_count']}\n\n", "info")

            unchanged_text.config(state="disabled")

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
        guide_frame.pack(fill="x", padx=20, pady=(15, 10))

        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=5, bg=cookie_win.cget("bg"),
                             relief="flat", wrap="word")
        guide_text.tag_config("bold", font=("微软雅黑", 9, "bold"))
        guide_text.tag_config("orange", foreground="orange")
        guide_text.insert("end", "Cookie 的用途：\n", "bold")
        guide_text.insert("end", "配置 Steam 登录态 Cookie 后，从鉴赏家列表获取游戏时可以获得")
        guide_text.insert("end", "完整的列表", "orange")
        guide_text.insert("end", "。\n\n未配置 Cookie 时，部分被 Steam 限制的内容可能无法获取。")
        guide_text.config(state="disabled")
        guide_text.pack(fill="x")

        # 当前状态
        status_frame = tk.Frame(cookie_win)
        status_frame.pack(fill="x", padx=20, pady=(0, 10))

        saved_cookie = self.core.get_saved_cookie()
        if saved_cookie:
            status_label = tk.Label(status_frame, text="🔐 当前状态：已配置 Cookie",
                                    font=("微软雅黑", 10, "bold"), fg="green")
        else:
            status_label = tk.Label(status_frame, text="⚠️ 当前状态：未配置 Cookie",
                                    font=("微软雅黑", 10, "bold"), fg="orange")
        status_label.pack(anchor="w")

        # 获取方法说明
        help_frame = tk.LabelFrame(cookie_win, text="📖 获取 Cookie 的方法",
                                   font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        help_frame.pack(fill="x", padx=20, pady=(0, 10))

        help_text = """1. 用浏览器登录 store.steampowered.com
2. 按 F12 打开开发者工具
3. 切换到 Application（应用程序）标签页
4. 左侧找到 Cookies → store.steampowered.com
5. 找到 steamLoginSecure，复制其 Value 值"""

        tk.Label(help_frame, text=help_text, font=("微软雅黑", 9), justify="left").pack(anchor="w")

        # Cookie 输入区域
        input_frame = tk.LabelFrame(cookie_win, text="🔑 输入 Cookie",
                                    font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        input_frame.pack(fill="x", padx=20, pady=(0, 10))

        cookie_var = tk.StringVar(value=saved_cookie)
        cookie_entry = tk.Entry(input_frame, textvariable=cookie_var, width=60, font=("微软雅黑", 9), show="•")
        cookie_entry.pack(fill="x", pady=(0, 8))

        # 按钮行
        btn_frame = tk.Frame(input_frame)
        btn_frame.pack(fill="x")

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
                self.core.save_cookie(val)
                status_label.config(text="🔐 当前状态：已配置 Cookie", fg="green")
                messagebox.showinfo("保存成功", "✅ Cookie 已保存！\n\n此 Cookie 将用于所有鉴赏家列表的获取。")
            else:
                messagebox.showwarning("提示", "请先输入 Cookie 值。")

        def clear_cookie():
            if messagebox.askyesno("确认清除", "确定要清除已保存的 Cookie 吗？"):
                cookie_var.set("")
                self.core.clear_saved_cookie()
                status_label.config(text="⚠️ 当前状态：未配置 Cookie", fg="orange")
                messagebox.showinfo("已清除", "Cookie 已清除。")

        show_btn = tk.Button(btn_frame, text="👁 显示", command=toggle_show, font=("微软雅黑", 9), width=10)
        show_btn.pack(side="left", padx=(0, 8))
        tk.Button(btn_frame, text="💾 保存 Cookie", command=save_cookie, font=("微软雅黑", 9), width=15).pack(
            side="left", padx=8)
        tk.Button(btn_frame, text="🗑 清除 Cookie", command=clear_cookie, font=("微软雅黑", 9), width=15).pack(
            side="left", padx=8)

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
        guide_frame.pack(fill="x", padx=20, pady=(15, 10))

        guide_text = tk.Text(guide_frame, font=("微软雅黑", 9), height=4, bg=igdb_win.cget("bg"),
                             relief="flat", wrap="word")
        guide_text.tag_config("bold", font=("微软雅黑", 9, "bold"))
        guide_text.tag_config("purple", foreground="#7c3aed")
        guide_text.insert("end", "IGDB API 的用途：\n", "bold")
        guide_text.insert("end", "配置 IGDB API 凭证后，可以按")
        guide_text.insert("end", "游戏类型分类", "purple")
        guide_text.insert("end",
                          "获取游戏列表。\nIGDB（Internet Game Database）是一个综合性的游戏数据库，由 Twitch（Amazon）运营。")
        guide_text.config(state="disabled")
        guide_text.pack(fill="x")

        # 当前状态
        status_frame = tk.Frame(igdb_win)
        status_frame.pack(fill="x", padx=20, pady=(0, 10))

        saved_id, saved_secret = self.core.get_igdb_credentials()
        if saved_id and saved_secret:
            status_label = tk.Label(status_frame, text="🔐 当前状态：已配置 IGDB API 凭证",
                                    font=("微软雅黑", 10, "bold"), fg="green")
        else:
            status_label = tk.Label(status_frame, text="⚠️ 当前状态：未配置 IGDB API 凭证",
                                    font=("微软雅黑", 10, "bold"), fg="orange")
        status_label.pack(anchor="w")

        # 获取方法说明
        help_frame = tk.LabelFrame(igdb_win, text="📖 获取 IGDB API 凭证的方法",
                                   font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        help_frame.pack(fill="x", padx=20, pady=(0, 10))

        help_text = """1. 访问 https://dev.twitch.tv/console/apps 并登录 Twitch 账号
2. 点击「Register Your Application」注册一个应用
3. 名称随意，OAuth Redirect URLs 填写 http://localhost
4. 分类选择「Application Integration」
5. 创建后点击应用，复制 Client ID
6. 点击「New Secret」生成并复制 Client Secret"""

        tk.Label(help_frame, text=help_text, font=("微软雅黑", 9), justify="left").pack(anchor="w")

        # 输入区域
        input_frame = tk.LabelFrame(igdb_win, text="🔑 输入 API 凭证",
                                    font=("微软雅黑", 10, "bold"), padx=15, pady=10)
        input_frame.pack(fill="x", padx=20, pady=(0, 10))

        # Client ID
        id_row = tk.Frame(input_frame)
        id_row.pack(fill="x", pady=(0, 5))
        tk.Label(id_row, text="Client ID:", font=("微软雅黑", 9), width=12, anchor="e").pack(side="left")
        id_var = tk.StringVar(value=saved_id)
        id_entry = tk.Entry(id_row, textvariable=id_var, width=45, font=("微软雅黑", 9))
        id_entry.pack(side="left", padx=(5, 0))

        # Client Secret
        secret_row = tk.Frame(input_frame)
        secret_row.pack(fill="x", pady=(0, 8))
        tk.Label(secret_row, text="Client Secret:", font=("微软雅黑", 9), width=12, anchor="e").pack(side="left")
        secret_var = tk.StringVar(value=saved_secret)
        secret_entry = tk.Entry(secret_row, textvariable=secret_var, width=45, font=("微软雅黑", 9), show="•")
        secret_entry.pack(side="left", padx=(5, 0))

        # 按钮行
        btn_frame = tk.Frame(input_frame)
        btn_frame.pack(fill="x")

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
                self.core.save_igdb_credentials(cid, csecret)
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
            self.core.save_igdb_credentials(cid, csecret)

            # 测试获取令牌
            token, error = self.core.get_igdb_access_token(force_refresh=True)
            if error:
                messagebox.showerror("测试失败", f"❌ 无法获取访问令牌：\n\n{error}")
            else:
                messagebox.showinfo("测试成功", "✅ IGDB API 凭证有效！\n\n已成功获取访问令牌。")
                status_label.config(text="🔐 当前状态：已配置 IGDB API 凭证", fg="green")

        def clear_credentials():
            if messagebox.askyesno("确认清除", "确定要清除已保存的 IGDB API 凭证吗？"):
                id_var.set("")
                secret_var.set("")
                self.core.clear_igdb_credentials()
                status_label.config(text="⚠️ 当前状态：未配置 IGDB API 凭证", fg="orange")
                messagebox.showinfo("已清除", "IGDB API 凭证已清除。")

        show_btn = tk.Button(btn_frame, text="👁 显示", command=toggle_show, font=("微软雅黑", 9), width=8)
        show_btn.pack(side="left", padx=(0, 5))
        tk.Button(btn_frame, text="🔍 测试凭证", command=test_credentials, font=("微软雅黑", 9), width=12).pack(
            side="left", padx=5)
        tk.Button(btn_frame, text="💾 保存凭证", command=save_credentials, font=("微软雅黑", 9), width=12).pack(
            side="left", padx=5)
        tk.Button(btn_frame, text="🗑 清除凭证", command=clear_credentials, font=("微软雅黑", 9), width=12).pack(
            side="left", padx=5)

        # 安全提示
        tk.Label(igdb_win, text="⚠️ API 凭证包含敏感信息，请勿分享配置文件给他人",
                 font=("微软雅黑", 8), fg="red").pack(pady=(0, 15))

    # ==================== 主界面 ====================
    def main_ui(self):
        """启动主界面（含账号选择）"""
        # 扫描账号
        self.core.accounts = SteamAccountScanner.scan_accounts()

        if not self.core.accounts:
            # 未找到账号，显示提示
            root = tk.Tk()
            root.title("Steam 库管理助手")
            root.resizable(False, False)

            tk.Label(root, text="❌ 未找到 Steam 账号", font=("微软雅黑", 14, "bold"), fg="red").pack(pady=20)
            tk.Label(root,
                     text="请确保:\n1. Steam 已安装在默认路径\n2. 至少登录过一个 Steam 账号\n3. 账号目录中存在 cloud-storage-namespace-1.json 文件",
                     font=("微软雅黑", 10), justify="left").pack(padx=30, pady=10)

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

                    self.core.accounts = [{
                        'friend_code': friend_code,
                        'userdata_path': os.path.dirname(os.path.dirname(os.path.dirname(path))),
                        'json_path': path,
                        'persona_name': f"手动选择 ({friend_code})",
                        'steam_path': "",
                    }]
                    root.destroy()
                    self.show_account_selector()

            tk.Button(root, text="📂 手动选择文件", command=manual_select, font=("微软雅黑", 10)).pack(pady=20)

            root.update_idletasks()
            cw, ch = root.winfo_reqwidth(), root.winfo_reqheight()
            sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
            root.geometry(f"{cw}x{ch}+{int((sw - cw) / 2)}+{int((sh - ch) / 2)}")
            root.mainloop()
        elif len(self.core.accounts) == 1:
            # 只有一个账号，直接使用
            self.core.set_current_account(self.core.accounts[0])
            self.show_main_window()
        else:
            # 多个账号，显示选择界面
            self.show_account_selector()

    def show_account_selector(self):
        """显示账号选择界面"""
        sel_root = tk.Tk()
        sel_root.title("选择 Steam 账号")
        sel_root.resizable(False, False)

        tk.Label(sel_root, text="🎮 检测到多个 Steam 账号", font=("微软雅黑", 12, "bold")).pack(pady=(20, 10))
        tk.Label(sel_root, text="请选择要管理的账号：", font=("微软雅黑", 10)).pack()

        list_frame = tk.Frame(sel_root)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)

        listbox = tk.Listbox(list_frame, width=60, height=10, font=("微软雅黑", 10))
        listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.config(yscrollcommand=scrollbar.set)

        for acc in self.core.accounts:
            listbox.insert("end", f"{acc['persona_name']} (好友代码: {acc['friend_code']})")

        if self.core.accounts:
            listbox.selection_set(0)

        def on_select():
            selected = listbox.curselection()
            if not selected:
                messagebox.showwarning("提示", "请选择一个账号。")
                return
            self.core.set_current_account(self.core.accounts[selected[0]])
            sel_root.destroy()
            self.show_main_window()

        tk.Button(sel_root, text="✅ 确认选择", command=on_select, font=("微软雅黑", 10), width=15).pack(pady=15)

        sel_root.update_idletasks()
        cw, ch = sel_root.winfo_reqwidth(), sel_root.winfo_reqheight()
        sw, sh = sel_root.winfo_screenwidth(), sel_root.winfo_screenheight()
        sel_root.geometry(f"{cw}x{ch}+{int((sw - cw) / 2)}+{int((sh - ch) / 2)}")
        sel_root.mainloop()

    def show_main_window(self):
        """显示主功能窗口"""
        root = tk.Tk()
        root.title("Steam 库管理助手")
        root.resizable(False, False)

        # ====== 待保存更改追踪 ======
        self._pending_data = None  # 待保存的 data 对象
        self._has_pending_changes = False
        self._original_col_ids = set()  # 导入前已有的收藏夹 ID，用于标红新增项

        def mark_dirty(data):
            """标记有未保存的更改"""
            self._pending_data = data
            self._has_pending_changes = True
            save_btn.config(state="normal")
            save_indicator.config(text="⚠️ 有未保存的更改", fg="orange")

        def commit_save():
            """储存更改：备份当前分类，写入新分类"""
            if not self._has_pending_changes or self._pending_data is None:
                messagebox.showinfo("提示", "没有需要保存的更改。")
                return
            result = self.core.save_json(self._pending_data, backup_description="储存收藏夹更改")
            if result:
                self._has_pending_changes = False
                self._pending_data = None
                self._original_col_ids.clear()
                save_btn.config(state="disabled")
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
        account_frame.pack(fill="x")

        acc_info = f"👤 {self.core.current_account['persona_name']}  |  好友代码: {self.core.current_account['friend_code']}"
        tk.Label(account_frame, text=acc_info, font=("微软雅黑", 11, "bold"), bg="#4a90d9", fg="white").pack(
            side="left", padx=15)

        if len(self.core.accounts) > 1:
            def switch_account():
                if self._has_pending_changes:
                    ans = messagebox.askyesnocancel("未保存的更改", "您有未保存的更改。\n\n是否在切换账号前保存？")
                    if ans is None:
                        return
                    if ans:
                        commit_save()
                root.destroy()
                self.show_account_selector()

            tk.Button(account_frame, text="🔄 切换账号", command=switch_account, font=("微软雅黑", 9)).pack(side="right",
                                                                                                           padx=15)

        # ====== 主内容区（左侧收藏夹列表 + 右侧功能控制区） ======
        main_container = tk.Frame(root)
        main_container.pack(fill="both", expand=True)

        # ====== 左侧：收藏夹列表面板（仿 Steam 侧边栏） ======
        left_panel = tk.Frame(main_container, bg="#f0f0f0", padx=10, pady=10)
        left_panel.pack(side="left", fill="y", padx=(10, 0), pady=10)

        # 标题行：📂 当前收藏夹 + 💾 备份管理按钮 + 🔄 刷新按钮
        title_row = tk.Frame(left_panel, bg="#f0f0f0")
        title_row.pack(fill="x")
        tk.Label(title_row, text="📂 当前收藏夹", font=("微软雅黑", 11, "bold"), bg="#f0f0f0").pack(side="left")
        ttk.Button(title_row, text="💾 备份", width=7, command=self.open_backup_manager_ui).pack(side="right",
                                                                                                padx=(5, 0))
        ttk.Button(title_row, text="🔄", width=3, command=lambda: refresh_categories()).pack(side="right", padx=(5, 0))

        tk.Label(left_panel, text="（按字母顺序排列）", font=("微软雅黑", 9), fg="#666666", bg="#f0f0f0").pack(anchor="w")

        # 全选控制行
        select_ctrl_row = tk.Frame(left_panel, bg="#f0f0f0")
        select_ctrl_row.pack(fill="x", pady=(5, 0))
        select_all_var = tk.BooleanVar(value=False)

        def toggle_select_all():
            val = select_all_var.get()
            for var in checkbox_vars:
                var.set(val)

        tk.Checkbutton(select_ctrl_row, text="全选", variable=select_all_var, command=toggle_select_all,
                       bg="#f0f0f0", font=("微软雅黑", 9)).pack(side="left")

        # 选中计数
        selection_count_label = tk.Label(select_ctrl_row, text="", font=("微软雅黑", 8), fg="#888888", bg="#f0f0f0")
        selection_count_label.pack(side="right")

        # 分类列表框架
        list_container = tk.Frame(left_panel, bg="#f0f0f0")
        list_container.pack(fill="both", expand=True, pady=(5, 5))

        # 使用 Canvas + Frame 实现滚动
        canvas = tk.Canvas(list_container, bg="#ffffff", width=220, height=380, highlightthickness=1,
                           highlightbackground="#cccccc")
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#ffffff")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 让 scrollable_frame 宽度始终跟随 canvas 宽度，确保 fill="x" 和 side="right" 生效
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

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
                data = self.core.load_json()
            if data is None:
                tk.Label(scrollable_frame, text="❌ 无法读取配置文件", font=("微软雅黑", 9), fg="red", bg="#ffffff",
                         padx=10, pady=5).pack(anchor="w")
                return

            collections = self.core.get_all_collections_ordered(data)
            current_collections.extend(collections)

            if not collections:
                empty_label = tk.Label(scrollable_frame, text="所有分类为空", font=("微软雅黑", 10), fg="#999999",
                                       bg="#ffffff", padx=10, pady=20)
                empty_label.pack(anchor="center", expand=True)
            else:
                for i, col in enumerate(collections):
                    # 创建每个分类的显示项
                    item_frame = tk.Frame(scrollable_frame, bg="#ffffff")
                    item_frame.pack(fill="x", padx=2, pady=1)

                    # 复选框
                    var = tk.BooleanVar(value=False)
                    var.trace_add("write", update_selection_count)
                    checkbox_vars.append(var)

                    cb = tk.Checkbutton(item_frame, variable=var, bg="#ffffff", activebackground="#ffffff")
                    cb.pack(side="left")

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
                        name_fg = "#cc0000"  # 红色：未保存的新增
                    elif has_sync_suffix and not self._has_pending_changes:
                        name_fg = "#1a6dcc"  # 蓝色：已保存但仍带后缀
                    else:
                        name_fg = "#000000"  # 默认黑色

                    # 分类名称
                    name_text = f"{icon} {col_name}"
                    if len(name_text) > 20:
                        name_text = name_text[:18] + "..."

                    name_label = tk.Label(item_frame, text=name_text, font=("微软雅黑", 9),
                                          bg="#ffffff", fg=name_fg, anchor="w")
                    name_label.pack(side="left", fill="x", expand=True)
                    # 点击名称也可以切换选中状态
                    name_label.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

                    # 蓝色项添加提示：鼠标悬停时显示 tooltip
                    if has_sync_suffix and not self._has_pending_changes:
                        tip_text = "请在 Steam 内删去名称后缀以触发云同步"
                        name_label.bind("<Enter>",
                                        lambda e, lbl=name_label, t=tip_text: lbl.config(cursor="question_arrow"))
                        name_label.bind("<Leave>", lambda e, lbl=name_label: lbl.config(cursor=""))

                    # 游戏数量（仅静态收藏夹显示数量，动态收藏夹显示额外添加数）
                    if not col['is_dynamic']:
                        count_label = tk.Label(item_frame, text=f"({len(col['added'])})", font=("微软雅黑", 8),
                                               fg="#888888", bg="#ffffff")
                        count_label.pack(side="right")
                    elif col.get('added'):
                        count_label = tk.Label(item_frame, text=f"(+{len(col['added'])})", font=("微软雅黑", 8),
                                               fg="#aa88cc", bg="#ffffff")
                        count_label.pack(side="right")

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
        left_btn_frame.pack(fill="x", pady=(5, 0))

        # 储存更改按钮 + 状态指示
        save_row = tk.Frame(left_btn_frame, bg="#f0f0f0")
        save_row.pack(fill="x", pady=(2, 0))
        save_btn = ttk.Button(save_row, text="💾 储存更改", width=23, command=commit_save, state="disabled")
        save_btn.pack(fill="x")

        save_indicator = tk.Label(left_panel, text="", font=("微软雅黑", 8), bg="#f0f0f0")
        save_indicator.pack(anchor="w")

        # 初始加载分类列表
        refresh_categories()

        # ====== 右侧：功能控制区 ======
        right_panel = tk.Frame(main_container)
        right_panel.pack(side="left", fill="both", expand=True)

        # ====== 操作守则 ======
        instruction_frame = tk.Frame(right_panel, pady=15, padx=35)
        instruction_frame.pack(fill="x")

        t_top = tk.Text(instruction_frame, font=("微软雅黑", 10), height=8, bg=root.cget("bg"), relief="flat",
                        wrap="word")
        t_top.tag_config("red", foreground="red", font=("微软雅黑", 10, "bold"))
        t_top.tag_config("green", foreground="green", font=("微软雅黑", 10, "bold"))

        t_top.insert("end", "✅ 已自动定位到账号的收藏夹配置文件\n\n", "green")
        t_top.insert("end", "操作守则：\n一、导入前请")
        t_top.insert("end", "关闭", "red")
        t_top.insert("end", " Steam；\n二、导入或更新后需点击左侧")
        t_top.insert("end", "「💾 储存更改」", "red")
        t_top.insert("end", "才会写入文件，程序会自动创建备份；\n三、为了上传云端，您必须")
        t_top.insert("end", "在 Steam 内手动修改", "red")
        t_top.insert("end", "新收藏，如删去自动添加的名称后缀等。")
        t_top.config(state="disabled")
        t_top.pack(fill="x")

        style = ttk.Style()
        style.configure("TButton", font=("微软雅黑", 11), padding=8)

        # ====== 功能按钮 ======
        row1_frame = tk.Frame(right_panel, padx=35)
        row1_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(row1_frame, text="📁 批量导入", width=15, command=self.import_from_txt).pack(side="left",
                                                                                               padx=(0, 10))
        ttk.Button(row1_frame, text="📤 批量导出", width=15, command=self.export_static_collection).pack(side="left",
                                                                                                        padx=10)
        ttk.Button(row1_frame, text="🔄 批量更新", width=15, command=self.update_static_collection).pack(side="left",
                                                                                                        padx=10)

        d_row1 = tk.Text(right_panel, font=("微软雅黑", 9), height=5, bg=root.cget("bg"), relief="flat", padx=35)
        d_row1.tag_config("red", foreground="red")
        d_row1.insert("end", "• 导入：支持 ")
        d_row1.insert("end", "TXT（AppID 列表）", "red")
        d_row1.insert("end", " 或 ")
        d_row1.insert("end", "JSON（结构化收藏夹）", "red")
        d_row1.insert("end", "。\n• 导出：需先在左侧勾选收藏夹，支持合并 TXT / 多个 TXT / JSON 三种格式。\n")
        d_row1.insert("end", "• 更新：支持增量更新（追加 + 差异记录）或替换更新（直接覆盖）两种模式。")
        d_row1.config(state="disabled")
        d_row1.pack(fill="x", pady=5)

        ttk.Button(right_panel, text="👥 批量同步 Steam 用户游戏库", width=53, command=self.open_friend_sync_ui).pack(
            pady=(5, 0))
        d4 = tk.Text(right_panel, font=("微软雅黑", 9), height=2, bg=root.cget("bg"), relief="flat", padx=35)
        d4.tag_config("red", foreground="red")
        d4.insert("end", "• 对方必须")
        d4.insert("end", "公开", "red")
        d4.insert("end", "了库。好友代码可在其 SteamDB 页面获取。")
        d4.config(state="disabled")
        d4.pack(fill="x", pady=5)

        # ====== 两个并列的来源按钮（居中） ======
        source_row = tk.Frame(right_panel)
        source_row.pack(fill="x", pady=(5, 0))
        source_inner = tk.Frame(source_row)
        source_inner.pack(anchor="center")
        ttk.Button(source_inner, text="⭐ 从推荐来源获取", width=25, command=self.personal_recommend_ui).pack(
            side="left", padx=(0, 10))
        ttk.Button(source_inner, text="🌐 从其他来源获取", width=25, command=self.open_source_selection).pack(
            side="left")

        d5 = tk.Text(right_panel, font=("微软雅黑", 9), height=4, bg=root.cget("bg"), relief="flat", padx=35)
        d5.tag_config("purple", foreground="#7c3aed")
        d5.tag_config("blue", foreground="#5b9bd5")
        d5.insert("end", "• 推荐来源：")
        d5.insert("end", "Steam250 排行榜", "purple")
        d5.insert("end", " + ")
        d5.insert("end", "精选鉴赏家", "purple")
        d5.insert("end", " + ")
        d5.insert("end", "游戏类型分类（IGDB）", "purple")
        d5.insert("end", "\n")
        d5.insert("end", "• 其他来源：")
        d5.insert("end", "Steam 列表页面", "blue")
        d5.insert("end", "（鉴赏家/发行商）、")
        d5.insert("end", "SteamDB", "blue")
        d5.config(state="disabled")
        d5.pack(fill="x", pady=(5, 10))

        # ====== Cookie 和 IGDB API 并排 ======
        config_row = tk.Frame(right_panel)
        config_row.pack(fill="x", pady=(5, 0))
        config_inner = tk.Frame(config_row)
        config_inner.pack(anchor="center")
        ttk.Button(config_inner, text="🔑 管理 Cookie", width=25, command=self.open_cookie_manager_ui).pack(side="left",
                                                                                                           padx=(0, 10))
        ttk.Button(config_inner, text="🎮 管理 IGDB API", width=25, command=self.open_igdb_credentials_ui).pack(
            side="left")

        d_config = tk.Text(right_panel, font=("微软雅黑", 9), height=3, bg=root.cget("bg"), relief="flat", padx=35)
        d_config.tag_config("orange", foreground="orange")
        d_config.tag_config("purple", foreground="#7c3aed")
        d_config.insert("end", "• Cookie：获取")
        d_config.insert("end", "完整的鉴赏家列表", "orange")
        d_config.insert("end", "（含各种内容）。\n")
        d_config.insert("end", "• IGDB API：按")
        d_config.insert("end", "游戏类型分类", "purple")
        d_config.insert("end", "获取游戏列表。")
        d_config.config(state="disabled")
        d_config.pack(fill="x", pady=(5, 10))

        # ====== 底部：打开数据文件夹 ======
        def open_data_folder():
            path = self.core.data_dir
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])

        bottom_row = tk.Frame(right_panel)
        bottom_row.pack(fill="x", padx=35, pady=(0, 10))
        tk.Button(bottom_row, text="📂 打开数据文件夹", command=open_data_folder,
                  font=("微软雅黑", 8), fg="#888", relief="flat", cursor="hand2").pack(side="right")

        root.update_idletasks()
        cw, ch = root.winfo_reqwidth(), root.winfo_reqheight()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{cw}x{ch}+{int((sw - cw) / 2)}+{int((sh - ch) / 2)}")
        root.mainloop()