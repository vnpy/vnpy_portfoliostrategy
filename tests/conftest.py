import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT: Path = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# vnpy.trader.utility 导入时按当前目录决定 .vntrader 位置，必须先切到临时目录，避免读写用户真实配置。
# vnpy.trader.logger 在导入时读取 log.file 和 log.console，必须在第一次 import vnpy 之前写好。
ORIGINAL_CWD: str = os.getcwd()
TRADER_TEMP_DIR: tempfile.TemporaryDirectory = tempfile.TemporaryDirectory()
TRADER_DIR: Path = Path(TRADER_TEMP_DIR.name).joinpath(".vntrader")
TRADER_DIR.mkdir()
TRADER_DIR.joinpath("vt_setting.json").write_text(
    json.dumps({"log.file": False, "log.console": False}),
    encoding="UTF-8",
)
os.chdir(TRADER_TEMP_DIR.name)


def pytest_unconfigure(config: pytest.Config) -> None:
    os.chdir(ORIGINAL_CWD)
    TRADER_TEMP_DIR.cleanup()
