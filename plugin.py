# plugin.py
"""
JM 本子下载插件

概述：
- 通过命令下载指定 ID 的 JMComic 本子
- 支持多章节本子的单章节下载（超出范围默认下载第 1 章并提示）
- 自动合成 PDF 并上传到 QQ 群或私聊（Napcat）

作者：yumemi1
项目：https://github.com/yumemi1/jm_plugin
"""
import asyncio
import os
import re
import json
from typing import List, Tuple, Type, Optional
from pathlib import Path

import aiohttp
from PIL import Image

from src.plugin_system import (
    BasePlugin,
    register_plugin,
    BaseCommand,
    ComponentInfo,
    ConfigField,
)
from src.config.config import global_config



# =============================================================================
# 工具函数
# =============================================================================

def sanitize_filename(name: str) -> str:
    """将文件名中的非法字符替换为下划线。

    替换字符包括：\ / : * ? " < > | 以及换行符。

    Args:
        name: 原始文件名

    Returns:
        处理后的安全文件名
    """
    return re.sub(r'[\\/:*?"<>|\r\n]+', '_', name).strip()



def images_to_pdf_sync(image_paths: List[Path], output_pdf_path: str) -> str:
    """按顺序将图片合并为单个 PDF。

    - 所有图片统一转换为 RGB 模式。
    - 自动创建输出目录（若不存在）。

    Args:
        image_paths: 图片文件路径列表
        output_pdf_path: 输出 PDF 文件路径

    Returns:
        生成的 PDF 文件路径

    Raises:
        ValueError: 当没有图片提供时
    """
    if not image_paths:
        raise ValueError("没有图片可合并")

    images: List[Image.Image] = []
    # 使用上下文管理器确保文件句柄及时释放
    for img_path in image_paths:
        with Image.open(img_path) as im:
            img = im.convert("RGB") if im.mode != "RGB" else im.copy()
        images.append(img)

    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

    first_image = images[0]
    remaining_images = images[1:]
    first_image.save(output_pdf_path, save_all=True, append_images=remaining_images)

    for img in images:
        try:
            img.close()
        except Exception:
            pass

    return output_pdf_path



# =============================================================================
# Napcat API 交互
# =============================================================================

async def upload_pdf_via_napcat(
    pdf_path: str,
    filename: str,
    scope: str,
    target_id: int,
    napcat_base: str,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """通过 Napcat API 上传 PDF 文件。

    尝试两种方式上传：
    1) JSON：传本地文件路径；失败则回退
    2) FormData：上传二进制内容

    Args:
        pdf_path: PDF 文件本地路径
        filename: 上传时的文件名
        scope: "group" 群聊 或 "private" 私聊
        target_id: 群号或用户 ID
        napcat_base: Napcat API 基础 URL
        timeout: 请求总超时（秒）

    Returns:
        (是否成功, 响应文本或错误信息)
    """
    if scope == "group":
        url = f"{napcat_base}/upload_group_file"
        json_payload = {"group_id": target_id, "file": pdf_path, "name": filename}
    else:
        url = f"{napcat_base}/upload_private_file"
        json_payload = {"user_id": target_id, "file": pdf_path, "name": filename}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as sess:
        # 方式 1：JSON 方式（直接传递文件路径）
        try:
            async with sess.post(url, json=json_payload) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        # 尝试格式化 JSON 响应
                        return True, json.dumps(json.loads(response_text), ensure_ascii=False)
                    except Exception:
                        return True, response_text
        except Exception:
            pass  # 静默失败，继续尝试方式 2
        
        # 方式 2：FormData 方式（上传文件二进制）
        form = aiohttp.FormData()
        if scope == "group":
            form.add_field("group_id", str(target_id))
        else:
            form.add_field("user_id", str(target_id))

        form.add_field("name", filename)
        file_handle = open(pdf_path, "rb")
        form.add_field("file", file_handle, filename=filename, content_type="application/pdf")

        try:
            async with sess.post(url, data=form) as response:
                response_text = await response.text()
                if response.status == 200:
                    try:
                        return True, json.dumps(json.loads(response_text), ensure_ascii=False)
                    except Exception:
                        return True, response_text
                else:
                    return False, f"HTTP {response.status}: {response_text}"
        finally:
            file_handle.close()



# =============================================================================
# JMComic 下载功能
# =============================================================================

async def check_album_chapters(
    album_id: str,
    output_dir: Optional[str] = None,
) -> Tuple[bool, Optional[int], Optional[str]]:
    """检查本子的章节数量。

    初始化 jmcomic 配置后查询指定 ID 的章节信息。
    
    Args:
        album_id: 本子 ID
        output_dir: 自定义输出目录，为空时使用默认目录
    
    Returns:
        元组 (是否成功, 章节数量, 错误信息)
        - 成功时返回 (True, 章节数, None)
        - 失败时返回 (False, None, 错误信息)
    """
    try:
        import jmcomic
    except Exception as e:
        return False, None, f"jmcomic 导入失败: {e}"

    try:
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "data")
        
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        option_file = os.path.join(output_dir, "option.yml")
        with open(option_file, "w", encoding="utf-8") as config_file:
            config_file.write(f"dir_rule:\n  base_dir: {output_dir}\n")
        
        option = jmcomic.create_option_by_file(option_file)
        
        # 使用线程池避免阻塞异步事件循环
        def get_album_info():
            client = option.new_jm_client()
            album = client.get_album_detail(album_id)
            return len(album)
        
        chapter_count = await asyncio.to_thread(get_album_info)
        return True, chapter_count, None
    except Exception as e:
        return False, None, f"获取章节信息失败: {e}"


