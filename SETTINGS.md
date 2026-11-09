# 设置项清单与生效位置

这份表由脚本从 `_conf_schema.json` 和源码生成：每一项都能在源码里找到读取它的位置。
改设置前先看最后一列，定位到具体文件与行。

| 设置项 | 说明 | 读取位置 |
|---|---|---|
| `rvc_base_url` | RVC API Gradio 后端服务地址 | main.py:153 |
| `auto_middleware` | 随 AstrBot 启停并托管中间层（接管旧实例，退出时关闭） | main.py:301 |
| `chorus_dir` | 中间层目录（留空自动找：CHORUS_DIR / RVC 整合包旁） | main.py:302 |
| `rvc_root` | RVC 整合包目录（中间层启动必须；留空从模型目录倒推） | main.py:303 |
| `chorus_python` | 跑中间层的 Python（留空由 start.ps1 从 PATH 找） | main.py:304 |
| `netease_cookie` | 网易云 MUSIC_U（备用取歌路径用） | main.py:174 |
| `netease_quality` | 网易云取歌音质（kbps） | main.py:176 |
| `netease_meting_base` | meting 取直链服务地址（主路） | main.py:185 |
| `netease_api_base` | NodeJS 网易云 API 地址（备用路） | main.py:191 |
| `netease_api_token` | NodeJS 网易云 API 访问令牌（可选） | main.py:200 |
| `source_order` | 取歌音源顺序（同时决定启停） | main.py:207 |
| `alert_admin_on_cookie_expired` | 网易云 cookie 连续失效时提醒管理员 | main.py:235 |
| `cookie_alert_interval_hours` | cookie 失效提醒最小间隔（小时） | main.py:239 |
| `qq_official_cards` | 自动识别 QQ 官方机器人并使用 Markdown 卡片 | main.py:159 |
| `qq_official_buttons` | 自动识别 QQ 官方机器人并启用交互按钮 | main.py:157 |
| `timeout` | 等待用户选择的超时时间（秒） | main.py:155 |
| `inference_timeout` | AI推理超时时间（秒） | main.py:170 |
| `enable_rvc` | 启用RVC推理引擎 | main.py:168 |
| `rvc_models_keywords` | RVC 模型别名配置 | main.py:162 |
| `rvc_models_dir` | RVC 音色模型文件夹 | main.py:164 |
| `model_library_dir` | 分类音色库目录（可选） | main.py:166 |
| `llm_force_mode` | LLM强制模式 - 禁用所有手动命令 | main.py:248 |
| `enable_smart_cover` | 启用方案A：智能单步翻唱（smart_cover） | main.py:249 |
| `enable_enhanced_context` | 启用方案B：增强上下文记忆 | main.py:250 |
| `persona_song_pick_enable` | 按人格自动选歌 | main.py:252 |
| `persona_song_pick_hint` | 额外选歌偏好 | main.py:253 |
| `persona_song_pick_avoid_count` | 最近唱过的不重复数量 | main.py:256 |
| `enable_confirm_mechanism` | 启用方案C：确认机制 | main.py:260 |
| `enable_batch_cover` | 启用方案D：批量翻唱 | main.py:261 |
| `enable_preference_learning` | 启用方案E：偏好学习与推荐 | main.py:262 |
| `rvc_default_model` | 选择音色模型（RVC 默认音色） | main.py:276 |
| `language_model_enable` | 按歌曲语言自动选音色 | main.py:278 |
| `language_model_zh` | 中文歌用的音色 | main.py:280 |
| `language_model_ja` | 日语歌用的音色 | main.py:281 |
| `language_model_en` | 英文歌用的音色 | main.py:282 |
| `default_key_shift` | 默认音调调整 | main.py:284 |
| `max_batch_size` | 批量翻唱最大数量 | main.py:333 |
| `preference_storage_path` | 偏好数据存储路径 | main.py:337 |
| `enable_llm_success_notify` | 处理完成后通知大语言模型 (LLM) | main.py:264 |
| `notify_progress` | 发送翻唱进度提示 | outbound.py:33 |
| `notify_retry` | 发送风控自动重试提示 | outbound.py:34 |
| `f0_method` | RVC音高提取算法（F0方法） | main.py:285 |
| `index_rate` | RVC特征检索比率（Index Rate） | main.py:286 |
| `rms_mix_rate` | 人声音量起伏贴合原唱的程度（rms_mix_rate） | main.py:290 |
| `protect` | 保护清音与气声的程度（protect） | main.py:291 |
| `inst_volume_db` | 伴奏音量（dB） | main.py:292 |
| `vocal_only` | 清唱模式：只出变声后人声，不混伴奏 | main.py:296 |
| `vocal_volume_db` | 人声音量（dB） | main.py:293 |
| `enable_send_file` | 推理完成后同时以文件形式发送到群聊 | main.py:265 |
| `enable_config_report` | 翻唱完成后发送配置信息报告 | main.py:266 |
| `enable_auto_key_shift` | 启用自动升降调（根据原曲歌手与模型性别自动调整音调） | main.py:351 |
| `enable_auto_key_shift_debug` | 自动升降调调试信息输出到群聊 | main.py:352 |
| `gender_detection_timeout` | 自动升降调性别识别超时（秒） | main.py:354 |
| `music_api_timeout` | 音乐搜索接口超时（秒） | main.py:171 |
| `male_to_female_shift` | 男→女 升调值（半音数） | main.py:356 |
| `female_to_male_shift` | 女→男 降调值（半音数） | main.py:357 |
| `artist_gender_map` | 歌手性别映射表 | main.py:358 |
| `model_gender_map` | 模型性别映射表 | main.py:359 |
| `shift_accompaniment` | 升降调时同时调整伴奏音高 | main.py:294 |
| `render_mode` | 翻唱时长模式（唱多长） | main.py:309 |
| `chorus_seconds` | 翻唱时长（秒） | main.py:315 |
| `chorus_start_seconds` | 指定副歌起点（秒，0=自动） | main.py:322 |
| `enable_inject_context` | 将翻唱任务状态注入LLM上下文记忆 | main.py:269 |
| `enable_task_tracking` | 启用翻唱任务状态追踪 | main.py:270 |
| `task_timeout_seconds` | 翻唱任务超时时间（秒） | main.py:271 |
| `enable_local_audio_cover` | 启用本地音频文件翻唱 | main.py:376 |
| `max_local_audio_size_mb` | 本地音频文件最大大小限制（MB） | main.py:375 |
| `local_audio_cache_ttl` | 本地音频缓存有效期（秒） | main.py:374 |
| `local_audio_trigger_keywords` | 本地音频自动触发关键词 | main.py:381 |
| `local_audio_auto_trigger` | 开启本地音频自动触发 | main.py:377 |
| `local_audio_default_model` | 本地音频自动触发默认模型 | main.py:383 |
| `local_audio_default_shift` | 本地音频自动触发默认音调 | main.py:384 |

共 72 项。
