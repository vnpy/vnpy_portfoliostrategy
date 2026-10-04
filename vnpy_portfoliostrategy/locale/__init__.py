"""加载组合策略的翻译文本。"""

from pathlib import Path
import gettext

localedir: Path = Path(__file__).parent
translations: gettext.NullTranslations = gettext.translation('vnpy_portfoliostrategy', localedir=localedir, fallback=True)

_ = translations.gettext
