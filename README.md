# JM 插件 (JMComic Plugin for MaiBot)

> 基于 `jmcomic` 的 MaiBot 插件，支持专辑/章节下载、PDF 合成与 Napcat 上传

## 📖 简介

JM 插件是为 [MaiBot](https://github.com/MaiM-with-u/MaiBot) 开发的内容下载与分享插件，面向 JMComic 图源。它可以：
- 解析并下载指定本子（支持多章节选择）
- 将图片合并为 PDF（可限制最大页数）
- 通过 Napcat 接口上传到 QQ 群或私聊

## ✨ 功能特性

- 📥 **本子下载**：输入本子 ID 即可下载
- 🧩 **章节选择**：多章节专辑可指定下载某一章
- 📄 **PDF 合成**：自动将图片集合转换为 PDF 文件
- 🚚 **Napcat 上传**：支持群聊/私聊文件上传
- 🔢 **页数限制**：可配置 `max_pdf_pages` 限制 PDF 页数
- 🧹 **自动清理**：完成后可清理临时文件目录（视配置/实现）

## 📦 安装

将本插件文件夹放入 MaiBot 的 `plugins/` 目录，并命名为 `jm_plugin`。

**使用 Git 安装**（将 `<MAIBOT_DIR>` 替换为你的 MaiBot 安装路径）：

```cmd
cd <MAIBOT_DIR>\plugins
git clone https://github.com/yumemi1/jm_plugin.git jm_plugin
```

**手动复制**：将本仓库文件夹复制到 `<MAIBOT_DIR>\plugins\jm_plugin`。

### 依赖说明

- 在 MaiBot 的 uv 虚拟环境中，宿主会统一管理依赖。一般无需额外操作。
- 如需手动安装，请确保以下库可用：
  - `jmcomic`
  - `pillow`
  - `aiohttp`

```cmd
pip install jmcomic pillow aiohttp
```

## ⚙️ 配置

在 `config.toml` 中的 `jm` 段进行配置：

```toml
[jm]
jm_data_dir = ""                       # 下载目录（留空则使用默认data路径）
napcat_base_url = "http://127.0.0.1:3000"  # Napcat 基础URL
max_pdf_pages = 300                     # PDF最大页数
```

参数说明：
- `jm_data_dir`：图集下载存储位置（相对/绝对路径均可）
- `napcat_base_url`：Napcat 上传 API 基础地址
- `max_pdf_pages`：限制每个 PDF 的最大页数，防止过大文件

## 🎮 使用方法

### 命令格式

```
/jm <本子ID>
/jm <本子ID> <章节序号>
```

### 行为规则
- 多章节本子：可选参数 `<章节序号>` 生效；超出范围时默认下载第 1 章（会提示）
- 单章节本子：忽略 `<章节序号>` 参数，按单章处理
- PDF 命名：
  - 未指定章节或默认第 1 章：`JM_<ID>_01.pdf`
  - 指定章节 N：`JM_<ID>_<NN>.pdf`（两位序号，如 `_02`）

### 示例

```
/jm 123456           # 下载本子 123456 的第1章（或单章节）
/jm 123456 2         # 下载本子 123456 的第2章
/jm 123456 99        # 超出范围时，下载第1章并提示
```

## 📸 效果演示（示例截图）

```markdown
![单章节本子下载](docs/screenshots/1.png)
![多章节本子下载](docs/screenshots/2.png)
![多章节本子下载](docs/screenshots/3.png)
```

## ⚠️ 注意事项

- 请确保 `napcat_base_url` 正确且 Napcat 服务已启动
- 生成 PDF 时可能占用较多内存与磁盘空间，建议设置合理的 `max_pdf_pages`
- 网络环境可能影响下载速度；`jmcomic` 在某些网络条件下需要额外配置（代理/Cookie）
- 请遵守相关法律法规与平台规范，不要传播非法或不当内容

## 🙏 鸣谢

- [JMComic-Crawler-Python](https://github.com/hect0x7/JMComic-Crawler-Python) - 图源与下载框架
- [MaiBot](https://github.com/MaiM-with-u/MaiBot) - 优秀的 QQ 机器人宿主框架
- [Napcat](https://github.com/NapNeko/NapcatQQ) - QQ 上传接口支持

## 📄 许可证

本插件采用 MIT 许可证开源，详见 `LICENSE` 文件。
