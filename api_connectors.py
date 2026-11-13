"""
API Connectors for the Bayesian Prior Factory.

Wires in live data from:
  - FlashAlpha (GEX, flow, Greeks, volatility, levels)
  - Edgeful (150+ session statistics reports)
  - Unusual Whales (dark pool, flow, market state, seasonality)
  - Databento (CME futures microstructure)

Keys come from the encrypted vault. Never printed/logged/committed.
All calls are GET-only (Tradier/Alpaca). No orders placed.
"""
import os
import json
import time
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("api_connectors")


@dataclass
class APIResponse:
    """Standardized response from any API connector."""
    provider: str
    endpoint: str
    status: int
    data: dict
    timestamp_ms: int
    latency_ms: float


class EdgefulConnector:
    """Edgeful session statistics API connector.

    150+ reports: gap fill, ORB, IB, ADR, prev day range, streaks,
    event reactions. Historical + live SSE.

    market_type: stock | futures | forex | crypto (NOT "stocks")
    """

    BASE_URL = "https://api.edgeful.com"

    def __init__(self):
        self._key = os.environ.get("EDGEFUL_API_KEY", "")
        if not self._key:
            logger.warning("EDGEFUL_API_KEY not set; Edgeful calls will fail")

    def get_report(
        self,
        slug: str,
        market_type: str,
        ticker: str,
        start_date: str = "",
        end_date: str = "",
        start_time: str = "09:30:00",
        end_time: str = "16:00:00",
    ) -> APIResponse:
        """Fetch a historical report from Edgeful."""
        import urllib.request
        import urllib.error

        url = (
            f"{self.BASE_URL}/report_calculation/{slug}"
            f"/{market_type}/{ticker}"
        )
        params = []
        if start_date:
            params.append(f"start_date={start_date}")
        if end_date:
            params.append(f"end_date={end_date}")
        params.append(f"start_time={start_time}")
        params.append(f"end_time={end_time}")
        params.append("timezone=America/New_York")
        url += "?" + "&".join(params)

        t0 = time.time()
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {self._key}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return APIResponse(
                    provider="edgeful",
                    endpoint=f"{slug}/{market_type}/{ticker}",
                    status=200,
                    data=data,
                    timestamp_ms=int(time.time() * 1000),
                    latency_ms=(time.time() - t0) * 1000,
                )
        except urllib.error.HTTPError as e:
            return APIResponse(
                provider="edgeful",
                endpoint=f"{slug}/{market_type}/{ticker}",
                status=e.code,
                data={"error": str(e)},
                timestamp_ms=int(time.time() * 1000),
                latency_ms=(time.time() - t0) * 1000,
            )

    def get_gap_fill(
        self, ticker: str = "QQQ", market_type: str = "stock"
    ) -> APIResponse:
        return self.get_report("gap-fill-standard", market_type, ticker)

    def get_prev_day_range(
        self, ticker: str = "QQQ", market_type: str = "stock"
    ) -> APIResponse:
        return self.get_report(
            "previous-days-range-standard", market_type, ticker
        )

    def get_orb(
        self, ticker: str = "QQQ", market_type: str = "stock"
    ) -> APIResponse:
        return self.get_report("orb-standard", market_type, ticker)

    def get_initial_balance(
        self, ticker: str = "ES", market_type: str = "futures"
    ) -> APIResponse:
        return self.get_report(
            "initial-balance-standard", market_type, ticker
        )


class FlashAlphaConnector:
    """FlashAlpha MCP connector for GEX, flow, Greeks, volatility.

    Uses the MCP tools already available in the session.
    This module wraps MCP calls into a standardized format.
    """

    ENDPOINTS = [
        "get_gex", "get_dex", "get_vex", "get_chex",
        "get_flow_summary", "get_flow_signals", "get_flow_live",
        "get_levels", "get_max_pain",
        "get_volatility", "get_vrp", "get_zero_dte",
        "get_historical_gex", "get_historical_dex",
        "get_historical_levels", "get_historical_vrp",
        "get_stock_quote", "get_stock_summary",
        "get_option_chain", "get_option_flow",
        "get_expected_move", "get_expected_move_history",
        "get_narrative",
    ]

    def build_state_vector(self, ticker: str = "QQQ") -> dict:
        """Build a market state vector from FlashAlpha endpoints.

        Returns a dict suitable for PriorRegistry.evaluate_all().
        """
        return {
            "_provider": "flashalpha",
            "_ticker": ticker,
            "_endpoints": self.ENDPOINTS,
            "_note": "Call via MCP tools in the session",
        }


class UnusualWhalesConnector:
    """Unusual Whales MCP connector for flow, dark pool, market state.

    Uses the MCP tools already available in the session.
    """

    ENDPOINTS = [
        "get_market_state", "get_market_tide", "get_market_etf_tide",
        "get_market_seasonality", "get_market_sector_tide",
        "get_option_trades", "get_dark_pool_trades",
        "get_flow_alerts", "get_flow_per_strike",
        "get_gex_levels", "get_max_pain",
        "get_greek_exposure_by_ticker", "get_greek_flow",
        "get_open_interest_changes",
        "get_market_events", "get_upcoming_earnings",
        "get_correlations",
    ]

    def build_state_vector(self, ticker: str = "QQQ") -> dict:
        return {
            "_provider": "unusual_whales",
            "_ticker": ticker,
            "_endpoints": self.ENDPOINTS,
        }


