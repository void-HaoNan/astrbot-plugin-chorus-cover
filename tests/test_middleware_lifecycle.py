"""中间层启停的纯逻辑：找目录、拼命令、归属判断（0.19.17）。

这些函数不 import astrbot，所以能在 CI 里直接测；main.py 只负责调度进程。
"""

import json
import os

import middleware_lifecycle as mw


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("")


def test_find_chorus_dir_prefers_configured(tmp_path):
    configured = tmp_path / "custom-mw"
    _touch(str(configured / "app.py"))
    env_dir = tmp_path / "env-mw"
    _touch(str(env_dir / "app.py"))

    found = mw.find_chorus_dir(str(configured), env={"CHORUS_DIR": str(env_dir)})
    assert found == str(configured)


def test_find_chorus_dir_falls_back_to_env(tmp_path):
    env_dir = tmp_path / "env-mw"
    _touch(str(env_dir / "app.py"))
    assert mw.find_chorus_dir("", env={"CHORUS_DIR": str(env_dir)}) == str(env_dir)


def test_find_chorus_dir_sibling_of_rvc_root(tmp_path):
    rvc = tmp_path / "RVC" / "assets" / "weights"
    os.makedirs(rvc)
    sibling = tmp_path / "chorus-mw"
    _touch(str(sibling / "app.py"))
    assert mw.find_chorus_dir("", env={}, models_dir=str(rvc)) == str(sibling)


def test_find_chorus_dir_returns_empty_when_missing(tmp_path):
    assert mw.find_chorus_dir("", env={}) == ""
    assert mw.find_chorus_dir(str(tmp_path / "nope"), env={}) == ""


def test_start_stop_commands_use_bundled_script():
    start = mw.start_argv(r"D:\mw")
    stop = mw.stop_argv(r"D:\mw")
    assert start[:5] == ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
    assert start[-1].endswith(os.path.join("scripts", "start.ps1"))
    assert stop[-1] == "-Stop"
    assert stop != start


def test_marker_roundtrip(tmp_path):
    path = mw.marker_path(str(tmp_path))
    assert mw.read_marker(path) == {}
    assert mw.write_marker(path, {"chorus_dir": r"D:\mw", "astrbot_pid": 42})
    data = mw.read_marker(path)
    assert data["chorus_dir"] == r"D:\mw"
    assert data["astrbot_pid"] == 42
    mw.remove_marker(path)
    assert not os.path.exists(path)


def test_should_stop_only_for_own_process():
    assert mw.should_stop({"astrbot_pid": 100, "adopted_at": 0}, 100, 10.0)
    assert not mw.should_stop({"astrbot_pid": 999, "adopted_at": 0}, 100, 10.0)
    assert not mw.should_stop({}, 100, 10.0)


def test_should_stop_skips_reload_adoption():
    marker = {"astrbot_pid": 100, "adopted_at": 12.0}
    assert not mw.should_stop(marker, 100, 10.0)


def test_chorus_candidates_order(tmp_path):
    models = tmp_path / "RVC" / "assets" / "weights"
    os.makedirs(models)
    candidates = mw.chorus_dir_candidates("cfg", {"CHORUS_DIR": "env"}, str(models))
    assert candidates[0] == "cfg"
    assert candidates[1] == "env"
    assert candidates[2] == str(tmp_path / "chorus-mw")


def test_parse_listener_pid_matches_only_listening_rows():
    text = "\n".join(
        [
            "活动连接",
            "  协议  本地地址          外部地址        状态           PID",
            "  TCP    0.0.0.0:3333           0.0.0.0:0              LISTENING       39948",
            "  TCP    127.0.0.1:3333         127.0.0.1:50000        ESTABLISHED     1111",
            "  TCP    0.0.0.0:33330          0.0.0.0:0              LISTENING       2222",
            "  UDP    0.0.0.0:3333           *:*                                    3333",
        ]
    )
    assert mw.parse_listener_pid(text, 3333) == 39948
    assert mw.parse_listener_pid(text, 33330) == 2222
    assert mw.parse_listener_pid(text, 9999) == 0
    assert mw.parse_listener_pid("", 3333) == 0


def test_parse_listener_pid_accepts_localized_state_column():
    # 中文系统的 netstat 状态列可能是「侦听」，解析不认文字，只认地址
    text = "  TCP    127.0.0.1:3333         0.0.0.0:0              侦听           1234"
    assert mw.parse_listener_pid(text, 3333) == 1234


def test_marker_owner_handles_bad_values():
    assert mw.marker_owner({"astrbot_pid": "42"}) == 42
    assert mw.marker_owner({"astrbot_pid": "x"}) == 0
    assert mw.marker_owner({}) == 0


def test_pid_alive_for_self_and_dead_pid():
    assert mw.pid_alive(os.getpid())
    assert not mw.pid_alive(0)
    # 0x7FFFFFFF 在 Windows 上基本不可能存在，OpenProcess 会失败
    assert not mw.pid_alive(0x7FFFFFFF)


def test_find_rvc_root_from_models_dir(tmp_path):
    root = tmp_path / "RVC"
    python = root / "runtime" / "python.exe"
    _touch(str(python))
    models = root / "assets" / "weights"
    os.makedirs(models)
    assert mw.find_rvc_root(str(models), env={}) == str(root)
    assert mw.find_rvc_root(str(tmp_path / "elsewhere"), env={"CHORUS_RVC_ROOT": str(root)}) == str(root)
    assert mw.find_rvc_root("", env={}) == ""

