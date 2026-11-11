"""PinnRadar: real-time Pinnacle odds API client. https://pinnradar.com/docs"""

__version__ = "0.1.1"

from .client import AuthError, Client, PinnRadarError, RateLimitError, parse_sse  # noqa: E402
from .odds import implied, margin, no_vig  # noqa: E402

__all__ = [
    "Client",
    "PinnRadarError",
    "AuthError",
    "RateLimitError",
    "parse_sse",
    "implied",
    "margin",
    "no_vig",
    "__version__",
]
