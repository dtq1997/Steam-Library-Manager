import json
import time
import secrets
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

class SteamToolbox:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.json_name = "cloud-storage-namespace-1.json"
        self.json_path = os.path.join(self.current_dir, self.json_name)

    def load_json(self):
        if not os.path.exists(self.json_path):
            messagebox.showerror("错误", f"找不到 {self.json_name}\n请确保脚本和它在同一文件夹。")
            return None
        try:
            with open(self.json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("读取错误", f"解析失败: {e}")
            return None

    def save_json(self, data):
        output_path = os.path.join(self.current_dir, "cloud-storage-namespace-1_NEW.json")
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            messagebox.showinfo("成功", f"文件已生成：\n{os.path.basename(output_path)}")
        except Exception as e:
            messagebox.showerror("保存失败", f"无法写入文件: {e}")

    def import_from_txt(self):
        data = self.load_json()
        if data is None: return

        txt_paths = filedialog.askopenfilenames(
            initialdir=self.current_dir,
            title="选择 AppID 列表 (TXT)",
            filetypes=[("Text files", "*.txt")]
        )
        if not txt_paths: return

        for path in txt_paths:
            file_title = os.path.splitext(os.path.basename(path))[0]
            with open(path, 'r', encoding='utf-8') as f:
                app_ids = [int(line.strip()) for line in f if line.strip().isdigit()]
            
            if not app_ids: continue
            self._add_static_collection(data, file_title, app_ids)
        
        self.save_json(data)

    def _add_static_collection(self, data, name, app_ids):
        col_id = f"uc-{secrets.token_hex(6)}"
        storage_key = f"user-collections.{col_id}"
        val_obj = {"id": col_id, "name": name, "added": app_ids, "removed": []}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()), 
                    "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')), "version": "1"}]
        data.append(new_entry)

    def open_friend_sync_ui(self):
        data = self.load_json()
        if data is None: return

        sync_win = tk.Toplevel()
        sync_win.title("批量同步 Steam 用户游戏库")
        sync_win.geometry("550x620")
        sync_win.attributes("-topmost", True)

        tk.Label(sync_win, text="1. 请输入对方的 Steam 好友代码（每行一个）", font=("微软雅黑", 10, "bold")).pack(pady=(15,0))
        codes_text = tk.Text(sync_win, height=8, width=60)
        codes_text.pack(padx=20, pady=5)

        tk.Label(sync_win, text="2. 生成的收藏夹名称 (每行一个)", font=("微软雅黑", 10, "bold")).pack(pady=(10,0))
        names_text = tk.Text(sync_win, height=8, width=60)
        names_text.pack(padx=20, pady=5)

        def generate_default_names():
            raw_content = codes_text.get("1.0", tk.END).strip()
            raw_ids = re.findall(r'\d+', raw_content)
            names_text.delete("1.0", tk.END)
            for rid in raw_ids:
                names_text.insert(tk.END, f"好友代码 [{rid}]\n")

        def commit_import():
            codes = re.findall(r'\d+', codes_text.get("1.0", tk.END))
            names = names_text.get("1.0", tk.END).strip().split('\n')
            names = [n.strip() for n in names if n.strip()]
            for i in range(len(codes)):
                cid = codes[i]
                cname = names[i] if i < len(names) else f"好友代码 [{cid}]"
                self._add_dynamic_collection(data, cname, cid)
            if codes:
                self.save_json(data)
                sync_win.destroy()

        btn_frame = tk.Frame(sync_win)
        btn_frame.pack(pady=20)
        tk.Button(btn_frame, text="✨ 生成默认名称", command=generate_default_names, width=18, height=2).pack(side=tk.LEFT, padx=10)
        # 按钮改成黑字，去掉加粗绿色
        tk.Button(btn_frame, text="开始导入", command=commit_import, width=18, height=2).pack(side=tk.LEFT, padx=10)

    def _add_dynamic_collection(self, data, name, friend_code):
        col_id = f"uc-{secrets.token_hex(4)}"
        storage_key = f"user-collections.{col_id}"
        filter_groups = [{"rgOptions": [], "bAcceptUnion": False} for _ in range(9)]
        filter_groups[0]["bAcceptUnion"] = True
        filter_groups[6]["rgOptions"] = [int(friend_code)]
        val_obj = {"id": col_id, "name": name, "added": [], "removed": [],
            "filterSpec": {"nFormatVersion": 2, "strSearchText": "", "filterGroups": filter_groups, "setSuggestions": {}}}
        new_entry = [storage_key, {"key": storage_key, "timestamp": int(time.time()), 
                    "value": json.dumps(val_obj, ensure_ascii=False, separators=(',', ':')), "version": "1"}]
        data.append(new_entry)

    def main_ui(self):
        root = tk.Tk()
        root.title("Steam 库管理助手")
        root.geometry("640x660")
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f'+{int((sw-640)/2)}+{int((sh-660)/2)}')

        # --- 顶部文字说明区 ---
        instruction_frame = tk.Frame(root, pady=15, padx=35)
        instruction_frame.pack(fill=tk.X)
        
        t_top = tk.Text(instruction_frame, font=("微软雅黑", 10), height=8, bg=root.cget("bg"), relief=tk.FLAT, wrap=tk.WORD)
        t_top.tag_config("red", foreground="red", font=("微软雅黑", 10, "bold"))
        t_top.insert(tk.END, "一、导入前请")
        t_top.insert(tk.END, "关闭", "red")
        t_top.insert(tk.END, " Steam；\n\n")
        t_top.insert(tk.END, "二、导入后，保险起见会创建一个新的文件cloud-storage-namespace-1_NEW.json。为了让修改生效，请您手动")
        t_top.insert(tk.END, "备份", "red")
        t_top.insert(tk.END, "原先的 cloud-storage-namespace-1.json，")
        t_top.insert(tk.END, "替换", "red")
        t_top.insert(tk.END, "成这个文件；\n\n")
        t_top.insert(tk.END, "三、为了让收藏夹能上传到云，您必须")
        t_top.insert(tk.END, "在 Steam 内手动修改", "red")
        t_top.insert(tk.END, "新创建的收藏。例如更改标题，或是添加/删除收藏内的游戏等。")
        t_top.config(state=tk.DISABLED)
        t_top.pack(fill=tk.X)

        # --- 按钮与对应说明 ---
        style = ttk.Style()
        style.configure("TButton", font=("微软雅黑", 11), padding=8)

        # 按钮 1
        ttk.Button(root, text="📁 批量导入 TXT 为收藏夹", width=45, command=self.import_from_txt).pack(pady=(10,0))
        
        desc1_frame = tk.Frame(root, padx=35)
        desc1_frame.pack(fill=tk.X)
        t1 = tk.Text(desc1_frame, font=("微软雅黑", 9), height=5, bg=root.cget("bg"), relief=tk.FLAT)
        t1.tag_config("red", foreground="red")
        t1.insert(tk.END, "一、导入文件必须是 ")
        t1.insert(tk.END, "txt", "red")
        t1.insert(tk.END, " 格式，文件名称会成为收藏夹名称；\n")
        t1.insert(tk.END, "二、内容必须为 ")
        t1.insert(tk.END, "每行一个 appid", "red")
        t1.insert(tk.END, "；\n")
        t1.insert(tk.END, "三、你不必拥有 txt 中的 appid，当你拥有后，它会自动同步进该收藏夹。")
        t1.config(state=tk.DISABLED)
        t1.pack(fill=tk.X, pady=5)

        # 按钮 2
        ttk.Button(root, text="👥 批量同步 Steam 用户游戏库", width=45, command=self.open_friend_sync_ui).pack(pady=(15,0))
        
        desc2_frame = tk.Frame(root, padx=35)
        desc2_frame.pack(fill=tk.X)
        t2 = tk.Text(desc2_frame, font=("微软雅黑", 9), height=3, bg=root.cget("bg"), relief=tk.FLAT)
        t2.tag_config("red", foreground="red")
        t2.insert(tk.END, "一、对方的 Steam 好友代码可在其 SteamDB 页面看到；\n")
        t2.insert(tk.END, "二、对方必须 ")
        t2.insert(tk.END, "公开", "red")
        t2.insert(tk.END, " 了自己的 Steam 库。")
        t2.config(state=tk.DISABLED)
        t2.pack(fill=tk.X, pady=5)

        root.mainloop()

if __name__ == "__main__":
    app = SteamToolbox()
    app.main_ui()
