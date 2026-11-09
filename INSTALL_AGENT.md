# 给 agent 的安装与验收指南

这份文档是写给「帮用户装插件的 agent」看的：按顺序做，每一步都有可验证的结果。
给人类看的简版在 [INSTALL.md](INSTALL.md)。

> 先记住一条：**中间层 3333 由插件托管，不要用 `start_supervisor.ps1`，也不要单独开守护窗口。**
> 插件启动时会自己拉起、退出时自己关掉；装了守护会和插件互相抢端口，关 AstrBot 也留进程。

## 0. 先确认边界

- 本插件只做「取歌 → 分离 → RVC 变声 → 混音 → 发回会话」，**不带任何模型权重**。
- 需要本机有 RVC 整合包（`runtime\python.exe`、`ffmpeg.exe`、`assets\weights`）和中间层 `chorus-mw`。
- 不要改 AstrBot 核心，不要动别的插件源码；只改本插件目录与 `data/config/` 下自己的配置。

## 1. 确认宿主

1. AstrBot ≥ 4.16，`data/` 目录在用户目录下（Windows 常见 `C:\Users\<user>\data`）。
2. 插件目录存在：`data/plugins/astrbot_plugin_chorus_cover`，`metadata.yaml` 里版本号能对上。
3. 记下 AstrBot 版本与插件版本，最后汇报要用。

## 2. 装中间层（不要启动它）

1. 目标版本 **chorus-mw ≥ 0.9.16**（0.9.16 起有父进程看护，`start.ps1 -Stop` 会连旧守护一起收）。
2. 用仓库里的 `scripts/install.bat` 或手动：

```powershell
git clone https://github.com/void-HaoNan/chorus-mw
cd chorus-mw
# 只装依赖，不要在这里启动（启动交给插件）
python -m pip install --target libs_web -r requirements.txt
python -m pip install --target libs -r requirements-worker.txt
```

3. 确认真能跑（临时启动一次再停掉，验证依赖完整）：

```powershell
$env:CHORUS_RVC_ROOT = 'D:\你的RVC整合包根目录'
$env:CHORUS_PYTHON   = 'C:\...\Python312\python.exe'
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
# 看到「就绪」即可；接着必须停掉，别留着
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Stop
```

4. 验证：`start.ps1 -Status` 显示「未运行」，且没有「旧守护」一行。

## 3. 配插件

在 `data/config/astrbot_plugin_chorus_cover_config.json` 里确认：

| 键 | 期望 |
|---|---|
| `rvc_base_url` | `http://127.0.0.1:3333/`（结尾带斜杠） |
| `auto_middleware` | `true`（默认；插件托管 3333） |
| `chorus_dir` | 中间层目录绝对路径（有 `app.py` 和 `scripts\start.ps1`） |
| `rvc_root` | RVC 整合包根目录（有 `runtime\python.exe`） |
| `chorus_python` | 跑中间层的 Python（3.10~3.12，装过中间层依赖） |
| `enable_rvc` | `true` |
| `language_model_zh/ja/en` | 按用户有的模型填，没有就留空 |
| `index_rate` | 默认 `0.8`，别随手改 |
| `persona_song_pick_enable` | 用户想要「按人设选歌」时打开 |

改完重启 AstrBot，日志里应出现 `Plugin astrbot_plugin_chorus_cover (0.19.17)`，
并在 10~40 秒内出现 `中间层已随插件启动`（或 `中间层已在运行…继续托管`）。

## 4. 验收（逐条给用户看结果）

1. **启动链**：重启 AstrBot，`scripts\start.ps1 -Status` 显示 3333 在听、进程是 `python -X utf8 app.py`；
   日志里有 `中间层已随插件启动`，`middleware.json` 的 `astrbot_pid` 是当前 AstrBot 的 pid。
2. **自检**：群里发 `/环境自检`：后端、模型数、运行时、ffmpeg、三档音色、取歌服务逐项有结论，
   并有一行「中间层由本插件托管」。
3. **翻唱**：点一首中文歌走完整流程，收到音频即通过；失败在日志里搜 `CoverFlow`。
4. **排队**：连发两首，第二首应被「排队」接住，而不是被拒绝。
5. **无人设选歌**：让用户发「唱首歌」不带歌名；若开了 `persona_song_pick_enable`，应挑一首非烂大街的。
6. **无残留（必做）**：关掉 AstrBot（正常关或任务管理器强杀都行），等 5 秒，确认：
   - `3333` 没有监听（`Test-NetConnection 127.0.0.1 -Port 3333` 失败）；
   - 没有 `app.py` / `resident_worker.py` / `start_supervisor.ps1` 的 python/powershell 进程；
   - 再开 AstrBot，10~40 秒后 3333 自动回来。

## 5. 已知边界（别当成 bug 报）

- 副歌里如果有说唱/念白段，RVC 转出来会糊；用 `chorus_start_seconds` 指定干净起点。
- 这个 RVC 整合包不支持 `harvest`（只认 pm/rmvpe/fcpe）。
- 自动移调默认关闭（实测不移调更贴音色）；需要时设 `CHORUS_AUTO_PITCH=1`。
- 语音转写受智谱 30 秒限制，引用长语音会失败。
- 中间层首次冷启动要 import torch，10~40 秒是正常的；插件最多等 90 秒。
- `auto_middleware` 只支持 Windows；Linux/Docker 请用 systemd 让中间层常驻并把这一项关掉。

## 6. 汇报模板

```
插件：astrbot_plugin_chorus_cover 0.19.17
中间层：chorus-mw 0.9.16（3333 在线，插件托管）
模型：<n> 个；三档音色：zh=… ja=… en=…
实测：启动 ✓ / 取歌 ✓ / 翻唱 ✓ / 排队 ✓ / 自检 ✓ / 关 AstrBot 无残留 ✓ / 再启动自动恢复 ✓
未验：<列出没跑到的>
```

## 7. 自己训练模型时

- `train.py` 的 `-sw 1` 会在 `assets/weights` 里留一堆 `xxx_e30`、`xxx_e60` 检查点，
  它们会出现在音色列表里。训练时用 `-sw 0`，或训练完把这些文件移到 `logs/` 下。
- 最终模型起个能被看懂的名字（例如「角色名+语言」），中间产物不要留在 `weights` 里。
