"""中间层的启停：找目录、拼命令行、查进程、记归属（0.19.17）。

插件自己拉起 chorus-mw 的时候，要能回答四个问题：

1. 中间层装在哪？——``chorus_dir`` 配置 → ``CHORUS_DIR`` 环境变量 → RVC 整合包旁边的
   ``chorus-mw``；
2. 怎么起、怎么停？——统一用中间层自带的 ``scripts\\start.ps1``（它自己会体检、等端口、
   停的时候连旧守护和常驻 worker 一起结束）；
3. 3333 上现在是谁？——按端口查监听进程，用命令行判断是不是 python 跑 ``app.py``；
4. 这个中间层是不是我拉起的？——在插件数据目录写一个 ``middleware.json`` 记住 pid 和时间。
   只有归属对得上、或者确认是旧实例时才接管，别的程序占着 3333 一律不碰。

这些函数不 import astrbot，本机进程相关的那几个只在 Windows 上调用，方便单测。
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, Iterable, Mapping, Optional

APP_FILE = "app.py"
START_SCRIPT = os.path.join("scripts", "start.ps1")
MARKER_NAME = "middleware.json"
CREATE_NO_WINDOW = 0x08000000


def chorus_dir_candidates(
    configured: str = "",
    env: Optional[Mapping[str, str]] = None,
    models_dir: str = "",
) -> list[str]:
    """按优先级列出可能的中间层目录（只列，不判断存在）。"""
    env = os.environ if env is None else env
    out: list[str] = []
    if configured:
        out.append(configured)
    env_dir = (env.get("CHORUS_DIR") or "").strip()
    if env_dir:
        out.append(env_dir)
    if models_dir:
        root = os.path.dirname(os.path.dirname(os.path.abspath(models_dir)))
        out.append(os.path.join(os.path.dirname(root), "chorus-mw"))
        out.append(os.path.join(os.path.dirname(os.path.dirname(root)), "chorus-mw"))
        out.append(os.path.join(root, "chorus-mw"))
    return out


def find_chorus_dir(
    configured: str = "",
    env: Optional[Mapping[str, str]] = None,
    models_dir: str = "",
) -> str:
    """返回第一个真的含 ``app.py`` 的目录，找不到返回空串。"""
    for candidate in chorus_dir_candidates(configured, env, models_dir):
        if candidate and os.path.isfile(os.path.join(candidate, APP_FILE)):
            return os.path.abspath(candidate)
    return ""


def rvc_root_candidates(models_dir: str = "", env: Optional[Mapping[str, str]] = None) -> list[str]:
    """RVC 整合包根目录的候选：模型目录往上找，再退回环境变量。

    中间层启动必须要 ``CHORUS_RVC_ROOT``，但用户机器上一般不会永久设这个变量，
    所以能从模型目录（``<RVC>\\assets\\weights``）推出来就从这里推。
    """
    env = os.environ if env is None else env
    out: list[str] = []
    if models_dir:
        current = os.path.abspath(models_dir)
        for _ in range(4):
            out.append(current)
            parent = os.path.dirname(current)
            if parent == current:
                break
            current = parent
    env_root = (env.get("CHORUS_RVC_ROOT") or "").strip()
    if env_root:
        out.append(env_root)
    return out


def find_rvc_root(models_dir: str = "", env: Optional[Mapping[str, str]] = None) -> str:
    """找到第一个 ``runtime\\python.exe`` 真的存在的 RVC 整合包根目录。"""
    for candidate in rvc_root_candidates(models_dir, env):
        if candidate and os.path.isfile(os.path.join(candidate, "runtime", "python.exe")):
            return os.path.abspath(candidate)
    return ""


def _powershell(script_args: Iterable[str]) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *script_args]


def start_argv(chorus_dir: str) -> list[str]:
    return _powershell([os.path.join(chorus_dir, START_SCRIPT)])


def stop_argv(chorus_dir: str) -> list[str]:
    return _powershell([os.path.join(chorus_dir, START_SCRIPT), "-Stop"])


def marker_path(plugin_data_dir: str) -> str:
    return os.path.join(plugin_data_dir, MARKER_NAME)


def read_marker(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_marker(path: str, data: Mapping[str, Any]) -> bool:
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def remove_marker(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def marker_owner(marker: Mapping[str, Any]) -> int:
    try:
        return int(marker.get("astrbot_pid") or 0)
    except (TypeError, ValueError):
        return 0


def pid_alive(pid: int) -> bool:
    """进程还在不在。Windows 用 WaitForSingleObject，别用 os.kill（会真杀进程）。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            SYNCHRONIZE = 0x00100000
            WAIT_TIMEOUT = 0x00000102
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            handle = kernel32.OpenProcess(SYNCHRONIZE, False, int(pid))
            if not handle:
                return False
            try:
                return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
            finally:
                kernel32.CloseHandle(handle)
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def parse_listener_pid(text: str, port: int) -> int:
    """从 ``netstat -ano`` 的输出里找出监听指定端口的 pid。

    不认状态列的文字（中文系统会本地化），只认「本端是 :port、对端是 :0」，
    这样 LISTENING / 侦听 都能命中。
    """
    for raw in (text or "").splitlines():
        parts = raw.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        local, foreign, pid = parts[1], parts[2], parts[-1]
        if local.rsplit(":", 1)[-1] != str(port):
            continue
        if foreign.rsplit(":", 1)[-1] != "0":
            continue
        if pid.isdigit():
            return int(pid)
    return 0


def listener_pid(port: int, timeout: float = 10.0) -> int:
    """查监听端口的 pid；查不到返回 0（非 Windows 或命令失败也一样）。"""
    if os.name != "nt" or port <= 0:
        return 0
    try:
        proc = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    text = (proc.stdout or b"").decode("utf-8", "ignore")
    if not text:
        text = (proc.stdout or b"").decode("mbcs", "ignore")
    return parse_listener_pid(text, port)


def should_stop(
    marker: Mapping[str, Any], own_pid: int, stopped_at: float
) -> bool:
    """插件停掉时要不要关中间层。

    只有「这条记录写的就是当前这个 AstrBot 进程」才管；如果停止之后有新实例接管过
    （``adopted_at > stopped_at``，说明只是插件重载），就不关——重载不该把正在跑的
    翻唱掐掉。
    """
    owner = marker_owner(marker)
    if owner != own_pid:
        return False
    try:
        adopted = float(marker.get("adopted_at") or 0)
    except (TypeError, ValueError):
        adopted = 0.0
    return adopted <= stopped_at
