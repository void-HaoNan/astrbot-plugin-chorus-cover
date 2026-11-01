"""封面 / 歌词的统一接口：四个音源一套标准，谁有就用谁的。

调用方（直播中台、插件自己）只用这一个函数：

    fetch_media_info(song, artist="", platform="", media_id="") -> dict

返回固定形状：

    {
      "ok": bool,            # 至少拿到封面或歌词
      "cover": bytes,        # 封面图原始字节（jpg/png），没有就是 b""
      "lrc": str,            # LRC 文本（标准 [mm:ss.xx] 格式），没有就是 ""
      "title": str, "artist": str,
      "source": str,         # 实际给了数据的是哪个平台
      "tried": [...],        # 每个平台的尝试结果，方便排查
    }

查的顺序：先试调用方指定的平台（音频就是从那儿来的，最可能对得上），
再退到网易云，最后酷狗。QQ/酷我/酷狗各自用自己的接口，互不影响。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
METING_BASE = "https://api.qijieya.cn/meting/"
ORDER = ("netease", "qqmusic", "kugou", "kuwo")
DISPLAY = {"netease": "网易云", "qqmusic": "QQ音乐", "kugou": "酷狗", "kuwo": "酷我"}


# ------------------------------------------------------------------ 小工具
def _get(url: str, timeout: float = 10.0, headers: dict | None = None) -> bytes:
    request = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


def _meting(params: dict, timeout: float = 10.0):
    url = METING_BASE + "?" + urllib.parse.urlencode(params)
    return json.loads(_get(url, timeout).decode("utf-8", "ignore"))


def _looks_like_lrc(text: str) -> bool:
    """必须有时间戳才算歌词：没有时间轴的纯文本没法跟着播放走。"""
    return bool(re.search(r'\\[\\d{1,3}:\\d{2}(?:[.:]\\d+)?\\]', str(text or '')))


def _pick(hits, song: str, artist: str):
    """在搜索结果里挑最像的一首：歌名对上加 2 分，歌手对上加 3 分，live 扣 1 分。"""
    best, best_score = None, 0
    for item in hits or []:
        name = str(item.get("name") or item.get("songname") or "")
        who = str(item.get("artist") or item.get("singer") or "")
        if isinstance(who, list):
            who = "、".join(str(x) for x in who)
        score = 0
        if song and song in name:
            score += 2
        if artist and artist in who:
            score += 3
        if "live" in name.lower():
            score -= 1
        if score > best_score:
            best, best_score = item, score
    return best


# ------------------------------------------------------------------ 各平台
def _provider_netease(song: str, artist: str, media_id: str = "") -> dict:
    out = {}
    hit = None
    if media_id and str(media_id).isdigit():
        rows = _meting({"type": "song", "id": media_id})
        hit = rows[0] if isinstance(rows, list) and rows else None
    if hit is None:
        rows = _meting({"type": "search", "id": f"{song} {artist}".strip()})
        hit = _pick(rows if isinstance(rows, list) else [], song, artist)
    if not hit:
        return out
    out["title"] = str(hit.get("name") or "")
    out["artist"] = str(hit.get("artist") or "")
    pic, lrc = str(hit.get("pic") or ""), str(hit.get("lrc") or "")
    if pic:
        try:
            out["cover"] = _get(pic)
        except Exception:
            pass
    if lrc:
        try:
            text = _get(lrc).decode("utf-8", "ignore")
            if _looks_like_lrc(text):
                out["lrc"] = text
        except Exception:
            pass
    return out


def _provider_kugou(song: str, artist: str, media_id: str = "") -> dict:
    out = {}
    rows = _meting({"server": "kugou", "type": "search", "id": f"{song} {artist}".strip()})
    hit = _pick(rows if isinstance(rows, list) else [], song, artist)
    if not hit:
        return out
    out["title"] = str(hit.get("name") or "")
    out["artist"] = str(hit.get("artist") or "")
    lrc = str(hit.get("lrc") or "")
    if lrc:
        try:
            text = _get(lrc).decode("utf-8", "ignore")
            if _looks_like_lrc(text):
                out["lrc"] = text
        except Exception:
            pass
    return out


def _provider_kuwo(song: str, artist: str, media_id: str = "") -> dict:
    """酷我没有开放搜索 JSON，用 search.kuwo.cn 的伪字典字符串抠字段。"""
    out = {}
    keyword = urllib.parse.quote(f"{song} {artist}".strip())
    url = ("http://search.kuwo.cn/r.s?all=" + keyword +
           "&ft=music&itemset=web_2013&client=kt&pn=0&rn=5&rformat=json&encoding=utf8")
    try:
        raw = _get(url).decode("utf-8", "ignore")
    except Exception:
        return out
    blocks = raw.split("'MUSICRID':'MUSIC_")
    for block in blocks[1:]:
        rid = re.match(r"(\d+)", block)
        name = re.search(r"'SONGNAME':'([^']*)'", block)
        who = re.search(r"'ARTIST':'([^']*)'", block)
        if not rid or not name:
            continue
        out["title"] = name.group(1)
        out["artist"] = who.group(1) if who else ""
        score = (2 if song and song in out["title"] else 0) + \
                (3 if artist and artist in out["artist"] else 0)
        if score <= 0:
            continue
        try:
            data = json.loads(_get(f"http://m.kuwo.cn/newh5/singles/songinfoandlrc?musicId={rid.group(1)}"))
            rows = ((data.get("data") or {}).get("lrclist") or [])
            if rows:
                lines = []
                for row in rows:
                    try:
                        seconds = float(row.get("time") or 0)
                    except Exception:
                        continue
                    # 酷我给的是「秒」，统一转成 [mm:ss.xx] 和别的平台一个格式
                    mins, secs = divmod(seconds, 60)
                    lines.append(f"[{int(mins):02d}:{secs:05.2f}]{row.get('lineLyric') or ''}")
                out["lrc"] = "\n".join(lines)
        except Exception:
            pass
        return out
    return out


def _provider_qqmusic(song: str, artist: str, media_id: str = "") -> dict:
    out = {}
    keyword = urllib.parse.quote(f"{song} {artist}".strip())
    headers = {"User-Agent": UA, "Referer": "https://y.qq.com/"}
    try:
        data = json.loads(_get("https://c.y.qq.com/soso/fcgi-bin/search_for_qq_cp"
                               "?format=json&n=5&w=" + keyword, headers=headers))
    except Exception:
        return out
    items = (((data.get("data") or {}).get("song") or {}).get("list") or [])
    hit = None
    for item in items:
        name = str(item.get("songname") or item.get("name") or "")
        who = "、".join(str(s.get("name") or "") for s in (item.get("singer") or []))
        if song and song in name and (not artist or artist in who):
            hit = item
            break
    if hit is None:
        return out
    out["title"] = str(hit.get("songname") or hit.get("name") or "")
    out["artist"] = "、".join(str(s.get("name") or "") for s in (hit.get("singer") or []))
    album_mid = str(hit.get("albummid") or "")
    song_mid = str(hit.get("songmid") or "")
    if album_mid:
        try:
            out["cover"] = _get(f"https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg")
        except Exception:
            pass
    if song_mid:
        try:
            payload = json.loads(_get(
                "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
                f"?songmid={song_mid}&format=json&nobase64=0", headers=headers))
            text = payload.get("lyric") or ""
            if text:
                import base64
                out["lrc"] = base64.b64decode(text).decode("utf-8", "ignore")
        except Exception:
            pass
    return out


PROVIDERS = {
    "netease": _provider_netease,
    "kugou": _provider_kugou,
    "kuwo": _provider_kuwo,
    "qqmusic": _provider_qqmusic,
}


# ------------------------------------------------------------------ 统一入口
def fetch_media_info(song: str, artist: str = "", platform: str = "",
                     media_id: str = "", timeout: float = 10.0) -> dict:
    """四个平台一套标准：先试指定平台，再网易云，最后酷狗。"""
    result = {"ok": False, "cover": b"", "lrc": "", "title": "", "artist": "",
              "source": "", "tried": []}
    song = str(song or "").strip()
    if not song:
        return result

    order = []
    for name in (platform, *ORDER):
        if name in PROVIDERS and name not in order:
            order.append(name)

    for name in order:
        try:
            data = PROVIDERS[name](song, artist, media_id if name == platform else "")
        except Exception as error:  # noqa: BLE001
            result["tried"].append((name, f"异常 {type(error).__name__}"))
            continue
        got_cover = bool(data.get("cover"))
        got_lrc = bool(data.get("lrc"))
        result["tried"].append((name, f"封面{'+' if got_cover else '-'} 歌词{'+' if got_lrc else '-'}"))
        if not result["cover"] and got_cover:
            result["cover"] = data["cover"]
        if not result["lrc"] and got_lrc:
            result["lrc"] = data["lrc"]
        if not result["title"] and data.get("title"):
            result["title"] = data["title"]
        if not result["artist"] and data.get("artist"):
            result["artist"] = data["artist"]
        if result["cover"] and result["lrc"]:
            result["source"] = name
            break
    if not result["source"]:
        for name, _detail in result["tried"]:
            result["source"] = name
            break
    result["ok"] = bool(result["cover"] or result["lrc"])
    return result