async def async_download_album(
    album_id: str,
    output_dir: Optional[str] = None,
    plugin_dir: Optional[str] = None,
    only_first_chapter: bool = False,
    chapter_index: Optional[int] = None,
) -> Tuple[bool, Optional[str], Optional[int]]:
    """异步下载 JMComic 本子。
    
    支持三种下载模式：
    1. 下载整本（only_first_chapter=False 且未指定 chapter_index）
    2. 仅下载第一章（only_first_chapter=True）
    3. 下载指定章节（指定 chapter_index，1-based）
    
    Args:
        album_id: 本子 ID
        output_dir: 自定义输出目录，为空时使用默认目录
        plugin_dir: 插件目录，用于确定默认的 data 目录位置
        only_first_chapter: 是否仅下载第一章
        chapter_index: 指定章节号（从 1 开始），优先级高于 only_first_chapter
    
    Returns:
        (是否成功, 图片目录或错误信息, 总章节数或 None)
    """
    try:
        import jmcomic
    except Exception as e:
        return False, f"jmcomic 导入失败: {e}", None

    # 确定下载目录
    if output_dir is None:
        if plugin_dir:
            output_dir = os.path.join(plugin_dir, "data")
        else:
            output_dir = os.path.join(os.getcwd(), "data")

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    option_file = os.path.join(output_dir, "option.yml")
    with open(option_file, "w", encoding="utf-8") as config_file:
        config_file.write(f"dir_rule:\n  base_dir: {output_dir}\n")

    try:
        option = jmcomic.create_option_by_file(option_file)
    except Exception as e:
        return False, f"jmcomic 配置错误: {e}", None
    
    # 解析并确定要下载的章节
    photo_id_to_download = None
    total_chapters = None
    download_chapter_index = None
    
    if chapter_index is not None or only_first_chapter:
        try:
            def get_album_chapters():
                client = option.new_jm_client()
                album = client.get_album_detail(album_id)
                total = len(album)
                return list(album), total
            
            chapters_list, total_chapters = await asyncio.to_thread(get_album_chapters)
            
            if total_chapters == 0:
                return False, "本子无章节信息", None
            
            if chapter_index is not None:
                # 用户指定了章节号（1-based），转换为内部索引（0-based）
                idx = chapter_index - 1
                if idx < 0 or idx >= total_chapters:
                    download_chapter_index = 0 if only_first_chapter else None
                else:
                    download_chapter_index = idx
            else:
                download_chapter_index = 0
            
            if download_chapter_index is not None:
                photo_id_to_download = chapters_list[download_chapter_index].photo_id
                if photo_id_to_download is None:
                    return False, "无法获取指定章节信息", None
        except Exception as e:
            return False, f"获取章节信息失败: {e}", None

    try:
        if download_chapter_index is not None:
            await asyncio.to_thread(jmcomic.download_photo, photo_id_to_download, option)
        else:
            await asyncio.to_thread(jmcomic.download_album, album_id, option)
    except Exception as e:
        return False, f"下载失败: {e}", None
    
    # 定位下载的图片目录
    # jmcomic 会在输出目录下创建子目录，需要找到包含图片的目录
    subdirs = [d for d in Path(output_dir).iterdir() if d.is_dir()]
    if not subdirs:
        return False, "未找到下载目录", None
    
    subdirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    
    target_dir = None
    image_extensions = [".jpg", ".jpeg", ".png", ".webp"]
    for subdir in subdirs:
        images = []
        for ext in image_extensions:
            images.extend(subdir.rglob(f"*{ext}"))
        if images:
            target_dir = str(subdir)
            break

    if not target_dir:
        return False, "未找到图片目录", None

    return True, target_dir, total_chapters