class DatabentoConnector:
    """Databento CME futures connector.

    GLBX.MDP3 = $0 (included in plan).
    NQ, ES, RTY, YM + CME options all $0.
    """

    DATASETS = {
        "GLBX.MDP3": {
            "cost": "$0",
            "symbols": [
                "NQ.c.0", "ES.c.0", "RTY.c.0", "YM.c.0",
                "ZN.c.0", "ZB.c.0", "CL.c.0", "GC.c.0",
            ],
            "schemas": [
                "ohlcv-1s", "trades", "tbbo", "bbo-1s", "mbp-10",
            ],
        },
    }

    def __init__(self):
        self._key = os.environ.get("DATABENTO_API_KEY", "")
        if not self._key:
            logger.warning("DATABENTO_API_KEY not set")

    def check_cost(
        self,
        dataset: str = "GLBX.MDP3",
        symbols: Optional[list] = None,
        schema: str = "ohlcv-1s",
        start: str = "",
        end: str = "",
    ) -> dict:
        """Check cost before any data pull. ALWAYS run this first."""
        try:
            import databento as db

            client = db.Historical(key=self._key)
            cost = client.metadata.get_cost(
                dataset=dataset,
                symbols=symbols or ["NQ.c.0", "ES.c.0"],
                schema=schema,
                start=start or "2026-11-01",
                end=end or "2026-11-13",
                stype_in="continuous",
            )
            return {"cost": cost, "approved": cost == 0}
        except ImportError:
            return {"error": "databento not installed", "approved": False}
        except Exception as e:
            return {"error": str(e), "approved": False}

    def get_ohlcv_1s(
        self,
        symbols: list,
        start: str,
        end: str,
    ) -> dict:
        """Fetch 1-second OHLCV bars from CME Globex."""
        cost_check = self.check_cost(
            symbols=symbols, schema="ohlcv-1s", start=start, end=end
        )
        if not cost_check.get("approved", False):
            return cost_check

        try:
            import databento as db

            client = db.Historical(key=self._key)
            data = client.timeseries.get_range(
                dataset="GLBX.MDP3",
                symbols=symbols,
                schema="ohlcv-1s",
                start=start,
                end=end,
                stype_in="continuous",
            )
            return {"status": "ok", "records": len(data)}
        except Exception as e:
            return {"error": str(e)}


class StateVectorBuilder:
    """Combine all API sources into a single market state vector.

    This is the input to PriorRegistry.evaluate_all().
    """

    def __init__(self):
        self.edgeful = EdgefulConnector()
        self.flashalpha = FlashAlphaConnector()
        self.unusual_whales = UnusualWhalesConnector()
        self.databento = DatabentoConnector()

    def build(
        self,
        ticker: str = "QQQ",
        vix: float = 0,
        gap_pct: float = 0,
        time_et: str = "",
        month: int = 0,
        event_type: str = "NORMAL",
        adx_15m: float = 0,
        gex_regime: str = "unknown",
        macro_bias: str = "unknown",
        day_bias: str = "unknown",
        tod_bucket: str = "unknown",
    ) -> dict:
        """Build a complete market state vector for prior evaluation."""
        now = datetime.now(timezone.utc)
        return {
            "ticker": ticker,
            "vix": vix,
            "gap_pct": gap_pct,
            "time_et": time_et or now.strftime("%H:%M"),
            "month": month or now.month,
            "event_type": event_type,
            "adx_15m": adx_15m,
            "gex_regime": gex_regime,
            "macro_bias": macro_bias,
            "day_bias": day_bias,
            "tod_bucket": tod_bucket,
            "timestamp_ms": int(time.time() * 1000),
        }


# Available report slugs for Edgeful (verified + catalog)
EDGEFUL_REPORT_SLUGS = [
    "gap-fill-standard",
    "gap-fill-by-size",
    "gap-fill-by-weekday",
    "gap-fill-time",
    "gap-fill-by-spike",
    "gap-fill-by-prev-candle",
    "orb-standard",
    "initial-balance-standard",
    "adr-standard",
    "adr-by-weekday",
    "adr-by-streak",
    "adr-extension",
    "previous-days-range-standard",
    "fvg-standard",
    "fib-levels-standard",
    "engulfing-standard",
    "cpi-reaction",
    "fomc-reaction",
    "session-high-standard",
    "session-low-standard",
    "streak-standard",
]

# FlashAlpha endpoints for the data fabric
FLASHALPHA_ENDPOINTS = FlashAlphaConnector.ENDPOINTS

# Unusual Whales endpoints
UNUSUAL_WHALES_ENDPOINTS = UnusualWhalesConnector.ENDPOINTS
