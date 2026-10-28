"""测试用的最小环境：不装 AstrBot 也能 import 插件里的纯逻辑模块。"""

import logging
import sys
import types

if "astrbot" not in sys.modules:
    astrbot = types.ModuleType("astrbot")
    api = types.ModuleType("astrbot.api")
    api.logger = logging.getLogger("chorus-cover-test")
    astrbot.api = api
    sys.modules["astrbot"] = astrbot
    sys.modules["astrbot.api"] = api
