# 更新日志

本文件记录 **astrbot_plugin_chorus_cover**（副歌翻唱 · 自维护分支）的变更。
上游 `sdfsfsk/matsuko_cover` 的历史日志请见上游仓库，此处只记本分支的差异。

## v0.6.0（2026-10-27）

新增「唱多长」配置：副歌片段 / 整首翻唱 / 自定义时长。后端 `chorus-mw` 同步升到 0.7.0，
默认链路从「整首分离再切」改成「先切 60 秒再分离」，同一首 4:39 的歌实测 72.2 秒 → 32.6 秒。

### 新增

- **`render_mode`**：`chorus`（默认，只翻副歌片段，45 秒）/ `full`（整首翻唱）/
  `custom`（自定义时长，用 `chorus_seconds`）。插件按名字探测后端 `/convert` 是否支持
  `render_mode`，老后端没有这个参数就整组不传、仍按副歌模式处理，不会报 invalid keyword。
- **`chorus_seconds`**：20~180 秒，默认 45；`custom` 模式按它定长，`chorus` 模式也用它当片段长度。
- **完整翻唱更慢**：`full` 要分离整首、变声整首，耗时可能是副歌模式的 5~10 倍，显存占用更高。
  4:39 的歌整首跑通常要几分钟以上，默认 `inference_timeout=300` 很可能不够；
  要整首翻唱请把 `inference_timeout` 和 `task_timeout_seconds` 一起调大。

### 说明

- 时长参数只对 RVC 后端（`chorus-mw` 0.7.0+）生效；SVC / SoulX-SVCVC 后端没有这组参数，
  插件自动跳过，行为不变。
- 中间层侧改动见 `chorus-mw` 的 CHANGELOG 0.7.0：先切后分离、常驻 worker、去混响与伴奏处理并行。

### 验证

- `py_compile` 通过：`main.py`。
- 实测同一首 4:39 的 mp3：`chorus` 端到端 34.1 秒（成品 45.0 秒 wav），
  `custom=30` 端到端 27.9 秒（成品 30.8 秒 wav），`full` 用 100 秒素材 52.7 秒跑通。
- 未重启 AstrBot（由用户重启）。

## v0.5.0（2026-10-27）

取歌/下载实现整套换成点歌插件 `astrbot_plugin_music` 那套，删掉自己写的那套和几条说明性日志横幅。

### 变更

- **新增 `netease_fetch.py`**：照搬点歌插件的取歌链路——搜歌 `POST http://music.163.com/api/search/get/web`
  （`s` / `limit` / `type=1` / `offset=0`，带 `appver=2.0.2`）、主路直链
  `GET https://api.qijieya.cn/meting/?type=song&id=<id>`、备用直链 NodeJS API
  （先 `/song/url/v1?level=…` 再 `/song/url`，可带 `MUSIC_U`）。
  落盘同样照搬：`temp_audio/` + `uuid4().hex` 命名、按 URL 后缀白名单、1024 字节分片、
  HTTP 非 200 / 返回错误页 / 超 60MB / 内容不全一律删半截文件。
  点歌插件里发卡片、发语音/文件、歌词与评论渲染、封面卡片等逻辑没有搬。
- **删除 `netease.py`**：原先自己写的「官方接口判定 + 外链兜底」实现（含 `download_by_id`
  / `download_by_api_service`）整体移除，改由 `netease_fetch.NeteaseFetcher` 承担。
- `_fetch_netease_audio` 改为直接 `await` 取歌器（不再 `asyncio.to_thread`），并保留
  cookie 失效连续计数与管理员提醒。
- `_search_netease_songs` 先用点歌插件那套搜索，失败/无结果再退回插件原来的搜索器。
- `_prepare_song_audio` 对外契约不变：`(本地文件路径 | None, 失败原因, 是否试听)`；
  **80 秒 `ffprobe` 闸门保留**，量不到时长照样判失败。
