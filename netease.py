"""网易云整首歌下载：官方取直链接口 + MUSIC_U cookie（chorus_cover 自维护分支）。

设计约定
========

1. 只依赖标准库（``urllib`` / ``json`` / ``subprocess``），不新增第三方依赖。
2. 所有函数都是**同步阻塞**的，插件侧（``main.py``）一律放进
   ``asyncio.to_thread`` 里调用，别直接在主事件循环里跑。
3. 判定"是不是整首歌"的唯一标准（官方接口实测）：

   - HTTP 状态 200；
   - 返回体 ``code == 200``；
   - ``data[0].url`` 非空；
   - ``data[0].freeTrialInfo is None``（非 null 就是只给了试听片段）；
   - ``data[0].time >= 80000``（毫秒，整首时长）。

   任一条不满足都算失败并给出简短中文原因。**接口只负责判定**：判定通过后
   它给的 ``data[0].url`` 不拿来下载（实测 CDN 直接 403），统一换成外链跳转
   入口 ``https://music.163.com/song/media/outer/url?id=<id>.mp3``（``urllib``
   默认跟随 302）；判定失败（比如只给试听）就直接返回，不再退回外链。
   下载完成后同样用 ``ffprobe`` 量一次真实时长，不足 80 秒的删文件判失败。
   拿不到时长时按失败处理（宁可不出歌，也不把 60 秒片段交给中间层）。
4. 0.3.0 起只保留网易云官方接口这一条路：没有第三方音源兜底，也没有别的
   取歌入口。取不到整首就失败，不会把试听片段交给中间层。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

#: 官方取直链接口（GET）：只用来判定是不是整首
OFFICIAL_URL = "https://music.163.com/api/song/enhance/player/url"
#: 官方接口要求的请求头（2026-10-27 实测）
DEFAULT_USER_AGENT = "Mozilla/5.0"
OFFICIAL_REFERER = "https://music.163.com"

#: 音频下载入口：接口给的 CDN 直链实测 403，这个外链入口会 302 到可用节点
MEDIA_OUTER_URL = "https://music.163.com/song/media/outer/url?id={song_id}.mp3"
#: 音频下载的请求头（和接口那套分开维护，改一边不影响另一边）
MEDIA_USER_AGENT = "Mozilla/5.0"
MEDIA_REFERER = "https://music.163.com"

#: 单文件下载上限：60MB（整首 320k 大约 10MB，留足余量）
MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024
#: 整首歌的最短时长：80 秒。低于它的直接当试听片段
MIN_FULL_LENGTH_MS = 80_000
_CHUNK_SIZE = 64 * 1024
_JSON_LIMIT = 4 * 1024 * 1024
#: 认得出的音频后缀
_AUDIO_SUFFIXES = (".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg", ".wma")

# ---------------------------------------------------------------------------
# 失败原因（全部是给人看的一句短话，尽量不要在这里堆砌长句）
# ---------------------------------------------------------------------------
REASON_NO_COOKIE = "没配置cookie"
REASON_TRIAL = "只给了试听"
REASON_NO_URL = "没拿到链接"
REASON_DOWNLOAD = "下载中断"
REASON_BAD_ID = "歌曲id不合法"
REASON_BAD_JSON = "接口返回的不是JSON"
REASON_BAD_PAYLOAD = "接口返回格式不对"
REASON_NO_CODE = "接口没返回code"
REASON_NO_TIME = "接口没返回整首时长"
REASON_TOO_BIG = "文件超过60MB"
REASON_NOT_AUDIO = "下载地址返回的不是音频"
REASON_HTTP = "接口返回 HTTP {status}"
REASON_HTTP_DOWNLOAD = "下载地址返回 HTTP {status}"
REASON_DL_NO_TIME = "下载完量不到时长，无法确认是整首"
REASON_DL_TOO_SHORT = "下载到的不是整首（时长 {seconds} 秒）"
REASON_CODE = "接口 code={code}"
REASON_REQUEST_FAILED = "接口请求失败"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _short_error(exc: BaseException) -> str:
    """把网络异常压成一句话，避免把整段堆栈塞进用户可见文案。"""
    text = str(exc or "").strip()
    if not text:
        return type(exc).__name__
    return text.splitlines()[0][:80]


def _safe_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _first_item(data: Any) -> dict:
    """取返回体里描述这一首歌的那一条（兼容 list / dict / 顶层平铺）。"""
    if isinstance(data, list):
        return _as_dict(data[0]) if data else {}
    if isinstance(data, dict):
        return data
    return {}


def _meta(payload: Any) -> dict:
    """把"外层字段"和"歌曲那一条"合并，方便统一读 code/time/freeTrialInfo。"""
    merged: dict = {}
    if isinstance(payload, dict):
        merged.update({k: v for k, v in payload.items() if k != "data"})
        merged.update(_first_item(payload.get("data")))
    elif isinstance(payload, list):
        merged.update(_first_item(payload))
    return merged


def _extract_url(payload: Any) -> str:
    """从各种可能的返回形状里把播放链接抠出来；拿不到返回空串。"""
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, (dict, list)):
        return ""
    if isinstance(payload, list):
        first = _first_item(payload)
        return str(first.get("url") or "").strip()
    data = payload.get("data")
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list) and data:
        head = data[0]
        if isinstance(head, str):
            return head.strip()
        if isinstance(head, dict):
            return str(head.get("url") or "").strip()
    if isinstance(data, dict):
        url = str(data.get("url") or "").strip()
        if url:
            return url
    return str(payload.get("url") or "").strip()


def _pick_time_ms(payload: Any) -> Optional[int]:
    """读整首时长（毫秒）。官方字段是 ``time``；兜底偶尔用 duration 之类的名字。"""
    meta = _meta(payload)
    value = meta.get("time")
    if value is None:
        value = meta.get("duration_ms")
    if value is None:
        value = meta.get("durationMs")
    if value is None:
        duration = meta.get("duration")
        if duration is not None:
            try:
                # duration 可能是秒（< 1000 视为秒）
                value = float(duration) * 1000 if float(duration) < 1000 else float(duration)
            except (TypeError, ValueError):
                value = None
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _suffix_from_url(url: str) -> str:
    path = str(url or "").split("?", 1)[0]
    suffix = os.path.splitext(path)[1].lower()
    if suffix in _AUDIO_SUFFIXES:
        return suffix
    return ".mp3"


def _remove_quietly(path: str) -> None:
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError as exc:
        logger.debug("删除临时文件失败: %s (%s)", path, exc)


# ---------------------------------------------------------------------------
# 判定
# ---------------------------------------------------------------------------
def judge_result(
    payload: Any,
    http_status: int = 200,
    *,
    require_code: bool = True,
    require_time: bool = True,
) -> Tuple[str, str, bool]:
    """按"整首"标准判定一次取链接响应。

    Returns:
        ``(url, 失败原因, 是否试听)``；成功时失败原因为空串。
        失败时 url 可能仍非空（比如只给了试听），方便调用方记日志。
    """
    if http_status != 200:
        return "", REASON_HTTP.format(status=http_status), False
    if not isinstance(payload, (dict, list)):
        return "", REASON_BAD_PAYLOAD, False

    meta = _meta(payload)
    code = meta.get("code")
    if code is None:
        if require_code:
            return "", REASON_NO_CODE, False
    else:
        try:
            code_ok = int(str(code)) == 200
        except (TypeError, ValueError):
            code_ok = False
        if not code_ok:
            return "", REASON_CODE.format(code=code), False

    url = _extract_url(payload)
    free_trial = meta.get("freeTrialInfo")
    if free_trial not in (None, ""):
        # 非 null 就是试听片段，不管 url 有没有都给这一条原因
        return url, REASON_TRIAL, True

    if not url:
        return "", REASON_NO_URL, False

    length = _pick_time_ms(payload)
    if length is None:
        if require_time:
            return "", REASON_NO_TIME, False
        return url, "", False
    if length < MIN_FULL_LENGTH_MS:
        return url, REASON_TRIAL, True
    return url, "", False


def is_cookie_failure(reason: str, is_trial: bool = False) -> bool:
    """判断这次失败是不是"cookie 相关问题"（用于连续 3 次后提醒管理员）。

    认定范围按需求固定为：cookie 为空、HTTP 401、``code != 200``、只给了试听。
    """
    if is_trial:
        return True
    text = str(reason or "").strip()
    if not text:
        return False
    if text == REASON_NO_COOKIE:
        return True
    if text.startswith("接口返回 HTTP 401"):
        return True
    if text.startswith("接口 code="):
        return True
    return False


# ---------------------------------------------------------------------------
# 网络
# ---------------------------------------------------------------------------
def _fetch_json(url: str, headers: dict, timeout: float) -> Tuple[int, Any, str]:
    """GET 一个接口并解析 JSON。

    Returns:
        ``(HTTP 状态码, 解析后的 JSON, 失败原因)``；成功时失败原因为空串。
        HTTP 非 200 也会尽量把返回体解析出来（有的接口用 4xx + JSON 说明原因）。
    """
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            raw = response.read(_JSON_LIMIT)
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            raw = exc.read(64 * 1024)
        except Exception:
            raw = b""
        return status, _safe_json(raw), ""
    except Exception as exc:  # URLError / timeout / 系统错误
        logger.warning("请求网易云接口失败: %s (%s)", url, _short_error(exc))
        return 0, None, REASON_REQUEST_FAILED

    payload = _safe_json(raw)
    if payload is None and status == 200:
        return status, None, REASON_BAD_JSON
    return status, payload, ""


def _api_headers(cookie: str) -> dict:
    """官方接口请求头：``MUSIC_U`` 只传值，不带 ``MUSIC_U=`` 前缀。"""
    return {
        "Cookie": f"MUSIC_U={cookie}",
        "Referer": OFFICIAL_REFERER,
        "User-Agent": DEFAULT_USER_AGENT,
    }


def _media_headers(cookie: str = "") -> dict:
    """音频下载请求头：外链入口同样要 cookie + referer，缺了会被挡回 403。"""
    headers = {"Referer": MEDIA_REFERER, "User-Agent": MEDIA_USER_AGENT}
    if cookie:
        headers["Cookie"] = f"MUSIC_U={cookie}"
    return headers


def _download_file(
    url: str,
    dest_dir: str,
    timeout: float,
    *,
    headers: Optional[dict] = None,
    prefix: str = "netease",
) -> Tuple[str, str]:
    """流式下载到 ``dest_dir``，限制 60MB。返回 ``(本地路径, 失败原因)``。"""
    if not url:
        return "", REASON_NO_URL
    if not dest_dir:
        return "", REASON_DOWNLOAD

    try:
        os.makedirs(dest_dir, exist_ok=True)
    except OSError as exc:
        logger.error("创建临时目录失败: %s (%s)", dest_dir, exc)
        return "", REASON_DOWNLOAD

    dest = os.path.join(
        dest_dir,
        f"{prefix}_{time.strftime('%H%M%S')}_{os.getpid()}_{int(time.time() * 1000) % 100000}{_suffix_from_url(url)}",
    )
    request_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        request_headers.update(headers)

    written = 0
    expected = 0
    try:
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            if status != 200:
                return "", REASON_HTTP_DOWNLOAD.format(status=status)
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if content_type.startswith("text/") or "json" in content_type or "html" in content_type:
                # 直链失效时 CDN 常返回 200 + 一段错误页，别把它当 mp3 存下来
                return "", REASON_NOT_AUDIO
            expected = int(response.headers.get("Content-Length") or 0)
            if expected > MAX_DOWNLOAD_BYTES:
                return "", REASON_TOO_BIG
            with open(dest, "wb") as handle:
                while True:
                    chunk = response.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_DOWNLOAD_BYTES:
                        raise ValueError(REASON_TOO_BIG)
                    handle.write(chunk)
    except urllib.error.HTTPError as exc:
        _remove_quietly(dest)
        return "", REASON_HTTP_DOWNLOAD.format(status=int(getattr(exc, "code", 0) or 0))
    except ValueError as exc:
        _remove_quietly(dest)
        return "", str(exc) or REASON_TOO_BIG
    except Exception as exc:
        _remove_quietly(dest)
        logger.warning("下载音频失败: %s (%s)", url, _short_error(exc))
        return "", REASON_DOWNLOAD

    if written <= 0:
        _remove_quietly(dest)
        return "", REASON_DOWNLOAD
    if expected and written < expected:
        # 连接被掐断时 file 已经落盘但内容不全，宁可丢掉也不要半首歌
        logger.warning("下载不完整: %s (期望 %s 字节，实际 %s 字节)", dest, expected, written)
        _remove_quietly(dest)
        return "", REASON_DOWNLOAD
    return dest, ""


def _probe_duration_ms(path: str) -> Optional[int]:
    """用 ffprobe 量本地音频时长（毫秒）；没有 ffprobe 或读不出来返回 None。"""
    exe = shutil.which("ffprobe")
    if not exe:
        logger.debug("没找到 ffprobe，无法测量兜底文件时长")
        return None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=creationflags,
        )
        text = (completed.stdout or "").strip()
        if not text:
            return None
        return int(float(text) * 1000)
    except Exception as exc:
        logger.debug("ffprobe 读取时长失败: %s (%s)", path, exc)
        return None


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------
def download_by_id(
    song_id: Any,
    cookie: str,
    quality_br: int = 320000,
    dest_dir: Optional[str] = None,
    timeout: float = 120,
) -> Tuple[Optional[str], str, bool]:
    """走官方接口判定"是不是整首"，再从外链入口把整首下到本地。

    接口返回的 ``data[0].url`` 只用来确认"确实给了整首"，**不拿来下载**
    （实测该 CDN 直链 403），下载固定走外链跳转入口；接口判定失败（没链接、
    只给试听、时长不够）直接返回，不再退回外链碰运气。

    Args:
        song_id: 网易云数字歌曲 id。
        cookie: 网易云 ``MUSIC_U`` 的值（不含 ``MUSIC_U=`` 前缀）。
        quality_br: 码率，默认 320000。
        dest_dir: 落盘目录，默认插件目录下的 ``temp_audio``。
        timeout: 单次网络请求超时（秒）。

    Returns:
        ``(本地路径 或 None, 失败原因, 是否试听)``。
    """
    song_id = str(song_id if song_id is not None else "").strip()
    cookie = str(cookie or "").strip()
    if not cookie:
        return None, REASON_NO_COOKIE, False
    if not song_id.isdigit():
        return None, REASON_BAD_ID, False

    try:
        br = int(quality_br or 320000)
    except (TypeError, ValueError):
        br = 320000

    dest = dest_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_audio")
    url = f"{OFFICIAL_URL}?ids=[{song_id}]&br={br}"
    headers = _api_headers(cookie)

    status, payload, error = _fetch_json(url, headers, timeout)
    if error:
        return None, error, False

    link, reason, is_trial = judge_result(payload, status)
    if reason:
        logger.warning(
            "官方接口不给整首: id=%s status=%s reason=%s trial=%s",
            song_id,
            status,
            reason,
            is_trial,
        )
        return None, reason, is_trial

    # 接口判定通过：它给的直链不用，统一换成外链跳转入口（urllib 默认跟随 302）
    logger.debug("接口直链不可用，改用外链下载: id=%s api_link=%s", song_id, link)
    media_url = MEDIA_OUTER_URL.format(song_id=song_id)
    path, download_reason = _download_file(
        media_url,
        dest,
        timeout,
        headers=_media_headers(cookie),
        prefix=f"nt_{song_id}",
    )
    if not path:
        return None, download_reason or REASON_DOWNLOAD, False

    length = _probe_duration_ms(path)
    if length is None:
        logger.warning("下载完量不到真实时长，按失败处理: id=%s file=%s", song_id, path)
        _remove_quietly(path)
        return None, REASON_DL_NO_TIME, False
    if length < MIN_FULL_LENGTH_MS:
        seconds = int(round(length / 1000))
        logger.warning("下载到的不是整首: id=%s 时长=%sms", song_id, length)
        _remove_quietly(path)
        return None, REASON_DL_TOO_SHORT.format(seconds=seconds), True
    return path, "", False

