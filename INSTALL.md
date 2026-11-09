# 安装与自检（小白版）

这个插件不打包引擎，它需要你本机有一套 RVC 整合包和配套的中间层 `chorus-mw`。
下面两种装法选一种，**不要两种都做**。

## 🚀 最省事：把这段发给 DSH / AI 工具

复制下面整段，发给 DSH（DeepSeek Harness）或 Claude Code / Cursor / Codex 这类能执行命令的 AI：

```text
帮我安装并配置 astrbot_plugin_chorus_cover（RVC 翻唱插件）：
插件仓库 https://github.com/void-HaoNan/astrbot-plugin-chorus-cover
中间层仓库 https://github.com/void-HaoNan/chorus-mw

要求：
1. 先读插件仓库的 INSTALL_AGENT.md，按里面的检查项一步步做，每一步把结果告诉我。
2. 中间层 3333 由插件自己启动和关闭，不要用 start_supervisor.ps1，也不要单独开守护窗口。
3. 装完重启 AstrBot，等 3333 就绪，在群里发 /环境自检，把结果贴给我；再关一次 AstrBot 确认没有残留进程。
```

它读完 `INSTALL_AGENT.md` 会按顺序检查：AstrBot 版本 → 插件目录 → 中间层目录 → RVC 整合包 → Python 3.10~3.12 → 依赖 → 执行策略 → 启动 → `/环境自检` → 停一次确认无残留。

**装完应该看到什么**（先记住，省得以为没装好）：

- 重启 AstrBot 后 10~40 秒，`http://127.0.0.1:3333` 自动就绪，**不需要你开任何黑色窗口**；
- 关掉 AstrBot，3333、常驻 worker、以及中间层自己拉起的 RVC WebUI 一起退出；
- 群里 `/环境自检` 显示「中间层由本插件托管」。

## 🖱 不想用 AI：双击安装器

进插件目录 → `scripts` → 双击 `install.bat`。窗口会依次问/找这几样，照提示走：

1. AstrBot 数据目录（一般自动找到 `用户目录\data`）
2. RVC 整合包目录（里面有 `runtime` 和 `assets`）
3. 中间层 chorus-mw（没有会自动从 GitHub 下载；下不动就手动解压到它问的目录）
4. Python 3.10~3.12（没有会打开官网）
5. rubberband（升降调用，自动下）
6. 把后端地址、中间层目录、RVC 目录、Python 路径写进插件配置
7. 试启动一次中间层确认能起来，然后停掉，交还给插件

最后**重启 AstrBot**，等 3333 就绪，在群里发 `/环境自检`（管理员）。

> 安装器不会改系统 PATH、不会装驱动、不会静默执行网上的脚本；下载地址只有 GitHub 和 breakfastquay 官方。

## ⚠️ 用户安装时最常卡住的 13 件事

我们开发机上装过很多遍，下面这些是**别的机器上真实会碰到、我们本机不一定复现**的：

| # | 现象 | 原因 | 怎么办 |
|---|---|---|---|
| 1 | PowerShell 报「无法加载文件 … 因为在此系统上禁止运行脚本」 | 执行策略是 Restricted | `install.bat` 已带 `-ExecutionPolicy Bypass`；手动跑也加这个参数，或 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 2 | 双击 `install.bat` 闪一下就没了 | 报错被窗口带走 | 在 `scripts` 目录地址栏输入 `powershell` 回车，再跑 `.\installer.ps1`，红字就是原因 |
| 3 | 中间层起不来，`_work\mw.log` 里 `ModuleNotFoundError` | 依赖装在另一个 Python 上 | 设置里「跑中间层的 Python」指到装过依赖的那个 3.10~3.12；或重跑安装器 |
| 4 | `pip install` 一堆红字 / torch 装不上 | 用了 Python 3.13 | RVC 依赖只到 3.12：装 3.10~3.12，或设置里指定 |
| 5 | 「找不到 python」/ 解析到 Windows 商店 | PATH 里是 `WindowsApps` 的假 python | 装 python.org 版本并勾 Add to PATH；或设置里指定完整 `python.exe` |
| 6 | 路径里有中文、空格、OneDrive | 老脚本拼命令没加引号 / 同步目录锁文件 | 装到短路径（如 `D:\RVC`），别放 OneDrive 同步目录 |
| 7 | 重启 AstrBot 后 3333 一直不通，机器却不卡 | 冷启动要 import torch，10~40 秒正常 | 等 `/环境自检`；超过 90 秒再看 `_work\mw.log` |
| 8 | 关掉 AstrBot 后 3333 还在 | 中间层是旧守护/控制台拉起的（外部实例） | 关掉 `start_supervisor.ps1` 或控制台的守护；重启 AstrBot 让插件接管 |
| 9 | 两个窗口抢 3333，日志一直「已在监听」 | 有两份管理者 | 只留插件：`start.ps1 -Status` 看旧守护 pid，`start.ps1 -Stop` 一起收 |
| 10 | GitHub 下载失败 | 网络到不了 codeload | 手动下 chorus-mw 的 zip 解压到 RVC 旁边，或设置「中间层目录」 |
| 11 | 中间层报 `When localhost is not accessible` | 系统代理把 127.0.0.1 也代理了 | `start.ps1` 已设 `NO_PROXY`；自己另起 Gradio 也要设 |
| 12 | AstrBot 装在 pipx/uv，找不到 `data` 目录 | 数据目录不一定是 `C:\Users\<你>\data` | 用 `ASTRBOT_DATA_DIR`，或安装器问的时候手动填 |
| 13 | 杀毒软件拦 `taskkill` / `.ps1` | 启发式拦截 | 给插件目录和中间层目录加信任；看 `_work\supervisor.log` 有没有「拒绝访问」 |