- 删除说明性日志横幅：`QQ 音源已下线：搜歌与取歌只走网易云官方接口`、
  `网易云取歌首选本地服务: …`、`没配置 netease_api_base，网易云取歌只走官方接口 + 外链方式`、
  `音乐源 xxx 已下线（QQ 音源下线），按网易云处理/搜索`；`default_api` 那条警告改成只说事实。
  正常 `[取歌] …` 日志与错误日志全部保留。

### 配置

- 新增 `netease_meting_base`（默认 `https://api.qijieya.cn/meting/`）：取直链主路，不需要密钥。
- 新增 `netease_api_token`：备用 NodeJS 服务需要鉴权时填写（`Authorization: Bearer …`）。
- `netease_api_base` 默认值改为点歌插件用的 `https://zm.wwoyun.cn`（线上仍是本机 `3003`，不受影响）。
- `netease_cookie`、`netease_quality` 等原有配置项名称与作用保持不变；`netease_cookie` 的说明
  改成"备用路用"，因为主路 meting 不吃 cookie。

### 验证

- `py_compile` 通过：`main.py`、`netease_fetch.py`。
- 真实下载「失眠飞行」（网易云 id `1365898499`）：走主路 meting，文件 8,289,219 字节，
  `ffprobe` 时长 **207.157 秒**；按歌名搜索也能命中同一 id 并下到同一首歌。
- 不存在的 id（`999999999`）两条路都返回"没拿到链接"，不落垃圾文件。
- 未重启 AstrBot（由用户重启）。

## v0.4.3（2026-10-27）

新增「点歌 / 翻唱」需求判定闸门，翻唱插件不再接点歌的活。

### 新增

- **`intent_gate.py`**：判定逻辑和词表集中在这里（`TICKET_WORDS_MUSIC` / `TICKET_WORDS_COVER`）。
  消息里出现点歌类词（点歌、放歌、听歌、来一首、放一首、播一首，以及「放首歌」这类省略写法），
  且**不包含**翻唱类词（唱、翻唱、翻唱成、变声、cover、用…唱）→ 判定为点歌需求。
- 闸门接在每个翻唱入口：`smart_cover`、`rvc_cover`、`svc_cover`、`svcvc_cover`、`batch_cover`、
  `cover_absolute_path_audio`、`cover_local_audio`，以及本地音频自动触发 `on_message_with_audio`。
  命中后只把「这是点歌需求」这句事实作为工具结果回给模型（并建议用「点歌 歌名」或点歌插件的
  `play_song_by_name`），不注册任务、不执行翻唱。

### 变更

- `local_audio_trigger_keywords` 默认值收窄为 `["翻唱", "变声"]`，去掉「转换」「处理」「修音」这类泛词。
- `local_audio_auto_trigger` 的 schema 默认值改为 `false`（代码里本来就是 `False`，之前 schema 写的是
  `true`，新装默认就会主动抢带音频的消息）。线上配置同步改成关闭 + 两个触发词。

### 修复

- 「嗯。点歌。失眠飞行。」这类不按命令格式发的点歌，不再被模型顺手调用 `smart_cover` 变成翻唱。
- 「点歌 晴天」即使命令没命中、落到模型手里，翻唱工具也会拒绝执行。

### 其它

- 同步线上已有的 `_pick_best_song`（搜歌时只接受歌名/歌手能对上的结果，宁可不选也不选错）：
  此前只改了线上文件，这次一并纳入仓库，保证两边 SHA256 一致。

### 验证

- `py_compile` 通过：`main.py`、`intent_gate.py`、点歌插件 `main.py`（只编译到 `_scratch`，没往点歌插件目录写文件）。
- 假 event 判定 7 条全过：点歌 晴天→拒绝、嗯。点歌。失眠飞行。→拒绝、唱晴天→允许、
  翻唱一下晴天→允许、用三月七唱晴天→允许、给我放首歌→拒绝、变声→允许。
- 线上与仓库文件 SHA256 对齐；未重启 AstrBot（由用户重启）。

## v0.4.2（2026-10-27）

