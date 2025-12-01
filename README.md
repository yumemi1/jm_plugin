# JM 插件 (jm_plugin)

此插件利用 `jmcomic` 库下载 JMComic 的专辑（album/photo），并将生成的 PDF 上传到 Napcat 机器人框架。

## 要求

- Python 环境（本项目依赖由宿主应用管理）
- 需要安装的 Python 库（若宿主应用不自动安装）：
  - `jmcomic`
  - `pillow`
  - `aiohttp`

安装示例：
```bash
pip install jmcomic pillow aiohttp
```

## 配置（`config.toml`）

在插件配置段 `jm` 下可设置：

- `jm_data_dir`：下载目录（相对或绝对）。默认：`plugins/jm_plugin/data`（插件目录下的 data）。
- `napcat_base_url`：Napcat 上传 API 的基础 URL，默认 `http://127.0.0.1:3000`。
- `max_pdf_pages`：生成 PDF 的最大页数限制（默认 300）。

示例（`config.toml`）:
```toml
[jm]
jm_data_dir = ""
napcat_base_url = "http://127.0.0.1:3000"
max_pdf_pages = 300
```

## 使用

在聊天中输入命令：
```
/jm 123456
```
插件会：检查专辑章节数，若是多章节仅下载第一章，合成 PDF 并通过 Napcat 上传。

## 注意

- 如果宿主应用自动安装插件依赖，则无需手动安装。
- `jmcomic` 可能对不同平台/网络环境有额外要求（代理、Cookie），请参考 `jmcomic` 文档。

## 开发

如需本地测试，确保 `config.toml` 中 `jm.jm_data_dir` 指向可写目录，并已安装上面列出的 python 库。

==========

功能：通过 `jmcomic` 下载指定 id 的图集，并根据配置（默认 img2pdf）生成 PDF 或图片目录后，上报到 QQ 群文件或客户端文件。

快速测试：在群聊中发送命令：

/jm 12345

将会触发下载流程并在完成后上传文件。

希望有大佬写个完美的
