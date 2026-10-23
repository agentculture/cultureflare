"""Back-compat alias: ``_shushu_sink`` is ``_grant_sink`` (shushu became grant).

Replaces this module in ``sys.modules`` so both names are the *same*
object and monkeypatching either one patches the other.
"""

import sys

from cultureflare._secrets import _grant_sink

sys.modules[__name__] = _grant_sink