### 修复
- smart_cover / rvc_cover 的工具描述里明确写清使用边界：只在用户要「唱 / 翻唱 / 变声」时调用，
  用户说「点歌 / 放首歌 / 听」是放原曲，不要用翻唱工具；拿不准时先反问。
  起因：命令插件热重载的空窗期，一条「点歌 晴天」落到模型手里，被误判成翻唱。

## v0.4.1（2026-10-27）

### 修复
- 本地网易云取歌服务没启动时，失败原因现在带上服务地址，日志里直接给出可执行提示（跑 netease-api\start.ps1 或用一键启动脚本），不用再翻半天日志才知道是服务没起。
- 配套：一键启动脚本 D:\QQBOT\启动\start.ps1 把该服务加进自启（端口 3003），-Status/-Stop 也一起纳管。

## v0.4.0（2026-10-27）

新增"本地 NeteaseCloudMusicApi 服务"取歌路径：能下会员歌，官方接口取不到时不再
只剩失败一条路。

### 背景

官方 `api/song/enhance/player/url` 能返回链接，但直连 CDN 一律 403；`outer/url`
对 `fee=1` 的会员歌只返回 HTML。实测两首失败样本：`657666`（残酷な天使のテーゼ）、
`536622304`（Lemon）；成功样本 `2652820720`（晴天）。

### 新增

- **`netease.py`**：新增 `download_by_api_service(song_id, cookie, base_url, quality_br,
  dest_dir, timeout)` —— 调本地服务的 `/song/url/v1` 换带时间签名的 CDN 直链再下载，
  判定沿用同一套整首闸门（`code=200`、`url` 非空、`freeTrialInfo` 为 null、
  `time >= 80000`），下载完再用 `ffprobe` 量真实时长，不足 80 秒删文件判失败。
- 配套小函数：`api_service_level()`（320000→`exhigh`、192000→`higher`、128000→`standard`）、
  `normalize_api_base()`（补 `http://`、去尾部斜杠）。
- 新增失败原因：`REASON_API_BASE`（没配置地址）、`REASON_API_UNREACHABLE`（服务连不上）。
- **`main.py`**：读取 `netease_api_base`；`_fetch_netease_audio()` 改成两条路——先本地服务，
  失败再回落原来的官方接口 + 外链方式；两条都失败才记一次 cookie 相关失败。
- **`_conf_schema.json`**：新增 `netease_api_base`（`string`，默认 `http://127.0.0.1:3000`，中文说明）。

### 实测（本地服务 `127.0.0.1:3003`）

| 歌曲 id | 接口 | 状态 | 时长 |
| --- | --- | --- | --- |
| 657666 残酷な天使のテーゼ | `/song/url/v1?level=exhigh` | 200 / 320k / 9.38MB | 245.9 秒 |
| 536622304 Lemon | 同上 | 200 / 320k / 9.77MB | 256.0 秒 |
| 2652820720 晴天 | 同上 | 200 / 320k / 10.65MB | 279.0 秒 |

### 部署提醒

- 端口 `3000`、`3001` 已被本机 SnowLuma 占用，实际服务起在 `3003`；线上插件配置里
  `netease_api_base` 填的是 `http://127.0.0.1:3003`，schema 默认值仍是 3000。
- 服务用 `D:\PYMSS-RVC\netease-api\start.ps1` 后台常驻，日志在 `netease-api\logs\server.log`。

### 版本

- `metadata.yaml`、`main.py` 的 `@register` 版本号升到 `0.4.0`，README 配置表与更新日志同步。

## v0.3.1（2026-10-27）

新增 RVC 默认音色下拉配置 `rvc_default_model`，不用再靠序号记音色。

### 新增

