import streamlit as st
from pathlib import Path
import pandas as pd
import time
from datetime import datetime
import os
# import yt_dlp
import threading

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="视频下载工具",
    page_icon="📥",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------- 样式优化 ----------
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
    }
    .success-box {
        padding: 10px;
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        margin: 10px 0;
    }
    .warning-box {
        padding: 10px;
        background-color: #fff3cd;
        border-left: 4px solid #ffc107;
        margin: 10px 0;
    }
    .error-box {
        padding: 10px;
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 初始化 ----------
default_path = Path.home() / "Downloads" / "视频下载"

# ---------- session_state 初始化 ----------
if "download_logs" not in st.session_state:
    st.session_state.download_logs = ""

if "stop_download" not in st.session_state:
    st.session_state.stop_download = False

if "failed_results" not in st.session_state:
    st.session_state.failed_results = []

if "is_downloading" not in st.session_state:
    st.session_state.is_downloading = False

if "download_stats" not in st.session_state:
    st.session_state.download_stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "start_time": None
    }


# ---------- 工具函数 ----------
def add_log(msg, log_type="info"):
    """追加日志到 session_state，带时间戳"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    icon = {"success": "🟢", "error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(log_type, "ℹ️")
    st.session_state.download_logs += f"[{timestamp}] {icon} {msg}\n"


def clear_logs():
    """清空日志和统计"""
    st.session_state.download_logs = ""
    st.session_state.failed_results = []
    st.session_state.download_stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "start_time": None
    }


def stop_download():
    """停止下载"""
    st.session_state.stop_download = True
    st.session_state.is_downloading = False


def validate_url(url):
    """验证URL格式"""
    return url.startswith(("http://", "https://"))


def detect_platform(url):
    """
    检测视频链接所属平台
    返回: platform_name (str)
    """
    url_lower = url.lower()

    # 抖音
    if 'douyin.com' in url_lower or 'v.douyin.com' in url_lower:
        return 'douyin'

    # 快手
    elif 'kuaishou.com' in url_lower or 'v.kuaishou.com' in url_lower:
        return 'kuaishou'

    # 小红书
    elif 'xiaohongshu.com' in url_lower or 'xhslink.com' in url_lower:
        return 'xiaohongshu'

    # 微信视频号
    elif 'weixin' in url_lower or 'channels.weixin' in url_lower:
        return 'weixin'

    # Bilibili
    elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'bilibili'

    # YouTube
    elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'

    # 其他平台
    else:
        return 'unknown'


# ========== 自定义平台下载器 ==========

def download_douyin(url, save_path, timeout=60):
    """
    抖音视频下载（处理分享链接）
    返回: (success: bool, error_msg: str, video_title: str)
    """
    try:
        # TODO: 实现抖音下载逻辑
        # 1. 解析分享链接获取真实视频ID
        # 2. 获取视频信息和下载地址
        # 3. 下载视频

        # 示例代码框架：
        # import requests
        # response = requests.get(url, timeout=timeout, allow_redirects=True)
        # real_url = response.url
        # # 解析页面获取视频地址
        # video_url = parse_douyin_video_url(real_url)
        # # 下载视频
        # download_file(video_url, save_path / "douyin_video.mp4")

        return False, "抖音下载功能待实现，请在 download_douyin 函数中添加逻辑", "抖音视频"

    except Exception as e:
        return False, f"抖音下载失败: {str(e)}", "抖音视频"


def download_kuaishou(url, save_path, timeout=60):
    """
    快手视频下载（处理分享链接）
    返回: (success: bool, error_msg: str, video_title: str)
    """
    try:
        # TODO: 实现快手下载逻辑
        return False, "快手下载功能待实现，请在 download_kuaishou 函数中添加逻辑", "快手视频"

    except Exception as e:
        return False, f"快手下载失败: {str(e)}", "快手视频"


def download_xiaohongshu(url, save_path, timeout=60):
    """
    小红书视频下载（处理分享链接）
    返回: (success: bool, error_msg: str, video_title: str)
    """
    try:
        # TODO: 实现小红书下载逻辑
        return False, "小红书下载功能待实现，请在 download_xiaohongshu 函数中添加逻辑", "小红书视频"

    except Exception as e:
        return False, f"小红书下载失败: {str(e)}", "小红书视频"


def download_weixin(url, save_path, timeout=60):
    """
    微信视频号下载（处理分享链接）
    返回: (success: bool, error_msg: str, video_title: str)
    """
    try:
        # TODO: 实现微信视频号下载逻辑
        return False, "微信视频号下载功能待实现，请在 download_weixin 函数中添加逻辑", "微信视频"

    except Exception as e:
        return False, f"微信视频号下载失败: {str(e)}", "微信视频"


# ========== 通用下载器（使用 yt-dlp）==========

def download_with_ytdlp(url, save_path, timeout=60, max_retries=2, video_quality='best'):
    """
    使用 yt-dlp 下载视频（支持大多数平台）
    返回: (success: bool, error_msg: str, video_title: str)
    """
    video_title = "未知视频"

    # 配置 yt-dlp 选项
    ydl_opts = {
        'outtmpl': str(save_path / '%(title)s.%(ext)s'),
        'format': video_quality,
        'socket_timeout': timeout,
        'retries': max_retries,
        'quiet': False,
        'no_warnings': False,
        'ignoreerrors': False,
        'nocheckcertificate': True,
        'progress_hooks': [],
    }

    # try:
    #     with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    #         info = ydl.extract_info(url, download=False)
    #         video_title = info.get('title', '未知视频')
    #         ydl.download([url])
    #
    #     return True, None, video_title
    #
    # except yt_dlp.utils.DownloadError as e:
    #     error_msg = str(e)
    #     if 'HTTP Error 403' in error_msg:
    #         return False, "访问被拒绝(403)，可能需要登录或该视频有地区限制", video_title
    #     elif 'HTTP Error 404' in error_msg:
    #         return False, "视频不存在(404)", video_title
    #     elif 'Unsupported URL' in error_msg:
    #         return False, "不支持的视频平台", video_title
    #     else:
    #         return False, f"下载错误: {error_msg}", video_title
    #
    # except Exception as e:
    #     return False, f"未知错误: {str(e)}", video_title

    return False, f"未知错误: {str(e)}", video_title

# ========== 智能路由下载器 ==========

def download_video(url, save_path, timeout=60, max_retries=2, video_quality='best', use_custom_downloader=True):
    """
    智能下载视频 - 根据平台自动选择下载器

    参数:
        url: 视频链接
        save_path: 保存路径
        timeout: 超时时间
        max_retries: 重试次数
        video_quality: 视频质量
        use_custom_downloader: 是否使用自定义下载器

    返回: (success: bool, error_msg: str, video_title: str)
    """

    # 检测平台
    platform = detect_platform(url)

    # 如果启用自定义下载器，优先使用
    if use_custom_downloader:
        if platform == 'douyin':
            return download_douyin(url, save_path, timeout)

        elif platform == 'kuaishou':
            return download_kuaishou(url, save_path, timeout)

        elif platform == 'xiaohongshu':
            return download_xiaohongshu(url, save_path, timeout)

        elif platform == 'weixin':
            return download_weixin(url, save_path, timeout)

    # 使用 yt-dlp 作为备用方案（支持 YouTube、Bilibili 等）
    return download_with_ytdlp(url, save_path, timeout, max_retries, video_quality)


def export_failed_results():
    """导出失败结果为Excel"""
    if st.session_state.failed_results:
        df = pd.DataFrame(st.session_state.failed_results)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"下载失败记录_{timestamp}.xlsx"
        return df.to_excel(filename, index=False, engine='openpyxl'), filename
    return None, None


# ---------- 标题和说明 ----------
st.title("📥 视频批量下载工具")
st.markdown("---")

# ---------- 侧边栏配置 ----------
with st.sidebar:
    st.header("⚙️ 配置选项")

    # 保存路径
    save_path = st.text_input(
        label="💾 保存路径",
        value=str(default_path),
        help="视频将保存到此目录",
        key="save_path_input"
    )
    save_path = Path(save_path)

    # 路径验证
    if not save_path.exists():
        st.info("💡 保存路径不存在，将自动创建")

    # 打开保存目录按钮
    if st.button("📂 打开保存目录"):
        try:
            if save_path.exists():
                if os.name == 'nt':  # Windows
                    os.startfile(save_path)
                elif os.name == 'posix':  # macOS and Linux
                    os.system(f'open "{save_path}"' if os.uname().sysname == 'Darwin' else f'xdg-open "{save_path}"')
                st.success("已打开保存目录")
            else:
                st.warning("保存目录尚未创建")
        except Exception as e:
            st.error(f"无法打开目录: {e}")

    st.markdown("---")

    # 下载设置
    st.subheader("下载设置")

    use_custom_downloader = st.checkbox(
        "启用自定义下载器",
        value=True,
        help="针对抖音、快手、小红书等特殊平台使用自定义下载逻辑"
    )

    max_retries = st.number_input("最大重试次数", min_value=0, max_value=5, value=2,
                                  help="下载失败后的重试次数")
    timeout = st.number_input("超时时间(秒)", min_value=10, max_value=300, value=60,
                              help="单个视频下载的最长等待时间")

    # 视频质量选择
    video_quality = st.selectbox(
        "视频质量",
        ["best", "worst", "bestvideo+bestaudio", "1080p", "720p", "480p"],
        index=0,
        help="best: 最佳质量 | worst: 最低质量 | 其他: 指定分辨率"
    )

    st.markdown("---")
    st.caption("v1.0.0 | 支持 Mac & Windows")

# ---------- 主界面 ----------
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📝 输入视频链接")
    video_links_text = st.text_area(
        label="每行输入一个视频链接",
        height=200,
        placeholder="https://example.com/video1\nhttps://example.com/video2\n...",
        key="video_links_text",
        help="支持批量粘贴，每行一个链接"
    )
    text_links = [link.strip() for link in st.session_state.video_links_text.splitlines() if link.strip()]

with col2:
    st.subheader("📤 或上传 Excel")
    uploaded_file = st.file_uploader(
        label="选择 Excel 文件",
        type=["xlsx", "xls"],
        key="excel_uploader",
        help="Excel 文件需包含【视频链接】列"
    )

    if st.button("📋 查看模板格式"):
        st.info("Excel 文件格式要求：\n\n需包含名为「视频链接」的列")
        template_df = pd.DataFrame({
            "视频链接": [
                "https://example.com/video1",
                "https://example.com/video2",
                "https://example.com/video3"
            ]
        })
        st.dataframe(template_df, width='stretch')

# ---------- 处理Excel文件 ----------
excel_links = []
required_column = "视频链接"

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        if required_column in df.columns:
            excel_links = df[required_column].dropna().astype(str).tolist()
            st.success(f"✅ 成功读取 {len(excel_links)} 条链接")
        else:
            st.error(f"❌ Excel 文件缺少「{required_column}」列")
            st.info(f"当前列名: {', '.join(df.columns.tolist())}")
    except Exception as e:
        st.error(f"❌ 读取 Excel 文件失败：{e}")

# ---------- 合并和验证链接 ----------
all_links_raw = text_links + excel_links
all_links = [link for link in all_links_raw if validate_url(link)]
invalid_links = [link for link in all_links_raw if link and not validate_url(link)]

st.markdown("---")

# ---------- 链接统计 ----------
if all_links or invalid_links:
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    with stat_col1:
        st.metric("✅ 有效链接", len(all_links))
    with stat_col2:
        st.metric("❌ 无效链接", len(invalid_links))
    with stat_col3:
        st.metric("📊 总计", len(all_links_raw))

    if invalid_links:
        with st.expander("⚠️ 查看无效链接"):
            for idx, link in enumerate(invalid_links, 1):
                st.text(f"{idx}. {link}")

# ---------- 下载控制按钮 ----------
st.markdown("---")
button_col1, button_col2, button_col3 = st.columns([1, 1, 2])

with button_col1:
    start_download = st.button(
        "🚀 开始下载",
        disabled=st.session_state.is_downloading or len(all_links) == 0,
        type="primary",
        use_container_width=True
    )

with button_col2:
    if st.session_state.is_downloading:
        st.button(
            "⏹️ 停止下载",
            on_click=stop_download,
            type="secondary",
            use_container_width=True
        )
    else:
        if st.button("🗑️ 清空日志", use_container_width=True):
            clear_logs()
            st.rerun()

with button_col3:
    if st.session_state.failed_results:
        # 导出失败记录
        try:
            df_failed = pd.DataFrame(st.session_state.failed_results)
            csv = df_failed.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="📥 导出失败记录 (CSV)",
                data=csv,
                file_name=f"下载失败记录_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True
            )
        except:
            pass

# ---------- 下载统计信息 ----------
if st.session_state.download_stats["total"] > 0:
    st.markdown("### 📊 下载统计")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

    with stat_col1:
        st.metric("总数", st.session_state.download_stats["total"])
    with stat_col2:
        st.metric("成功", st.session_state.download_stats["success"],
                  delta=f"{st.session_state.download_stats['success'] / st.session_state.download_stats['total'] * 100:.1f}%")
    with stat_col3:
        st.metric("失败", st.session_state.download_stats["failed"],
                  delta=f"{st.session_state.download_stats['failed'] / st.session_state.download_stats['total'] * 100:.1f}%",
                  delta_color="inverse")
    with stat_col4:
        if st.session_state.download_stats["start_time"]:
            elapsed = (datetime.now() - st.session_state.download_stats["start_time"]).seconds
            st.metric("用时", f"{elapsed // 60}分{elapsed % 60}秒")

# ---------- 日志显示 ----------
st.markdown("### 📋 下载日志")
log_placeholder = st.empty()

if st.session_state.download_logs:
    log_placeholder.markdown(
        f'<div style="height:300px; overflow-y:auto; background:#f8f9fa; padding:15px; border-radius:8px; border:1px solid #dee2e6; font-family: monospace; white-space: pre-wrap; word-wrap: break-word; font-size: 13px;">{st.session_state.download_logs}</div>',
        unsafe_allow_html=True
    )
else:
    log_placeholder.info("暂无日志记录")

# ---------- 开始下载逻辑 ----------
if start_download:
    clear_logs()
    st.session_state.stop_download = False
    st.session_state.is_downloading = True
    st.session_state.download_stats = {
        "total": len(all_links),
        "success": 0,
        "failed": 0,
        "start_time": datetime.now()
    }

    if not all_links:
        st.warning("⚠️ 没有有效的视频链接")
        st.session_state.is_downloading = False
    else:
        add_log(f"开始批量下载，共 {len(all_links)} 个视频", "info")
        st.rerun()

# ---------- 执行下载 ----------
if st.session_state.is_downloading and all_links:
    try:
        # 创建保存目录
        if not save_path.exists():
            save_path.mkdir(parents=True, exist_ok=True)
            add_log(f"已创建保存目录: {save_path}", "info")

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, url in enumerate(all_links, start=1):
            if st.session_state.stop_download:
                add_log("用户手动终止下载", "warning")
                break

            status_text.info(f"⏳ 正在下载第 {i}/{len(all_links)} 个视频...")

            try:
                # 调用智能下载函数
                success, error_msg, video_title = download_video(
                    url,
                    save_path,
                    timeout=timeout,
                    max_retries=max_retries,
                    video_quality=video_quality,
                    use_custom_downloader=use_custom_downloader
                )

                if success:
                    add_log(f"第 {i}/{len(all_links)} 个视频下载成功: {video_title}", "success")
                    st.session_state.download_stats["success"] += 1
                else:
                    raise Exception(error_msg)

            except Exception as e:
                st.session_state.failed_results.append({
                    "序号": i,
                    "视频链接": url,
                    "失败原因": str(e),
                    "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                add_log(f"第 {i}/{len(all_links)} 个视频下载失败: {str(e)}", "error")
                st.session_state.download_stats["failed"] += 1

            # 更新进度
            progress_bar.progress(i / len(all_links))

            # 更新日志显示
            log_placeholder.markdown(
                f'<div style="height:300px; overflow-y:auto; background:#f8f9fa; padding:15px; border-radius:8px; border:1px solid #dee2e6; font-family: monospace; white-space: pre-wrap; word-wrap: break-word; font-size: 13px;">{st.session_state.download_logs}</div>',
                unsafe_allow_html=True
            )

        # 下载完成
        status_text.empty()
        st.session_state.is_downloading = False

        # 显示结果
        if st.session_state.stop_download:
            st.warning("⚠️ 下载已被用户手动终止")
            add_log("下载任务已终止", "warning")
        else:
            if st.session_state.download_stats["failed"] == 0:
                st.success("🎉 全部视频下载完成！")
                add_log("全部视频下载成功！", "success")
            else:
                st.warning(f"⚠️ 下载完成，但有 {st.session_state.download_stats['failed']} 个视频失败")
                add_log(
                    f"下载完成，成功 {st.session_state.download_stats['success']} 个，失败 {st.session_state.download_stats['failed']} 个",
                    "warning")

        st.balloons()

    except Exception as e:
        st.error(f"❌ 发生严重错误: {e}")
        add_log(f"发生严重错误: {e}", "error")
        st.session_state.is_downloading = False

# ---------- 失败明细 ----------
if st.session_state.failed_results:
    st.markdown("---")
    st.markdown("### ❌ 失败明细")

    df_failed = pd.DataFrame(st.session_state.failed_results)

    # 添加筛选功能
    filter_col1, filter_col2 = st.columns([3, 1])
    with filter_col1:
        search_term = st.text_input("🔍 搜索失败原因", placeholder="输入关键词筛选...")

    if search_term:
        df_failed = df_failed[df_failed['失败原因'].str.contains(search_term, case=False, na=False)]

    st.dataframe(
        df_failed,
        width='stretch',
        height=400,
        column_config={
            "序号": st.column_config.NumberColumn("序号", width="small"),
            "视频链接": st.column_config.LinkColumn("视频链接", width="large"),
            "失败原因": st.column_config.TextColumn("失败原因", width="medium"),
            "时间": st.column_config.DatetimeColumn("时间", width="medium")
        }
    )

    st.caption(f"共 {len(st.session_state.failed_results)} 条失败记录")

# ---------- 页脚 ----------
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>💡 使用提示：支持批量粘贴链接，支持 Excel 导入，失败记录可导出</p>
        <p style='font-size: 12px;'>如有问题或建议，请联系技术支持</p>
    </div>
    """,
    unsafe_allow_html=True
)