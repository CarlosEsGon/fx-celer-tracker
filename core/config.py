"""App configuration: .env (secrets/URLs/selection) + settings.yaml (behaviour)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    # selection
    trade_feed: str = "mock"          # mock | celer
    market_data: str = "mock"         # mock | blpapi

    # mock server
    mock_rest_url: str = "http://localhost:8000"
    mock_ws_url: str = "ws://localhost:8000/ws/trades"

    # real celer
    celer_ws_url: str = ""
    celer_rest_url: str = ""
    celer_auth_header_name: str = "Authorization"
    celer_auth_header_value: str = ""
    capture_raw: bool = True

    # blpapi
    blpapi_host: str = "localhost"
    blpapi_port: int = 8194
    blpapi_tick_window_sec: int = 120

    # app
    voice_enabled: bool = True
    digest_threshold: int = 5
    db_path: str = "data/trades.db"
    valuation_date_mode: str = "trade_date"   # trade_date | spot
    discount_rates: dict = field(default_factory=dict)
    tenor_buckets: list = field(default_factory=list)


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(
    env_path: str | Path = ".env",
    yaml_path: str | Path = "config/settings.yaml",
) -> Settings:
    load_dotenv(env_path)

    cfg: dict = {}
    yaml_file = Path(yaml_path)
    if yaml_file.exists():
        cfg = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}

    s = Settings()
    s.trade_feed = os.getenv("TRADE_FEED", s.trade_feed).lower()
    s.market_data = os.getenv("MARKET_DATA", s.market_data).lower()
    s.mock_rest_url = os.getenv("MOCK_REST_URL", s.mock_rest_url)
    s.mock_ws_url = os.getenv("MOCK_WS_URL", s.mock_ws_url)
    s.celer_ws_url = os.getenv("CELER_WS_URL", s.celer_ws_url)
    s.celer_rest_url = os.getenv("CELER_REST_URL", s.celer_rest_url)
    s.celer_auth_header_name = os.getenv(
        "CELER_AUTH_HEADER_NAME", s.celer_auth_header_name
    )
    s.celer_auth_header_value = os.getenv(
        "CELER_AUTH_HEADER_VALUE", s.celer_auth_header_value
    )
    s.capture_raw = _bool(os.getenv("CAPTURE_RAW"), s.capture_raw)
    s.blpapi_host = os.getenv("BLPAPI_HOST", s.blpapi_host)
    s.blpapi_port = int(os.getenv("BLPAPI_PORT", str(s.blpapi_port)))
    s.blpapi_tick_window_sec = int(
        os.getenv("BLPAPI_TICK_WINDOW_SEC", str(s.blpapi_tick_window_sec))
    )
    s.voice_enabled = _bool(os.getenv("VOICE_ENABLED"), s.voice_enabled)
    s.digest_threshold = int(os.getenv("DIGEST_THRESHOLD", str(s.digest_threshold)))
    s.db_path = os.getenv("DB_PATH", s.db_path)

    voice_cfg = cfg.get("voice", {})
    if "enabled" in voice_cfg and os.getenv("VOICE_ENABLED") is None:
        s.voice_enabled = bool(voice_cfg["enabled"])
    popup_cfg = cfg.get("popup", {})
    if "digest_threshold" in popup_cfg and os.getenv("DIGEST_THRESHOLD") is None:
        s.digest_threshold = int(popup_cfg["digest_threshold"])
    analytics_cfg = cfg.get("analytics", {})
    s.valuation_date_mode = analytics_cfg.get("valuation_date", s.valuation_date_mode)
    s.discount_rates = {
        str(k).upper(): float(v) for k, v in (cfg.get("discount_rates") or {}).items()
    }
    s.tenor_buckets = cfg.get("tenor_buckets") or []
    return s


def build_feed(s: Settings):
    from core.trade_feed import MockCelerFeed, RealCelerFeed

    if s.trade_feed == "celer":
        if not s.celer_ws_url:
            raise ValueError("TRADE_FEED=celer requires CELER_WS_URL in .env")
        return RealCelerFeed(
            ws_url=s.celer_ws_url,
            rest_url=s.celer_rest_url,
            auth_header_name=s.celer_auth_header_name,
            auth_header_value=s.celer_auth_header_value,
            capture_raw=s.capture_raw,
        )
    return MockCelerFeed(ws_url=s.mock_ws_url, rest_url=s.mock_rest_url)


def build_market_data(s: Settings):
    from core.market_data import BlpapiProvider, MockBloombergProvider

    if s.market_data == "blpapi":
        return BlpapiProvider(
            host=s.blpapi_host,
            port=s.blpapi_port,
            tick_window_sec=s.blpapi_tick_window_sec,
            discount_rates=s.discount_rates,
        )
    return MockBloombergProvider(rest_url=s.mock_rest_url)