- **`_conf_schema.json`**：新增 `rvc_default_model`（`string`，下拉），`options` 固定为 `Yuuka.pth`、`ainuo.pth`、`guanguanV1.pth`、`keruanV1.pth`、`kikiV1.pth`、`youzhanv2-xi.pth`、`三月七.pth`、`穹.pth` 共 8 个文件名；`default` 为空串，表示不指定、沿用序号逻辑。
- **`main.py`**：读取 `self.rvc_default_model`；新增 `_configured_rvc_model_index()`，按文件名 / 去扩展名 / 别名做精确匹配，把下拉值换成当前模型列表里的序号。
- 生效位置：`smart_cover`、`batch_cover`、`cover_local_audio` / `cover_absolute_path_audio` 以及本地音频执行入口，只在用户没有显式给出模型名或序号时套用。

### 优先级

- 用户显式指定的模型名/序号 > `rvc_default_model` > 用户偏好 / `default_model_index`。
- 仅对 RVC 生效；下拉选的模型不在当前列表里（没 `/刷新rvc模型`、模型被删）时回落到原来的序号逻辑，并记一条 `logger.warning`。
- 命令与 LLM 工具里已经显式指定模型的分支未改动。

### 版本

- `metadata.yaml` 与 `main.py` 的 `@register` 版本号升到 `0.3.1`，README 配置表与更新日志同步。

### 验证

- `py_compile main.py` 通过；`_conf_schema.json` 可被 `json.loads` 解析，新项存在；临时脚本确认 `options` 为 8 个、顺序与要求一致、`default` 为空串，跑完已删除。
- 已同步改动的 `.py` / `.json` / `.md` / `.yaml` 到线上插件副本，逐文件 SHA256 对齐；未重启 AstrBot。

## v0.3.0（2026-10-27）

彻底移除洛雪（LX-Source），音源只剩网易云官方接口 + cookie；QQ 音源下线。

### 移除

- **`netease.py`**：删除 `download_via_lx()`、`build_lx_url()`、`probe_duration_ms()` 以及全部 `REASON_LX_*` 常量与 lx 相关辅助函数；文件只剩官方接口判定 + 外链下载这一条路，`download_by_id()` 核心逻辑未改。
- **`main.py`**：删除 `_fetch_lx_audio()`、`_fetch_qq_audio()`、`_handle_qq_cover()` 与 `/qqrvc`、`/qqsvc`、`/qqsvcvc`、`/qq点歌` 四个 QQ 入口；`_fetch_netease_audio()` 去掉全部洛雪兜底，取不到整首直接失败。
- **`_conf_schema.json`**：删除洛雪地址、洛雪认证头、洛雪兜底开关三项配置；`api.py` 里已废弃的第三方音源短路注释一并清掉。

### 变更为只用网易云

- `disable_qqmusic` 默认改为 `true` 并在代码里固定为 `True`（描述写明“已锁死只用网易云”）；`_resolve_music_source()` 无论调用方或配置怎么写，最终一律返回网易云。
- `_prepare_song_audio()`：纯数字 → 网易云 id；旧的 QQ mid → 不再碰 QQ，直接按歌名去网易云搜，搜不到就失败；其它字符串 → 按歌名搜网易云；全部只过官方接口。
- `_do_cover()` 与 `search_music()` 删掉 QQ 搜索分支与风控重试，网易云搜索失败直接给失败原因。
- `default_api=qqmusic` 或未知值一律回落网易云官方接口并记 warning；`disable_netease` 保留读取但按网易云继续（只记 warning）。

### 版本

- 版本号 0.3.0；`metadata.yaml`、`README.md`、`NOTICE.md` 同步更新；`requirements.txt` 去掉已不再使用的 `qqmusic-api-python`。

### 验证

- 六个 Python 文件 `py_compile` 全过；`_conf_schema.json` JSON 解析通过；全目录 grep 确认无洛雪配置键、旧端口、失效域名残留。

## v0.2.2（2026-10-27）

修网易云整首下载 403：官方接口只用来判定，下载改走外链跳转入口。

### 修复