# =============================================================================
# 命令处理
# =============================================================================

class JMCommand(BaseCommand):
    """JM 本子下载命令处理器。

    命令格式：
    - /jm <ID>        下载指定 ID 的本子（多章节默认第 1 章）
    - /jm <ID> <章节> 下载指定 ID 本子的指定章节

    执行流程：解析参数 → 检查章节 → 决策下载 → 合成 PDF → 上传 → 清理。
    """
    
    command_name = "jm"
    command_description = "下载 JM 本子为 PDF 并上传。用法：/jm ID 或 /jm ID 章节数"
    command_pattern = r"^/jm(?:\s+(?P<args>.+))?$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行命令主逻辑。
        
        下载策略：
        - 单章节漫画：下载全部，忽略章节参数
        - 多章节漫画 + 无章节参数：下载第一章
        - 多章节漫画 + 有效章节参数：下载指定章节
        - 多章节漫画 + 无效章节参数：下载第一章并提示
        
        Returns:
            元组 (是否继续执行, 执行结果消息, 是否成功)
        """
        args_str = ""
        if self.matched_groups and "args" in self.matched_groups:
            args_str = self.matched_groups["args"] or ""
        args_str = args_str.strip()
        
        if not args_str:
            await self.send_text("用法：/jm ID 或 /jm ID 章节数")
            return True, None, True
        
        parts = args_str.split()
        album_id = parts[0]
        chapter_num = None
        
        if len(parts) > 1:
            try:
                chapter_num = int(parts[1])
                if chapter_num <= 0:
                    await self.send_text("章节数必须为正整数")
                    return True, None, True
            except ValueError:
                await self.send_text("章节数必须为正整数")
                return True, None, True

        await self.send_text("开始下载")

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        jm_data_dir = self.get_config("jm.jm_data_dir","")
        napcat_base_url = self.get_config("jm.napcat_base_url")
        max_pdf_pages = self.get_config("jm.max_pdf_pages")

        success, chapter_count, error_msg = await check_album_chapters(
            album_id,
            output_dir=jm_data_dir or None,
        )

        if not success:
            await self.send_text(f"检查章节信息失败: {error_msg}")
            return True, error_msg, True

    # 决定下载策略
        only_first_chapter = False
        use_chapter_index = None
        
        if chapter_count > 1:
            if chapter_num is not None:
                if chapter_num > chapter_count:
                    only_first_chapter = True
                    await self.send_text(f"本子仅有{chapter_count}章，忽略无效的章节数，下载第一章")
                else:
                    use_chapter_index = chapter_num
                    await self.send_text(f"检测到多章节本子({chapter_count}话)，下载第{chapter_num}章")
            else:
                only_first_chapter = True
                await self.send_text(f"检测到多章节本子({chapter_count}话)，仅下载第一章")
        else:
            if chapter_num is not None:
                await self.send_text("单章节本子，忽略章节数参数")

        success, album_dir, total_chapters = await async_download_album(
            album_id,
            output_dir=jm_data_dir or None,
            plugin_dir=plugin_dir,
            only_first_chapter=only_first_chapter,
            chapter_index=use_chapter_index,
        )

        if not success:
            await self.send_text("下载失败")
            return True, album_dir, True

        album_name = os.path.basename(album_dir)
        await self.send_text(album_name)

    # 收集图片文件
        supported_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        img_paths = sorted(
            [p for p in Path(album_dir).rglob("*") if p.suffix.lower() in supported_extensions],
            key=lambda p: p.as_posix()
        )

        if not img_paths:
            await self.send_text("未找到图片")
            return True, None, True

        if len(img_paths) > max_pdf_pages:
            await self.send_text(f"页数超过 {max_pdf_pages}，不生成 PDF")
            return True, None, True

    # 生成 PDF
        safe_name = sanitize_filename(album_id)
        if use_chapter_index is not None:
            safe_name = f"{safe_name}_{use_chapter_index:02d}"
        elif only_first_chapter:
            safe_name = f"{safe_name}_01"
        pdf_dir = os.path.join(plugin_dir, "tmp_pdf")
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{safe_name}.pdf")

        try:
            await asyncio.to_thread(images_to_pdf_sync, img_paths, pdf_path)
        except Exception as e:
            await self.send_text("PDF 生成失败")
            return True, str(e), True

    # 确定上传目标
        is_group = False
        group_id = None
        user_id = None
        
        try:
            message_info = self.message.message_info
            if message_info.group_info and message_info.group_info.group_id:
                is_group = True
                group_id = int(message_info.group_info.group_id)
            elif message_info.user_info and message_info.user_info.user_id:
                user_id = int(message_info.user_info.user_id)
        except Exception:
            pass

        if is_group:
            ok, msg = await upload_pdf_via_napcat(
                pdf_path, f"{safe_name}.pdf", "group", group_id, napcat_base_url
            )
        elif user_id:
            ok, msg = await upload_pdf_via_napcat(
                pdf_path, f"{safe_name}.pdf", "private", user_id, napcat_base_url
            )
        else:
            await self.send_text("无法识别发送对象")
            return True, None, True

        if not ok:
            await self.send_text("上传失败")
            return True, msg, True

        try:
            os.remove(pdf_path)
        except Exception:
            pass

        return True, "完成", True



# =============================================================================
# 插件注册
# =============================================================================

@register_plugin
class JMPlugin(BasePlugin):
    """JM 漫画下载插件主类。
    
    本插件为 MaiBot 提供 JMComic 图集下载功能。
    通过集成 jmcomic 库实现图集爬取，使用 Pillow 进行 PDF 转换，
    最后通过 Napcat API 将文件上传到 QQ。
    
    主要特性：
    - 支持单章节和多章节漫画
    - 可选择性下载指定章节
    - 自动 PDF 转换和页数限制
    - 支持群聊和私聊上传
    
    Python 依赖：
    - jmcomic: JMComic 爬虫库
    - pillow: 图片处理和 PDF 生成
    - aiohttp: HTTP 客户端
    """
    
    plugin_name: str = "jm_plugin"
    enable_plugin: bool = True

    dependencies: List[str] = []
    python_dependencies: List[str] = ["jmcomic", "pillow", "aiohttp"]

    config_file_name: str = "config.toml"
    
    config_schema = {
        "jm": {
            "jm_data_dir": ConfigField(
                type=str,
                default="",
                description="JM 漫画下载目录，为空默认 plugins/jm_plugin/data"
            ),
            "napcat_base_url": ConfigField(
                type=str,
                default="http://127.0.0.1:3000",
                description="Napcat 机器人框架的 API 基础 URL"
            ),
            "max_pdf_pages": ConfigField(
                type=int,
                default=300,
                description="PDF 最大页数限制"
            ),
        }
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件提供的命令组件列表。"""
        return [(JMCommand.get_command_info(), JMCommand)]
