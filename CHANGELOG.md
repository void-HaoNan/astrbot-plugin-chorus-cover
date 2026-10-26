# 更新日志

本文件记录 **astrbot_plugin_chorus_cover**（副歌翻唱 · 自维护分支）的变更。
上游 `sdfsfsk/matsuko_cover` 的历史日志请见上游仓库，此处只记本分支的差异。

## v0.2.0（2026-10-27）

网易云点歌改走**官方取直链接口 + MUSIC_U cookie**，洛雪源只当兜底；两条路都按"整首"标准过滤试听片段，cookie 连续失效会提醒管理员。

### 新增

- 新增 `netease.py`（纯标准库，不新增第三方依赖）：
  - `download_by_id(song_id, cookie, quality_br=320000, dest_dir, timeout=120) -> (路径|None, 失败原因, 是否试听)`：调官方接口 `GET https://music.163.com/api/song/enhance/player/url?ids=[<id>]&br=<码率>`，带 `Cookie: MUSIC_U=...`、`Referer: https://music.163.com`、`User-Agent: Mozilla/5.0`；成功就流式下载到本地，单文件上限 60MB。
  - `download_via_lx(...)`：洛雪源兜底 `GET <lx_source_base>/link/wy/<id>/<音质>`，带 `X-LxM-Auth`。
  - `judge_result(...)` / `is_cookie_failure(...)`：把"整首"判定和"这次算不算 cookie 问题"抽成纯函数，方便单测。
- 配置项 7 个：`netease_cookie`、`netease_quality`、`lx_source_base`、`lx_source_key`、`enable_lx_fallback`、`alert_admin_on_cookie_expired`、`cookie_alert_interval_hours`。
- cookie 失效提醒：连续 3 次取歌都因为 cookie 相关问题失败（没配置 / HTTP 401 / `code != 200` / 只给试听）时，私聊 AstrBot 全局配置里的 `admins_id`；读不到管理员就发回触发这次点歌的会话；同一失效状态按 `cookie_alert_interval_hours` 去重，取歌成功后清空状态。
- `outbound.py` 新增 `alert` 出口（管理员提醒），与 `start/progress/retry/failed/done` 共用同一个"台词交给模型现编"的出口；`say()` 现在返回是否真的发出去（`bool`），方便管理员会话发不出去时降级重发。

### 变化

- **网易云不再把歌曲 id 直接交给中间层**（中间层不认 id）：`_do_cover`（LLM 工具 / 批量翻唱走这条）和 `_send_song`（卡片选歌后走这条）两处都改成"先下载成文件，再把本地路径交给中间层"。
- **试听判定**：成功必须同时满足 HTTP 200、`code == 200`、`data[0].url` 非空、`data[0].freeTrialInfo is None`、`data[0].time >= 80000`（毫秒）。任一条不满足都算失败，失败原因（没拿到链接 / 只给了试听 / 接口 code=... / 接口返回 HTTP ... / 下载中断）只进日志和上层统一失败出口。
- **洛雪只作兜底**：官方接口失败后才用同一个数字 id 去 `/link/wy/<id>/320k`。洛雪返回体只有 `data`（链接）和 `msg`，没有时长字段，所以兜底路径下完文件后用 `ffprobe` 量真实时长，同样按 `>= 80000ms` 卡一遍，60 秒试听片段因此过不去；量不到时长按失败处理（宁可不出歌，也不把片段交给中间层）。
- 网易云这条路的下载文件与 QQ 音乐一致，落在 `temp_audio/`，任务结束由 `finally` 清理。

### 验证

- `netease.py` / `main.py` / `outbound.py` 三个文件 `py_compile` 通过。
- 判定逻辑离线自检 23 项全过：官方成功、试听、`code=404`、时长不足、没链接、HTTP 401、没 code、没时长、洛雪 `data` 直链形状、洛雪带 `freeTrialInfo`、非 cookie 原因不误报、空 cookie、非法 id、洛雪没配地址、duration 秒/毫秒兜底。
- `outbound.say` 行为自检 8 项全过：`alert` 只发一条且走模型文案、`progress` 静音返回 `False`、未知类型静音、发送异常返回 `False`、目标对象返回 `False` 时调用方可降级、拿不到 provider 时 `alert` 退回一句兜底中文。
- `ffprobe` 时长闸门实测：90 秒文件量到 90000ms（判为整首），30 秒文件量到 30000ms（判为试听）。
- **未覆盖**：真实 cookie 下的官方接口下载、真实洛雪兜底（本轮不跑长测试；实测洛雪 `/link/wy/.../320k` 当前返回 503，服务在但源没给链接），以及中间层真正吃到本地文件的端到端翻唱。