- **`download_by_id` 不再用接口返回的 `data[0].url` 下载**（该 CDN 直链实测 403 Forbidden），判定通过后固定改走外链跳转入口 `https://music.163.com/song/media/outer/url?id=<id>.mp3`，请求头同样带 `Cookie: MUSIC_U` / `Referer` / `User-Agent`，`urllib` 默认跟随 302。接口判定逻辑（HTTP 200、`code == 200`、`url` 非空、`freeTrialInfo is null`、`time >= 80000`）原样保留；判定失败（如只给试听）仍直接返回，不再退回外链碰运气。
- **下载后再用 `ffprobe` 量一次真实时长**：不足 80000ms 就删文件并返回失败原因“下载到的不是整首（时长 xx 秒）”，量不到时长按“下载完量不到时长，无法确认是整首”失败（宁可不出歌，也不把片段交出去）。
- **下载失败原因带 HTTP 状态**：`REASON_HTTP_DOWNLOAD`（“下载地址返回 HTTP xxx”）在直链返回 403/404 等时原样透出，方便定位。

### 变化

- 下载请求头抽成 `MEDIA_USER_AGENT` / `MEDIA_REFERER` + `_media_headers(cookie)`，与接口那套 `DEFAULT_USER_AGENT` / `OFFICIAL_REFERER` / `_api_headers(cookie)` 分开维护，改一边不影响另一边；`_download_file` 改为接收 `headers` 字典。

### 验证

- `netease.py`、`main.py` 的 `py_compile` 通过（Python 3.12）。
- 用线上配置里的 `netease_cookie` 真实跑了一次 `download_by_id('2652820720', cookie)`：落盘 4,464,684 字节（约 4.4MB），`ffprobe` 时长 278,962ms（约 279 秒），`reason` 为空、`is_trial=False`；跳转落在 `m701.music.126.net`，`Content-Type: audio/mpeg`，是整首 128k。
- 已同步 `netease.py` / `main.py` / `metadata.yaml` / `README.md` / `CHANGELOG.md` 到线上插件副本，逐文件 SHA256 对齐；未重启服务。

## v0.2.1（2026-10-27）

把"取歌"这条链收成一个入口：卡片选歌、命令点歌、LLM 工具、批量翻唱都只走 `_prepare_song_audio`，id / QQ mid 不再有任何一条路能原样递给中间层。

### 新增

- **统一取歌入口 `_prepare_song_audio(event, song) -> (本地路径|None, 失败原因, 是否试听)`**，判定顺序：
  1. 已经是存在的本地文件 → 直接返回；
  2. 纯数字 → 网易云 id（官方接口优先，失败再洛雪 `/link/wy/<id>/<音质>`，都过 80 秒闸门）；
  3. `^[0-9A-Za-z]{11,14}$` 且含字母 → QQ mid：洛雪 `/link/tx/<mid>/128k`（下完 `ffprobe` 量时长，< 80000ms 判试听失败）→ QQ 官方库 → 按歌名回网易云搜索，再回到第 2 条；
     （规格里写的是 11~12 位，但实测线上报错的两个 mid `0039MnYb0qxYhV`、`003YYGKC1DTKmZ` 都是 14 位，所以按 11~14 位认，否则这两个 id 会漏进"按歌名搜索"。）
  4. 其它 → 当歌名：网易云搜索第一条的 id 回到第 2 条，搜不到再洛雪 `/link/wy/<歌名>` 试一次。
  每一步失败的原因按顺序串成一句中文，技术细节只写 logger。
- 配置项 `disable_qqmusic`（bool，默认 `false`）：开启后搜歌阶段只走网易云，不再拿回 QQ mid；`/qqrvc` 等 QQ 入口会提示改用网易云命令。两个搜索源同时禁用时按网易云处理并记 warning。
- `netease.py` 新增公开的 `probe_duration_ms(path)`，供插件给 QQ 直链 / 本地文件做 80 秒闸门。

### 变化

