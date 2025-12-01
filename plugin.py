# plugin.py
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


# ========================
# 工具：清理文件名
# ========================
def sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符，使其适合作为文件系统路径。
    
    Args:
        name: 原始文件名
        
    Returns:
        清理后的文件名（将非法字符替换为下划线）
    """
    return re.sub(r'[\\/:*?"<>|\r\n]+', '_', name).strip()


# ========================
# 工具：图片合并 PDF
# ========================
def images_to_pdf_sync(image_paths: List[Path], output_pdf_path: str) -> str:
    """将多张图片合并为单个 PDF 文件。
    
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

    # 打开并转换所有图片为 RGB 模式
    images = []
    for img_path in image_paths:
        img = Image.open(img_path)
        # 确保图片为 RGB 模式（某些格式可能是 RGBA 或灰度）
        if img.mode != "RGB":
            img = img.convert("RGB")
        images.append(img)

    # 创建输出目录
    os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)

    # 合并图片：第一张图片为主，其余为附加
    first_image = images[0]
    remaining_images = images[1:]
    first_image.save(output_pdf_path, save_all=True, append_images=remaining_images)

    # 关闭所有图片对象释放内存
    for img in images:
        try:
            img.close()
        except Exception:
            pass

    return output_pdf_path


# ========================
# Napcat 上传 PDF
# ========================
async def upload_pdf_via_napcat(
    pdf_path: str,
    filename: str,
    scope: str,
    target_id: int,
    napcat_base: str,
    timeout: int = 60,
) -> Tuple[bool, str]:
    """通过 Napcat 机器人框架上传 PDF 文件到群聊或私聊。
    
    尝试两种上传方式：
    1. JSON 方式：直接发送文件路径
    2. FormData 方式：上传文件二进制数据
    
    Args:
        pdf_path: PDF 文件的本地路径
        filename: 文件名
        scope: 上传范围，"group" 为群聊，其他为私聊
        target_id: 目标 ID（群号或用户 ID）
        napcat_base: Napcat API 基础 URL
        timeout: 请求超时时间（秒）
        
    Returns:
        (成功标志, 响应消息)
    """
    # 根据范围选择对应的 API 端点和参数
    if scope == "group":
        url = f"{napcat_base}/upload_group_file"
        json_payload = {"group_id": target_id, "file": pdf_path, "name": filename}
    else:
        url = f"{napcat_base}/upload_private_file"
        json_payload = {"user_id": target_id, "file": pdf_path, "name": filename}

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as sess:
        # 方式 1：尝试用 JSON 方式发送文件路径
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
            pass  # JSON 方式失败，尝试 FormData 方式

        # 方式 2：使用 FormData 上传文件二进制数据
        form = aiohttp.FormData()
        if scope == "group":
            form.add_field("group_id", str(target_id))
        else:
            form.add_field("user_id", str(target_id))

        form.add_field("name", filename)
        # 打开并上传文件
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


# ========================
# 下载 JM 漫画
# ========================
async def check_album_chapters(
    album_id: str,
    output_dir: Optional[str] = None,
) -> Tuple[bool, Optional[int], Optional[str]]:
    """检查漫画专辑的章节数。
    
    Args:
        album_id: 漫画专辑 ID
        output_dir: 自定义输出目录，为空时使用默认目录
        
    Returns:
        (成功标志, 章节数或None, 错误信息或None)
    """
    try:
        import jmcomic
    except Exception as e:
        return False, None, f"jmcomic 导入失败: {e}"

    try:
        # 创建临时配置
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "data")
        
        output_dir = os.path.abspath(output_dir)
        os.makedirs(output_dir, exist_ok=True)
        
        option_file = os.path.join(output_dir, "option.yml")
        with open(option_file, "w", encoding="utf-8") as config_file:
            config_file.write(f"dir_rule:\n  base_dir: {output_dir}\n")
        
        option = jmcomic.create_option_by_file(option_file)
        
        # 在线程池中获取专辑信息
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
) -> Tuple[bool, Optional[str], Optional[int]]:
    """异步下载 JM 漫画专辑并返回图片目录路径。
    
    Args:
        album_id: 漫画专辑 ID
        output_dir: 自定义输出目录，为空时使用默认目录
        plugin_dir: 插件目录，用于确定默认的 data 目录位置
        only_first_chapter: 是否仅下载第一章
        
    Returns:
        (成功标志, 图片目录路径或错误信息, 总章节数或None)
    """
    # 动态导入 jmcomic 库
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

    # 创建 jmcomic 配置文件
    option_file = os.path.join(output_dir, "option.yml")
    with open(option_file, "w", encoding="utf-8") as config_file:
        config_file.write(f"dir_rule:\n  base_dir: {output_dir}\n")

    # 加载并解析配置
    try:
        option = jmcomic.create_option_by_file(option_file)
    except Exception as e:
        return False, f"jmcomic 配置错误: {e}", None

    # 如果需要仅下载第一章，需要获取第一章的 photo_id
    photo_id_to_download = None
    total_chapters = None
    
    if only_first_chapter:
        try:
            def get_first_chapter_info():
                client = option.new_jm_client()
                album = client.get_album_detail(album_id)
                total = len(album)
                if total > 0:
                    first_photo = list(album)[0]
                    return first_photo.photo_id, total
                return None, total
            
            photo_id_to_download, total_chapters = await asyncio.to_thread(get_first_chapter_info)
            
            if photo_id_to_download is None:
                return False, "无法获取第一章信息", None
        except Exception as e:
            return False, f"获取章节信息失败: {e}", None

    # 在线程池中执行下载（避免阻塞事件循环）
    try:
        if only_first_chapter and photo_id_to_download:
            await asyncio.to_thread(jmcomic.download_photo, photo_id_to_download, option)
        else:
            await asyncio.to_thread(jmcomic.download_album, album_id, option)
    except Exception as e:
        return False, f"下载失败: {e}", None

    # 查找最新下载的图片目录
    # jmcomic 会在 output_dir 下创建多个子目录，需要找到包含图片的最新目录
    subdirs = [d for d in Path(output_dir).iterdir() if d.is_dir()]
    if not subdirs:
        return False, "未找到下载目录", None

    # 按修改时间排序，最新的目录排在前面
    subdirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)

    # 遍历目录找到包含图片的最新目录
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