## 安装前先确认这五件事（缺一个就跑不起来）

1. **中间层 3333 由插件托管**：正常不用你开；`auto_middleware` 关掉或 Linux 部署时，必须自己保证 `http://127.0.0.1:3333` 有返回。
2. **RVC 整合包路径、音色模型目录**：装完在插件设置里填，路径里要能看到 `runtime`、`assets`。
3. **能访问外网取歌**：默认 meting 是 `https://api.qijieya.cn/meting/`，搜歌是 `https://music.163.com`。
   连不上就会报「取歌服务连不上」或「搜不到这首歌」——这一步最容易卡住，先用浏览器打开这两个地址确认能通。
4. **网易云 cookie（建议）**：不配能搜歌，但部分版权歌拿不到直链。
5. **AstrBot ≥ 4.16，且知道它的 data 目录**：插件在 `<data>\plugins\astrbot_plugin_chorus_cover`，
   配置在 `<data>\config\astrbot_plugin_chorus_cover_config.json`。

装完发 `/环境自检`，上面这些它会逐条检查并给结论。

## `/环境自检` 看什么

- 中间层能不能连上、有几个模型、**中间层归谁管**（插件托管 / 外部实例 / 另一个 AstrBot）
- RVC 运行时、ffmpeg、rubberband 在不在
- 中文/日语/英文三档音色有没有配、配的模型还在不在
- 默认音色是否还在列表里
- 取歌服务 3003 是否在线（可选，没有也能跑）

全绿就是能唱；有 ❌ 按提示修，一行一个动作，不猜。

## 装好之后的日常命令

- `/同步音色库`（管理员）：把分类库里的模型自动链接进 RVC 并刷新列表，先到设置里填「分类音色库目录」。
- `/重启中间层`（管理员）：中间层卡住或掉线时一条命令拉活，不用去命令行；重启后的实例也归插件管。
- `/刷新rvc模型`：只是重新读一遍模型列表，不动文件。
- `/环境自检`：装完、改完配置、出问题，先发这个。

## 只想看不想装

```
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\installer.ps1 -CheckOnly
```

只报告当前状态，不装依赖、不写配置、不启动服务。

## 常见问题

**双击 bat 闪一下就没了**
用资源管理器地址栏打开插件 `scripts` 目录，在地址栏输入 `powershell` 回车，再执行
`.\installer.ps1`，就能看到报错。

**GitHub 下载失败**
安装器带两个下载地址（`master` 和 `main`）。都不行就手动下
`void-HaoNan/chorus-mw` 的 zip，解压到安装器问你的目录，再重跑。

**3333 起不来**
去中间层目录看 `_work\mw.log`。最常见是 Python 依赖没装上、Python 版本不对，或 RVC 路径填错。
命令行排查：

```
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Status
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

**关掉 AstrBot 后中间层还在**
先看 `/环境自检` 里「中间层归谁管」那一行：

- 显示「外部实例」→ 是旧守护、旧控制台或者你手动开的。关掉那个守护，重启 AstrBot 让插件接管；
- 显示「插件托管」但 3333 还在 → 在中间层目录跑 `start.ps1 -Stop`，看输出里有没有「端口还被占着」；
  有的话说明还有另一个守护在拉起它，`start.ps1 -Status` 会列出旧守护 pid。

**RVC WebUI（7897）要不要自己开**
不用。中间层第一次翻唱时会自己拉起 7897，并随中间层一起结束；
如果你另外开着 7897，中间层会复用，不会重复起。

**音色模型放哪**
`<RVC>\assets\weights` 里的 `.pth` 和 `assets\indices` 里的 `.index`。
想按语言/角色分类存放，用 README 里「硬链接」那一节的办法，别直接把文件搬走。

**会不会被市场安全审核拦**
安装器不在市场插件里自动执行，它只是仓库里的一个脚本，由你自己双击。
市场里只有插件本体和 `/环境自检` 这条只读检查命令，不改系统、不下载执行。

## 卸载 / 换机

1. 群里先 `auto_middleware` 关掉（或直接停 AstrBot），确认 3333 已退出；
2. 删 `data\plugins\astrbot_plugin_chorus_cover`；
3. 中间层目录整份删掉即可，它不写注册表、不装服务；
4. `data\plugin_data\astrbot_plugin_chorus_cover` 里是偏好、统计和 `middleware.json`，不要可以一起删。
