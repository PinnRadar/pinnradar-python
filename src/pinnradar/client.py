"""HTTP client for the PinnRadar odds API. Standard library only."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, Iterator, List, Optional, Union

from . import __version__

DEFAULT_BASE_URL = "https://pinnradar.com"
Params = Dict[str, Any]


class PinnRadarError(Exception):
    """Any non-success answer from the API."""

    def __init__(self, message: str, status: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class AuthError(PinnRadarError):
    """401/403: the key is missing, wrong, expired, or the plan lacks this feature."""


class RateLimitError(PinnRadarError):
    """429: slow down. `retry_after` is the number of seconds the server asked for."""

    def __init__(self, message: str, retry_after: Optional[float], status: int = 429, body: Any = None):
        super().__init__(message, status, body)
        self.retry_after = retry_after


def _clean(params: Params) -> Params:
    out: Params = {}
    for k, v in params.items():
        if v is None:
            continue
        if isinstance(v, bool):
            v = int(v)
        elif isinstance(v, (list, tuple, set)):
            v = ",".join(str(x) for x in v)
        out[k] = v
    return out


def _csv(v: Union[None, str, Iterable[Any]]) -> Optional[str]:
    if v is None or isinstance(v, str):
        return v
    return ",".join(str(x) for x in v)


def parse_sse(lines: Iterable[str]) -> Iterator[str]:
    """Yield the `data` payload of each Server-Sent Event in an iterable of text lines."""
    data: List[str] = []
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line == "":
            if data:
                yield "\n".join(data)
                data = []
            continue
        if line.startswith(":"):
            continue  # comment / keep-alive
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data.append(value)
    if data:
        yield "\n".join(data)


class Client:
    """PinnRadar API client.

    >>> from pinnradar import Client
    >>> pr = Client("YOUR_KEY")            # or set PINNRADAR_API_KEY
    >>> board = pr.markets(sport_id=1)       # live soccer
    >>> for drop in pr.stream_drops(min_drop=5):
    ...     print(drop["home"], drop["sect"], drop["from_price"], "->", drop["to_price"])
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 20.0,
        user_agent: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("PINNRADAR_API_KEY") or os.environ.get("PINNRADAR_KEY")
        if not self.api_key:
            raise AuthError("No API key. Pass Client('...') or set PINNRADAR_API_KEY. Free keys: https://pinnradar.com/panel")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.user_agent = user_agent or f"pinnradar-python/{__version__}"

    # ------------------------------------------------------------------ core

    def _url(self, path: str, params: Optional[Params] = None) -> str:
        q = urllib.parse.urlencode(_clean(params or {}))
        return f"{self.base_url}{path}" + (f"?{q}" if q else "")

    def _request(self, path: str, params: Optional[Params] = None, auth: bool = True, stream: bool = False):
        headers = {"user-agent": self.user_agent, "accept": "text/event-stream" if stream else "application/json"}
        if auth:
            headers["x-api-key"] = self.api_key  # type: ignore[assignment]
        req = urllib.request.Request(self._url(path, params), headers=headers)
        try:
            return urllib.request.urlopen(req, timeout=None if stream else self.timeout)
        except urllib.error.HTTPError as e:
            raise self._error(e) from None
        except urllib.error.URLError as e:
            raise PinnRadarError(f"Connection failed: {e.reason}") from None

    @staticmethod
    def _error(e: urllib.error.HTTPError) -> PinnRadarError:
        raw = e.read().decode("utf-8", "replace")
        try:
            body: Any = json.loads(raw)
        except ValueError:
            body = raw
        detail = body.get("error") if isinstance(body, dict) else None
        msg = f"HTTP {e.code}" + (f": {detail}" if detail else "")
        if e.code == 429:
            ra = e.headers.get("retry-after")
            try:
                retry = float(ra) if ra is not None else None
            except ValueError:
                retry = None
            return RateLimitError(msg, retry, body=body)
        if e.code in (401, 403):
            return AuthError(msg, e.code, body)
        return PinnRadarError(msg, e.code, body)

    def get(self, path: str, **params: Any) -> Any:
        """Call any GET endpoint and return the decoded JSON."""
        with self._request(path, params) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------- endpoints

    def markets(
        self,
        sport_id: int,
        event_type: str = "live",
        since: Optional[int] = None,
        include_specials: Union[None, bool, str] = None,
    ) -> Dict[str, Any]:
        """Live board for one sport.

        For prematch, use `prematch_fixtures()` / `prematch_markets()`: this endpoint answers
        `event_type="prematch"` with 503 prematch_disabled.

        Pass the `last` value of the previous answer as `since` to receive only what changed.
        `include_specials=True` adds props, correct score and outrights ("nested" attaches them
        under their parent event).
        """
        inc = 1 if include_specials is True else (include_specials or None)
        return self.get("/kit/v1/markets", sport_id=sport_id, event_type=event_type, since=since, include_specials=inc)

    def details(self, event_id: int) -> Dict[str, Any]:
        """Every market of one live event."""
        return self.get("/kit/v1/details", event_id=event_id)

    def prematch_fixtures(self, sport_id: int, since: Optional[int] = None) -> Dict[str, Any]:
        """Upcoming fixtures of one sport with their main prices."""
        return self.get("/kit/v1/prematch/fixtures", sport_id=sport_id, since=since)

    def prematch_markets(self, event_id: int) -> Dict[str, Any]:
        """Complete market set of one prematch event."""
        return self.get("/kit/v1/prematch/markets", event_id=event_id)

    def prematch_lines(self, event_id: int, market_type: Optional[str] = None) -> Dict[str, Any]:
        """Lines of one prematch event; `market_type` is money_line, spreads, totals or team_total."""
        return self.get("/kit/v1/prematch/lines", event_id=event_id, market_type=market_type)

    def drops(
        self,
        max_age_sec: int = 600,
        mode: str = "live",
        min_drop_pct: Optional[float] = None,
        max_drop_pct: Optional[float] = None,
        sport_id: Optional[int] = None,
        markets: Union[None, str, Iterable[str]] = None,
        periods: Union[None, str, Iterable[int]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Recent price drops from the server-side buffer (about 3 hours deep).

        Returns the list of drop rows (`event_id`, `home`, `away`, `market`, `side`, `from`, `to`,
        `nvp`, `drop_pct`, ...).
        """
        page = self.get(
            "/api/drops",
            mode=mode,
            max_age_sec=max_age_sec,
            min_drop_pct=min_drop_pct,
            max_drop_pct=max_drop_pct,
            sport_id=sport_id,
            markets=_csv(markets),
            periods=_csv(periods),
            limit=limit,
        )
        return page.get("drops", []) if isinstance(page, dict) else page

    def ping(self) -> bool:
        """True when the API answers. Needs no key."""
        try:
            with self._request("/ping", auth=False) as resp:
                return resp.status == 200
        except PinnRadarError:
            return False

    # -------------------------------------------------------------- streams

    def stream_drops(
        self,
        prematch: bool = False,
        min_drop: Optional[float] = None,
        recheck: Optional[int] = None,
        reconnect: bool = True,
        max_backoff: float = 30.0,
    ) -> Iterator[Dict[str, Any]]:
        """Follow the live (or prematch) drop alerts over Server-Sent Events.

        Yields one dict per drop as soon as the detector flags it: `home`, `away`, `league`,
        `sport`, `sect` (Moneyline, Spread, Total, TeamTotal), `outcome`, `point`, `period`,
        `from_price`, `to_price`, `nvp` (no-vig price), `limit` and, in play, `live` (score,
        clock, cards, corners). Reconnects with backoff
        when the connection drops (set `reconnect=False` to stop instead). Needs a plan with
        SSE (Drops, Edge or Scale). Only one stream of each kind per key at a time.
        """
        path = "/odds-drop-prematch" if prematch else "/odds-drop"
        backoff = 1.0
        while True:
            try:
                with self._request(path, {"min_drop": min_drop, "recheck": recheck}, stream=True) as resp:
                    backoff = 1.0
                    lines = (b.decode("utf-8", "replace") for b in resp)
                    for payload in parse_sse(lines):
                        try:
                            frame = json.loads(payload)
                        except ValueError:
                            continue
                        if isinstance(frame, list):
                            for drop in frame:
                                yield drop
                        elif isinstance(frame, dict):
                            if frame.get("type") == "error":
                                raise PinnRadarError(str(frame.get("error") or "stream error"), body=frame)
                            if "to_price" in frame or "to" in frame:
                                yield frame
            except (AuthError, RateLimitError):
                raise
            except (PinnRadarError, OSError):
                if not reconnect:
                    raise
            if not reconnect:
                return
            time.sleep(backoff)
            backoff = min(max_backoff, backoff * 2)
