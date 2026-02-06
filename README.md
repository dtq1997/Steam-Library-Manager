# Steam Library Manager (Steam 收藏夹管理助手)

![Steam](https://img.shields.io/badge/Platform-Steam-blue) ![Python](https://img.shields.io/badge/Language-Python-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

**Steam Library Manager** 是一款为“游戏收藏家”设计的强力工具。它突破了 Steam 客户端手动分类的低效，支持通过鉴赏家、排行榜及专业游戏数据库（IGDB）批量生成和管理你的游戏收藏夹。

---

## ✨ 核心功能

* **智能增量更新**：更新收藏夹时采用“增量”模式，只添加新游戏，不覆盖原有内容。程序会自动生成“比旧版多”和“比旧版少”的临时分类，方便核对。
* **多维度数据源**：
    * **页面抓取**：直接同步 Steam 鉴赏家、发行商、开发商及系列专题页面。
    * **SteamDB 联动**：支持导入 SteamDB 页面源代码提取 AppID。
    * **推荐分类**：内置 Steam250 榜单及 IGDB 游戏类型（如 Roguelike、平台跳跃）分类功能。
* **多账号支持**：启动时自动扫描本地所有 Steam 账号，支持一键切换并自动定位配置文件。
* **完善的备份与差异对比**：在修改原文件前自动创建备份。内置差异查看器，可以直观对比不同版本之间的收藏夹变化。
* **SSL 优化**：针对 macOS 环境优化了证书验证逻辑，确保抓取过程不报错。

---

## 🚀 快速上手



### 1. 环境准备
确保你的电脑已安装 **Python 3.x**。由于本工具使用 Python 标准库 `tkinter` 构建 GUI，通常无需额外安装 UI 库。

### 2. 运行程序
将代码下载到本地，在终端/命令行执行：
```bash
python Steam_Library_Manager_v2.10.py
