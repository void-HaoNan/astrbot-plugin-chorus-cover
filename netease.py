"""网易云整首歌下载：官方取直链接口 + 洛雪源兜底（chorus_cover 自维护分支）。

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

   任一条不满足都算失败并给出简短中文原因。洛雪兜底返回体里通常**没有**
   ``time`` / ``freeTrialInfo``（它的协议只有 ``data`` 链接和 ``msg``），
   所以兜底会先按返回体判一次，下完文件再用 ``ffprobe`` 量真实时长，
   同样按 ``>= 80000ms`` 卡一遍——60 秒试听片段因此在兜底这条路上也过不去。
   拿不到时长时按失败处理（宁可不出歌，也不把 60 秒片段丢给中间层）。
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

#: 官方取直链接口（GET）
OFFICIAL_URL = "https://music.163.com/api/song/enhance/player/url"
#: 官方接口要求的请求头（2026-10-27 实测）
DEFAULT_USER_AGENT = "Mozilla/5.0"
OFFICIAL_REFERER = "https://music.163.com"

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
REASON_CODE = "接口 code={code}"
REASON_REQUEST_FAILED = "接口请求失败"
REASON_LX_NO_BASE = "没配置洛雪地址"
REASON_LX_HTTP = "兜底接口返回 HTTP {status}"
REASON_LX_CODE = "兜底 code={code}"
REASON_LX_NO_URL = "兜底没给链接"
REASON_LX_NO_TIME = "兜底没给时长，无法确认是整首"


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


def _download_file(
    url: str,
    dest_dir: str,
    timeout: float,
    *,
    referer: str = "",
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
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if referer:
        headers["Referer"] = referer

    written = 0
    expected = 0
    try:
        request = urllib.request.Request(url, headers=headers, method="GET")
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
    """走官方接口取整首歌并下载到本地。

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
    headers = {
        "Cookie": f"MUSIC_U={cookie}",
        "Referer": OFFICIAL_REFERER,
        "User-Agent": DEFAULT_USER_AGENT,
    }

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

    path, download_reason = _download_file(
        link,
        dest,
        timeout,
        referer=OFFICIAL_REFERER,
        prefix=f"nt_{song_id}",
    )
    if not path:
        return None, download_reason or REASON_DOWNLOAD, False
    return path, "", False


def download_via_lx(
    song_id: Any,
    base_url: str,
    auth_key: str,
    quality: str = "320k",
    dest_dir: Optional[str] = None,
    timeout: float = 120,
    source: str = "wy",
) -> Tuple[Optional[str], str, bool]:
    """洛雪源兜底：``GET /link/<源>/<id>/<音质>``。

    只用于官方接口失败后的最后一条路。返回体通常只有 ``data``（链接）和
    ``msg``，所以下完文件后还要量一次真实时长，避免把 60 秒试听片段交出去。

    Returns:
        ``(本地路径 或 None, 失败原因, 是否试听)``。
    """
    song_id = str(song_id if song_id is not None else "").strip()
    base_url = str(base_url or "").strip().rstrip("/")
    if not song_id.isdigit():
        return None, REASON_BAD_ID, False
    if not base_url:
        return None, REASON_LX_NO_BASE, False

    dest = dest_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_audio")
    url = f"{base_url}/link/{source}/{song_id}/{quality or '320k'}"
    headers = {
        "X-LxM-Auth": str(auth_key or ""),
        "User-Agent": DEFAULT_USER_AGENT,
    }

    status, payload, error = _fetch_json(url, headers, timeout)
    if error:
        return None, error, False
    if status != 200:
        return None, REASON_LX_HTTP.format(status=status), False
    if not isinstance(payload, (dict, list)):
        return None, REASON_BAD_JSON, False

    # 洛雪自己的协议里没有 code 强制字段；有的话仍按 200 校验
    code = payload.get("code") if isinstance(payload, dict) else None
    if code is not None:
        try:
            code_ok = int(str(code)) == 200
        except (TypeError, ValueError):
            code_ok = False
        if not code_ok:
            return None, REASON_LX_CODE.format(code=code), False

    link, reason, is_trial = judge_result(
        payload,
        status,
        require_code=False,
        require_time=False,
    )
    if is_trial:
        return None, reason or REASON_TRIAL, True
    if not link:
        return None, reason or REASON_LX_NO_URL, False

    path, download_reason = _download_file(
        link,
        dest,
        timeout,
        prefix=f"lx_{song_id}",
    )
    if not path:
        return None, download_reason or REASON_DOWNLOAD, False

    # 返回体没有时长时，用文件真实时长兜住"60 秒试听"这一类
    length = _pick_time_ms(payload)
    if length is None:
        length = _probe_duration_ms(path)
    if length is None:
        _remove_quietly(path)
        return None, REASON_LX_NO_TIME, False
    if length < MIN_FULL_LENGTH_MS:
        logger.warning("兜底给的还是短片段: id=%s 时长=%sms", song_id, length)
        _remove_quietly(path)
        return None, REASON_TRIAL, True
    return path, "", False