## v0.1.0（2026-10-27）

首个自维护版本，基线为上游 **sdfsfsk/matsuko_cover v2.13.0**，许可证 **AGPL-3.0**。

### 新增

- 新增 `outbound.py`（统一对话出口 `Outbound`）：把原先硬编码直接发给用户的三类文本——**进度提示**、**风控重试提示**、**报错详情**——收敛到一个出口，台词交给 AstrBot 当前使用的人格模型现编，插件只提供事实（歌名、模型、来源、失败原因）。
- 新增配置项 `notify_progress`、`notify_retry`（均为 `bool`，缺省 `false`）。

### 变化

- **进度提示 / 重试提示默认静音**：两个开关缺省关闭，关掉时一条都不发；打开后也只由模型说一句人话，不再刷"⏳ 遇到风控，正在自动重试…"这类模板句。
- **失败只发一句话**：失败时不再把整段 `result` 字符串（重试次数、错误码、可能原因清单）甩给用户，技术细节只写 `logger`；用户看到的是一句"这首没唱成，换个歌名我再试一次"级别的人话。
- **工具返回值去装饰**：`rvc_cover` / `svc_cover` / `svcvc_cover` / `smart_cover` 不再返回"🎵 正在从【X】用【Y】翻唱《Z》…请稍等"，改为一句中性短句交给 LLM 组织措辞（避免"工具结果 + LLM 回复"两次说话）。
- **失败判断去关键词**：`_smart_cover_async`（以及批量翻唱）只认 `result.startswith("❌")` 或 `result.startswith("FAIL:")`，删掉"失败/错误/超时/未找到/无法获取/触发风控/当前没有/已禁用"的关键词匹配——正常文案里带"失败"两个字会被误判成任务失败。`_do_cover` 的返回值协议不变，保留 `❌` 前缀兼容现有返回点。
- 出口层自身异常（拿不到 provider、模型调用失败、发送失败）全部吞掉并退回极短兜底文本，只记 `warning`，不影响翻唱主流程。

### 修复

- **QQ 音乐 mid 解析**：新版 `qqmusic-api-python` 返回结构里 `mid` 可能已经是字符串，直接读 `obj.mid` 会抛 `'str' object has no attribute 'mid'`（日志里表现为"官方API获取失败"）。新增 `_extract_mid()`：有 `mid` 属性就取 `mid`，本身是字符串就用它，其余视为拿不到；拿不到时记日志并降级，不把异常抛给用户。
- **移除失效的备选音源接口**：`api.lolimi.cn` 域名已无法解析（2026-10-27 实测 `getaddrinfo failed`），该分支删除并短路返回，不再让每次重试白等一次 15 秒网络超时。

### 验证

- 五个 Python 文件 `py_compile` 全通过。
- 全目录检索确认已无 `遇到风控，正在自动重试`、`正在从【` 这类硬编码文案，统一出口接线 17 处。
- `outbound.py` 在 AstrBot 运行环境（uv 工具虚拟环境 python 3.12）跑行为测试 9 项全过：进度/重试默认静音、失败走模型、模型不可用退回兜底、`event.send` 抛异常被吞、开关打开后进度可发、未知类型静音。
- 线上加载验证：AstrBot 重启后日志显示 `Plugin astrbot_plugin_chorus_cover (v0.1.0) by void-HaoNan`、`Added llm tool: smart_cover`、平台钩子正常，无异常堆栈；配置从上游插件迁入后 `rvc_base_url`、8 个模型、两个新开关均正确。
- 未覆盖：`main.py` 17 处接线的运行时行为（需要真实点一首歌才能验证）。

### 说明

- 本分支**不再跟随上游更新**，需要上游新功能请直接使用上游仓库版本。
- `LICENSE` 保持上游原样（AGPL-3.0），修改声明见 `NOTICE.md`。