- **批量翻唱不再把 id 交给中间层**：`_do_cover`（LLM 工具 / 批量走这条）和 `_send_song`（卡片 / 命令选歌走这条）都改成调统一入口，先拿到本地音频文件再提交；`song_input_for_api = str(selected_song["id"])` 这类写法已全部删除（grep 确认无残留）。
- **修掉"网易云搜不到这首歌：<QQ mid>"的根因**：`default_api=qqmusic` 时 `self.api` 是 QQ 搜索器，而网易云分支直接复用它，拿到的 id 其实是 mid。现在网易云这条路固定用"确定是网易云"的搜索器（`_netease_search_api`），`self.api` 是 QQ 时临时新建 `NetEaseMusicAPI`。
- **洛雪兜底支持多源**：洛雪下载函数不再强制纯数字 id（`tx` 传 mid、`wy` 可传歌名），落盘文件名做了安全化处理；按歌名兜底时 URL 路径段做百分号编码（中文直接拼进 URL 会让 `urllib` 抛 `UnicodeEncodeError`）。
- **批量报告只说人话**：每条失败改成"这首拿不到音源 / 生成超时了 / 这个引擎被禁用了"这类短句，中间层原始报错、重试次数等技术细节只进日志；批量整体异常的报告也收敛成一句。
- `_fetch_netease_audio` 返回值补上"是否试听"，供统一入口串失败原因。

### 验证

- 六个 Python 文件 `py_compile` 全通过。
- 临时自检脚本（假对象 / monkeypatch，不真下歌）覆盖：本地文件直通、纯数字走网易云、QQ mid 走洛雪失败后回落到按名搜索、歌名搜索不到、`disable_qqmusic=true` 时搜歌不调 QQ，全部通过；脚本跑完已删除。
- 已同步到线上插件目录，逐文件 SHA256 对齐；未重启服务。

## v0.2.0（2026-10-27）

网易云点歌改走**官方取直链接口 + MUSIC_U cookie**，洛雪源只当兜底；两条路都按"整首"标准过滤试听片段，cookie 连续失效会提醒管理员。

### 新增

- 新增 `netease.py`（纯标准库，不新增第三方依赖）：
  - `download_by_id(song_id, cookie, quality_br=320000, dest_dir, timeout=120) -> (路径|None, 失败原因, 是否试听)`：调官方接口 `GET https://music.163.com/api/song/enhance/player/url?ids=[<id>]&br=<码率>`，带 `Cookie: MUSIC_U=...`、`Referer: https://music.163.com`、`User-Agent: Mozilla/5.0`；成功就流式下载到本地，单文件上限 60MB。
  - 洛雪源兜底函数：向本机洛雪服务要直链，带认证头，下完再量时长。
  - `judge_result(...)` / `is_cookie_failure(...)`：把"整首"判定和"这次算不算 cookie 问题"抽成纯函数，方便单测。
- 配置项 7 个：`netease_cookie`、`netease_quality`、洛雪地址、洛雪认证头、洛雪兜底开关、`alert_admin_on_cookie_expired`、`cookie_alert_interval_hours`。
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
- **移除失效的备选音源接口**：该域名已无法解析（2026-10-27 实测 `getaddrinfo failed`），分支删除并短路返回，不再让每次重试白等一次 15 秒网络超时。

### 验证

- 五个 Python 文件 `py_compile` 全通过。
- 全目录检索确认已无 `遇到风控，正在自动重试`、`正在从【` 这类硬编码文案，统一出口接线 17 处。
- `outbound.py` 在 AstrBot 运行环境（uv 工具虚拟环境 python 3.12）跑行为测试 9 项全过：进度/重试默认静音、失败走模型、模型不可用退回兜底、`event.send` 抛异常被吞、开关打开后进度可发、未知类型静音。
- 线上加载验证：AstrBot 重启后日志显示 `Plugin astrbot_plugin_chorus_cover (v0.1.0) by void-HaoNan`、`Added llm tool: smart_cover`、平台钩子正常，无异常堆栈；配置从上游插件迁入后 `rvc_base_url`、8 个模型、两个新开关均正确。
- 未覆盖：`main.py` 17 处接线的运行时行为（需要真实点一首歌才能验证）。

### 说明

- 本分支**不再跟随上游更新**，需要上游新功能请直接使用上游仓库版本。
- `LICENSE` 保持上游原样（AGPL-3.0），修改声明见 `NOTICE.md`。
