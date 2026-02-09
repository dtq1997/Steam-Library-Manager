# Steam Library Manager (Steam 收藏夹管理助手)

![Steam](https://img.shields.io/badge/Platform-Steam-blue) ![Python](https://img.shields.io/badge/Language-Python-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

**Steam Library Manager** 是一款为"游戏收藏家"设计的强力工具。它突破了 Steam 客户端手动分类的低效，支持通过鉴赏家、排行榜及专业游戏数据库（IGDB）批量生成和管理你的游戏收藏夹。

---

## ✨ 核心功能

### 多维度数据源

- **Steam 列表页面抓取**：直接同步 Steam 鉴赏家、发行商、开发商及系列专题页面，自动多语言扫描以获取最全数据。
- **SteamDB 联动**：支持导入 SteamDB 页面源代码提取 AppID。
- **Steam250 榜单**：内置 Steam250 排行榜抓取，快速创建高质量游戏合集。
- **IGDB 游戏类型分类**：通过 IGDB API 按类型（如 Roguelike、平台跳跃等）批量获取游戏列表，支持全量本地缓存（7 天有效期）。

### 智能收藏夹管理

- **增量更新**：更新收藏夹时默认采用"增量"模式，只添加新游戏，不覆盖原有内容。程序会自动生成"比旧版多"和"比旧版少"的临时分类，方便核对差异。
- **替换式更新**：也可选择直接替换收藏夹内容。
- **批量导入/导出**：支持 TXT（AppID 列表）和 JSON（结构化收藏夹，含动态逻辑）两种格式，可批量操作多个收藏夹。
- **批量更新映射**：一屏选择多个来源文件到目标收藏夹的映射关系，统一执行更新。

### 多账号支持

- 启动时自动扫描本地所有 Steam 账号（支持 Windows、macOS、Linux 及 WSL 环境）。
- 支持一键切换账号，自动定位 `cloud-storage-namespace-1.json` 配置文件。
- 未检测到账号时可手动选择文件路径。

### 备份与差异对比

- 修改原文件前自动创建带时间戳的备份。
- 内置差异查看器，可直观对比不同备份版本之间的收藏夹变化（新增/删除/修改）。
- 支持备份恢复和删除管理。

### 其他

- **Cookie 管理**：保存 Steam 登录 Cookie（Base64 混淆存储），获取完整的鉴赏家列表（含各种内容）。
- **IGDB API 凭证管理**：保存 Twitch/IGDB 的 Client ID 和 Client Secret，自动获取和缓存 Access Token。
- **SSL 优化**：针对 macOS 环境优化了证书验证逻辑，确保抓取过程不报错。
- **原子写入**：保存 JSON 文件时使用临时文件 + 原子替换，防止写入中断导致数据损坏。

---

## 📁 项目结构

```
├── main.py              # 程序入口
├── ui.py                # GUI 界面（tkinter），含账号选择和主窗口
├── core.py              # 核心业务逻辑（数据抓取、收藏夹操作、IGDB API 等）
├── account_manager.py   # Steam 账号发现与管理
├── local_storage.py     # 备份管理器（创建/恢复/删除/对比备份）
├── spiders.py           # 爬虫模块（IGDB，扩展预留）
└── README.md
```

---

## 🚀 快速上手

### 1. 环境准备

确保已安装 **Python 3.12+**。GUI 基于 Python 标准库 `tkinter`，大多数系统自带。

安装唯一的第三方依赖：

```bash
pip install vdf
```

> `vdf` 用于解析 Steam 的 Valve Data Format 配置文件以读取用户昵称。

### 2. 运行程序

```bash
python main.py
```

程序启动后会自动扫描本地 Steam 账号。若检测到多个账号，会显示选择界面；若仅一个则直接进入主窗口。

### 3. 使用可选功能

- **IGDB 游戏类型分类**：需要在 [Twitch 开发者后台](https://dev.twitch.tv/console) 注册应用，获取 Client ID 和 Client Secret，在程序内「管理 IGDB API」中配置。首次使用某类型时会自动下载全量缓存（约 5–8 分钟），后续使用本地缓存。
- **完整鉴赏家列表**：部分鉴赏家推荐可能被 Steam 内容过滤隐藏，配置登录 Cookie 后可获取完整列表。

---

## 🔧 工作原理

本工具通过直接读写 Steam 本地配置文件 `cloud-storage-namespace-1.json`（位于 `userdata/<SteamID3>/config/cloudstorage/`）来管理收藏夹。修改保存后，Steam 客户端会在下次启动或同步时将变更上传至云端。

为确保触发云同步，程序会在收藏夹名称末尾附加提示文字 `(删除这段字以触发云同步)`，手动删除该后缀即可触发 Steam 的云同步机制。

---

## ⚠️ 注意事项

- 使用前请确保 **Steam 客户端已完全退出**，避免文件读写冲突。
- 若收藏夹中包含未拥有的游戏、重复条目或 DLC，可能导致 Steam 客户端内显示的数目与实际不符。
- 程序数据（配置、IGDB 缓存）统一存放在 `~/.steam_toolbox/` 目录下。

---

## 📄 License

MIT