# ========================
# JMCommand
# ========================
class JMCommand(BaseCommand):
    """JM 漫画下载命令类。
    
    处理 /jm <album_id> 命令：
    1. 下载指定专辑的漫画图片
    2. 将所有图片合并为 PDF
    3. 通过 Napcat 上传 PDF 到群聊或私聊
    4. 清理临时文件
    """
    
    command_name = "jm"
    command_description = "下载 JM 漫画为 PDF 并上传"
    command_pattern = r"^/jm\s*(?P<id>\S+)$"

    async def execute(self) -> Tuple[bool, Optional[str], bool]:
        """执行 /jm 命令：下载漫画、转换为 PDF、上传到群聊或私聊。
        
        如果是多章节本子，仅下载和输出第一章。
        """
        # 提取命令参数
        album_id = self.matched_groups.get("id")
        if not album_id:
            await self.send_text("用法：/jm 123456")
            return True, None, True

        # 通知用户开始下载
        await self.send_text("开始下载")

        # 获取配置参数
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        jm_data_dir = self.get_config("jm.jm_data_dir","")
        napcat_base_url = self.get_config("jm.napcat_base_url")
        max_pdf_pages = self.get_config("jm.max_pdf_pages")

        # 第一步：检查章节数
        success, chapter_count, error_msg = await check_album_chapters(
            album_id,
            output_dir=jm_data_dir or None,
        )

        if not success:
            await self.send_text(f"检查章节信息失败: {error_msg}")
            return True, error_msg, True

        # 根据章节数决定是否只下载第一章
        only_first_chapter = chapter_count > 1
        if only_first_chapter:
            await self.send_text(f"检测到多章节本子({chapter_count}话)，仅下载第一章")

        # 第二步：下载漫画
        success, album_dir, total_chapters = await async_download_album(
            album_id,
            output_dir=jm_data_dir or None,
            plugin_dir=plugin_dir,
            only_first_chapter=only_first_chapter,
        )

        if not success:
            await self.send_text("下载失败")
            return True, album_dir, True

        # 发送下载完成的漫画名称
        album_name = os.path.basename(album_dir)
        await self.send_text(album_name)

        # 第三步：收集所有支持的图片文件
        supported_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        img_paths = sorted(
            [p for p in Path(album_dir).rglob("*") if p.suffix.lower() in supported_extensions],
            key=lambda p: p.as_posix()
        )

        if not img_paths:
            await self.send_text("未找到图片")
            return True, None, True

        # 检查页数是否超过限制
        if len(img_paths) > max_pdf_pages:
            await self.send_text(f"页数超过 {max_pdf_pages}，不生成 PDF")
            return True, None, True

        # 第四步：生成 PDF 文件
        safe_name = sanitize_filename(album_id)
        if only_first_chapter:
            safe_name = f"{safe_name}_01"
        pdf_dir = os.path.join(plugin_dir, "tmp_pdf")
        os.makedirs(pdf_dir, exist_ok=True)
        pdf_path = os.path.join(pdf_dir, f"{safe_name}.pdf")

        try:
            await asyncio.to_thread(images_to_pdf_sync, img_paths, pdf_path)
        except Exception as e:
            await self.send_text("PDF 生成失败")
            return True, str(e), True

        # 第五步：确定上传目标（群聊或私聊）
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

        # 第六步：上传 PDF 到 Napcat
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

        # 清理临时 PDF 文件
        try:
            os.remove(pdf_path)
        except Exception:
            pass

        return True, "完成", True


# ========================
# 插件主体
# ========================
@register_plugin
class JMPlugin(BasePlugin):
    """JM 漫画下载插件。
    
    功能：
    - 使用 /jm <专辑ID> 命令下载 JM 漫画
    - 自动转换为 PDF 格式
    - 上传到群聊或私聊
    
    依赖：
    - jmcomic: 漫画下载库
    - pillow: 图片处理库
    - aiohttp: 异步 HTTP 客户端
    """
    
    plugin_name: str = "jm_plugin"
    enable_plugin: bool = True

    dependencies: List[str] = []
    python_dependencies: List[str] = ["jmcomic", "pillow", "aiohttp"]

    config_file_name: str = "config.toml"
    
    # 配置文件架构定义
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
        """返回插件包含的所有命令组件。"""
        return [(JMCommand.get_command_info(), JMCommand)]
