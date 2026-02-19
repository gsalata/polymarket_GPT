"""
Polymarket Arbitrage Simulator + Live Paper-Trader (Public APIs Only)
Based on Jakub's 2026 Framework — Educational & Profitability Testing
Uses public Gamma + CLOB read endpoints — no keys, no trading, simulation only
"""

# ==============================================================================
# Executive Summary (2026-02-19)
# - Added pinned-market support by Gamma slug (default: "btc-updown-5m-1771611600").
#   Edit DEFAULT_PINNED_SLUG below, or change it from the sidebar at runtime.
# - Updated fetch_markets so max_markets=0 means "ALL" (with pagination via limit/offset)
#   and an optional ABSOLUTE_MAX safety cap to prevent accidental overload.
# - Added caching for pinned-market resolution to avoid Gamma spam (TTL=30s).
# - ensure_pinned_market() is called exactly once per scan cycle (LIVE mode only),
#   immediately before scan_markets_once().
# - Preserved original styling/layout; ensured consistent 4-space indentation.
#
# Key Inserts/Updates (Markdown table)
# | Function / Change            | Type      | Location (section header)                         |
# |-----------------------------|-----------|---------------------------------------------------|
# | fetch_market_by_slug        | Inserted  | HELPER FUNCTIONS                                  |
# | ensure_pinned_market        | Inserted  | HELPER FUNCTIONS                                  |
# | fetch_markets pagination    | Updated   | API FUNCTIONS                                     |
# | max_markets (0=ALL) UI      | Updated   | SIDEBAR                                           |
# | pinned slug UI input        | Inserted  | SIDEBAR                                           |
# | pinned badge in results     | Inserted  | TAB 1 — LIVE PAPER TRADER (results table builder) |
# | ABSOLUTE_MAX safety cap     | Inserted  | CONSTANTS & DEFAULTS + SIDEBAR                    |
#
# Notes
# - Polymarket Gamma list endpoints support pagination with limit/offset; /markets supports slug filtering.
# - CLOB read endpoints are public; orderbook depth can be fetched with GET /book?token_id=...
# - For high-performance scanning, consider async fetching or CLOB batch endpoints (e.g., POST /books).
# ==============================================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import requests
import time
import json
import random
from collections import deque
from datetime import datetime

# ─────────────────────────────────────────────
# PAGE CONFIG & DARK THEME STYLES
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Polymarket Arb Simulator",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Syne:wght@400;600;700;800&display=swap');

:root {
    --bg: #090c10;
    --surface: #0d1117;
    --surface2: #161b22;
    --border: #21262d;
    --accent: #00ff88;
    --accent2: #0ea5e9;
    --danger: #ff4444;
    --warn: #f59e0b;
    --text: #e6edf3;
    --muted: #7d8590;
}

html, body, [data-testid="stApp"] {
    background-color: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Syne', sans-serif;
}

[data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
}

.stTabs [data-baseweb="tab-list"] {
    background: var(--surface) !important;
    border-bottom: 1px solid var(--border);
    gap: 0;
}

.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--muted) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
    padding: 0.6rem 1.2rem !important;
    border-bottom: 2px solid transparent !important;
}

.stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: transparent !important;
}

.metric-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    font-family: 'JetBrains Mono', monospace;
}

.metric-val {
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1;
}

.metric-val.red { color: var(--danger); }
.metric-val.blue { color: var(--accent2); }
.metric-val.warn { color: var(--warn); }

.metric-label {
    font-size: 0.7rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
}

.opportunity-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 99px;
    font-size: 0.7rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.badge-hot { background: rgba(0,255,136,0.15); color: #00ff88; border: 1px solid rgba(0,255,136,0.3); }
.badge-warm { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.badge-cold { background: rgba(125,133,144,0.1); color: #7d8590; border: 1px solid rgba(125,133,144,0.2); }
.badge-exec { background: rgba(14,165,233,0.15); color: #0ea5e9; border: 1px solid rgba(14,165,233,0.3); }

.log-entry {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    padding: 4px 8px;
    border-left: 2px solid var(--border);
    margin: 2px 0;
    color: var(--muted);
}

.log-entry.arb { border-color: var(--accent); color: var(--text); }
.log-entry.warn { border-color: var(--warn); }
.log-entry.err  { border-color: var(--danger); }

.formula-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent2);
    border-radius: 6px;
    padding: 1.2rem 1.5rem;
    margin: 1rem 0;
}

.hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 2.4rem;
    font-weight: 800;
    background: linear-gradient(135deg, #00ff88 0%, #0ea5e9 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.1;
    margin: 0;
}

.hero-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 0.4rem;
    letter-spacing: 0.05em;
}

.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}

.dot-green { background: var(--accent); box-shadow: 0 0 8px var(--accent); animation: pulse 2s infinite; }
.dot-red   { background: var(--danger); }
.dot-gray  { background: var(--muted); }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.stButton > button {
    background: linear-gradient(135deg, #00ff88, #0ea5e9) !important;
    color: #000 !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 0.5rem 1.5rem !important;
}

.stButton > button:hover {
    opacity: 0.85 !important;
    transform: translateY(-1px);
}

.market-row {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.8rem 1rem;
    margin: 0.4rem 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
}

.market-row:hover {
    border-color: var(--accent2);
}

div[data-testid="stExpander"] {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

code {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.78rem !important;
}

.stSlider > div > div { color: var(--accent) !important; }

hr { border-color: var(--border) !important; }

[data-testid="stMetric"] {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.8rem 1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────
# CONSTANTS & DEFAULTS
# ─────────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

DEFAULT_PINNED_SLUG = "btc-updown-5m-1771611600"

# When max_markets=0 (ALL), this safety cap prevents scanning an unbounded number of markets.
DEFAULT_ABSOLUTE_MAX_MARKETS = 500

DEFAULT_PARAMS = {
    "profit_threshold_bps": 30,
    "clob_fee_pct": 0.075,
    "gas_merge_usd": 0.5,
    "swap_spread_pct": 0.02,
    "buffer_bps": 10,
    "min_trade_usd": 50.0,
    "max_trade_usd": 5000.0,
    "slippage_pct": 0.5,
    "refresh_interval_sec": 10,
    "min_volume_usd": 100_000,
    "max_markets": 10,
}

# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
def init_state():
    defaults = {
        "running": False,
        "live_mode": False,
        "markets": {},  # condition_id -> market info dict
        "trade_history": [],
        "pnl_series": [],
        "logs": deque(maxlen=150),
        "total_pnl": 0.0,
        "total_trades": 0,
        "total_opps": 0,
        "last_fetch": 0.0,
        "edge_history": [],
        "session_start": time.time(),
        "pinned_slug": DEFAULT_PINNED_SLUG,
        "absolute_max_markets": DEFAULT_ABSOLUTE_MAX_MARKETS,
        **DEFAULT_PARAMS,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────
def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.appendleft({"ts": ts, "msg": msg, "level": level})


@st.cache_data(ttl=30, show_spinner=False)
def fetch_market_by_slug(slug: str):
    """
    Resolve a Polymarket market from Gamma by slug.
    Cached to reduce repeated Gamma calls during Streamlit reruns.
    """
    if not slug:
        return None

    try:
        r = requests.get(
            f"{GAMMA_API}/markets",
            params={"slug": slug},
            timeout=10,
        )
        if r.status_code == 429:
            time.sleep(1)
            r = requests.get(f"{GAMMA_API}/markets", params={"slug": slug}, timeout=10)

        r.raise_for_status()
        data = r.json()
        if not data:
            return None

        m = data[0]
        outcomes = m.get("outcomes", [])
        clob_ids = m.get("clobTokenIds", [])

        if not isinstance(outcomes, list):
            try:
                outcomes = json.loads(outcomes)
            except Exception:
                outcomes = []

        if not isinstance(clob_ids, list):
            try:
                clob_ids = json.loads(clob_ids)
            except Exception:
                clob_ids = []

        if len(outcomes) != 2 or len(clob_ids) != 2:
            return None

        vol = float(m.get("volume", 0) or 0)

        return {
            "condition_id": m.get("conditionId", m.get("id", "")),
            "question": m.get("question", slug)[:80],
            "yes_token": clob_ids[0],
            "no_token": clob_ids[1],
            "volume": vol,
            "outcomes": outcomes,
            "_pinned": True,
        }
    except Exception:
        return None


def ensure_pinned_market(markets: list, slug: str):
    """
    Force-include a pinned market in the scan universe (dedupe by condition_id).
    Called exactly once per scan cycle (LIVE mode) just before scan_markets_once().
    """
    pinned = fetch_market_by_slug(slug)
    if not pinned:
        if slug:
            log(f"[PINNED] Could not resolve pinned slug={slug}", "warn")
        return markets

    cid = pinned.get("condition_id")
    if cid:
        markets = [m for m in markets if m.get("condition_id") != cid]

    markets.insert(0, pinned)
    st.session_state["pinned_market"] = pinned
    return markets


def get_effective_prices(yes_ask, yes_bid, no_ask, no_bid):
    """Compute effective buy/sell prices (mimics article's price_utils)."""
    spread_yes = yes_ask - yes_bid if yes_bid > 0 else 0
    spread_no = no_ask - no_bid if no_bid > 0 else 0
    # Effective buy = ask + half spread impact
    eff_buy_yes = yes_ask + spread_yes * 0.1
    eff_buy_no = no_ask + spread_no * 0.1
    eff_sell_yes = yes_bid - spread_yes * 0.1 if yes_bid > 0 else 0
    eff_sell_no = no_bid - spread_no * 0.1 if no_bid > 0 else 0
    return {
        "effective_buy_yes": min(eff_buy_yes, 0.99),
        "effective_buy_no": min(eff_buy_no, 0.99),
        "effective_sell_yes": max(eff_sell_yes, 0.01),
        "effective_sell_no": max(eff_sell_no, 0.01),
    }


def compute_edge(
    buy_yes,
    buy_no,
    clob_fee=0.00075,
    gas_usd=0.5,
    swap_spread=0.0002,
    buffer_bps=10,
    trade_size_usd=500,
):
    """Full cost model from article: edge = 1 - (yes+no) - fees - gas - spread - buffer"""
    long_cost = buy_yes + buy_no
    raw_edge = 1.0 - long_cost
    fees_clob = clob_fee * 2  # both legs
    gas_frac = gas_usd / trade_size_usd if trade_size_usd > 0 else 0
    buffer = buffer_bps / 10000
    net_edge = raw_edge - fees_clob - gas_frac - swap_spread - buffer
    return raw_edge, net_edge


def simulate_execution(buy_yes, buy_no, net_edge, params):
    """Simulate fill with slippage and partial fill chance."""
    slip = random.uniform(0, params["slippage_pct"] / 100)
    partial_fill_pct = random.uniform(0.75, 1.0)  # 75-100% fill
    trade_size = random.uniform(
        params["min_trade_usd"], min(params["max_trade_usd"], 2000)
    )
    cost_per_share = buy_yes + buy_no + slip
    if cost_per_share >= 1.0:
        return None
    shares = (trade_size * partial_fill_pct) / cost_per_share
    gross_pnl = shares * (1.0 - cost_per_share)
    gas = params["gas_merge_usd"]
    net_pnl = gross_pnl - gas
    return {
        "trade_size_usd": trade_size * partial_fill_pct,
        "shares": shares,
        "fill_pct": partial_fill_pct * 100,
        "cost_per_set": cost_per_share,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "net_edge_pct": net_edge * 100,
    }


# ─────────────────────────────────────────────
# API FUNCTIONS
# ─────────────────────────────────────────────
def _http_get_with_backoff(url: str, params=None, timeout: int = 10, max_retries: int = 3):
    """
    Small helper to back off on 429s. Keeps behavior predictable and avoids hard failures.
    """
    attempt = 0
    while True:
        attempt += 1
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code != 429 or attempt >= max_retries:
            return r
        sleep_s = min(2 ** (attempt - 1), 8)  # 1s, 2s, 4s (cap)
        time.sleep(sleep_s + random.uniform(0, 0.25))


@st.cache_data(ttl=60, show_spinner=False)
def fetch_markets(min_volume=100_000, limit=20, absolute_max=DEFAULT_ABSOLUTE_MAX_MARKETS):
    """
    Fetch markets from Gamma API (public, no auth).

    Updates:
    - limit == 0 means "ALL" (subject to absolute_max safety cap).
    - Uses Gamma pagination (limit/offset) to fetch multiple pages.
    - Returns binary YES/NO markets only (2 outcomes, 2 clobTokenIds).
    """
    try:
        url = f"{GAMMA_API}/markets"

        # Interpret limit=0 as ALL, but keep a safety cap.
        want_all = (limit is None) or (int(limit) == 0)
        requested_limit = 0 if limit is None else int(limit)

        page_size = 200  # reduce number of Gamma calls, still reasonable payload size
        offset = 0

        out = []
        while True:
            params = {
                "active": "true",
                "closed": "false",
                "limit": page_size,
                "offset": offset,
                "order": "volume",
                "ascending": "false",
                "volume_num_min": float(min_volume),
            }

            r = _http_get_with_backoff(url, params=params, timeout=10, max_retries=3)
            r.raise_for_status()
            data = r.json() or []

            if not data:
                break

            for m in data:
                outcomes = m.get("outcomes", [])
                clob_ids = m.get("clobTokenIds", [])

                if not isinstance(outcomes, list):
                    try:
                        outcomes = json.loads(outcomes)
                    except Exception:
                        continue

                if not isinstance(clob_ids, list):
                    try:
                        clob_ids = json.loads(clob_ids)
                    except Exception:
                        continue

                if len(outcomes) == 2 and len(clob_ids) == 2:
                    vol = float(m.get("volume", 0) or 0)
                    if vol >= float(min_volume):
                        out.append(
                            {
                                "condition_id": m.get("conditionId", m.get("id", "")),
                                "question": m.get("question", "Unknown")[:80],
                                "yes_token": clob_ids[0],
                                "no_token": clob_ids[1],
                                "volume": vol,
                                "outcomes": outcomes,
                            }
                        )

                        # Stop early if we reached requested limit
                        if (not want_all) and len(out) >= requested_limit:
                            return out[:requested_limit]

                        # Safety cap when scanning "ALL"
                        if want_all and absolute_max and len(out) >= int(absolute_max):
                            return out[: int(absolute_max)]

            # Stop if last page was partial (no more results)
            if len(data) < page_size:
                break

            offset += page_size
            continue

        return out if want_all else out[:requested_limit]
    except Exception:
        return []


def fetch_orderbook(token_id: str):
    """Fetch order book for a token from CLOB API (public)."""
    if not token_id:
        return None
    try:
        r = _http_get_with_backoff(
            f"{CLOB_API}/book",
            params={"token_id": token_id},
            timeout=6,
            max_retries=3,
        )
        if r.status_code == 429:
            return None
        r.raise_for_status()
        data = r.json() or {}
        sells = data.get("asks", data.get("sells", []))
        bids = data.get("bids", [])
        return {"bids": bids, "asks": sells}
    except Exception as e:
        log(f"[API] Orderbook error ({token_id[:10]}…): {e}", "err")
        return None


def best_ask(ob):
    """Extract best ask price from orderbook."""
    if not ob:
        return None
    asks = ob.get("asks", [])
    prices = []
    for o in asks:
        try:
            p = float(o.get("price", o.get("p", 0)))
            s = float(o.get("size", o.get("s", 0)))
            if p > 0 and s > 0:
                prices.append(p)
        except Exception:
            pass
    return min(prices) if prices else None


def best_bid(ob):
    """Extract best bid price from orderbook."""
    if not ob:
        return None
    bids = ob.get("bids", [])
    prices = []
    for o in bids:
        try:
            p = float(o.get("price", o.get("p", 0)))
            s = float(o.get("size", o.get("s", 0)))
            if p > 0 and s > 0:
                prices.append(p)
        except Exception:
            pass
    return max(prices) if prices else None


# ─────────────────────────────────────────────
# SYNTHETIC DATA GENERATOR
# ─────────────────────────────────────────────
def generate_synthetic_markets(n=8):
    topics = [
        "Will Bitcoin exceed $150,000 by end of 2026?",
        "Will the Fed cut rates 3+ times in 2026?",
        "Will Ethereum ETF see $5B inflows in Q1?",
        "Will OpenAI release GPT-5 before June 2026?",
        "Will US GDP growth exceed 3% in 2026?",
        "Will the S&P 500 hit 7000 in 2026?",
        "Will inflation drop below 2% by mid-2026?",
        "Will NVIDIA market cap surpass $5T?",
        "Will Solana flip Ethereum by TVL in 2026?",
        "Will SpaceX Starship reach orbit in 2026?",
    ]
    markets = []
    for i, q in enumerate(topics[:n]):
        yes_ask_base = random.uniform(0.30, 0.70)
        no_ask_base = random.uniform(0.30, 0.70)
        if random.random() < 0.25:
            deficit = random.uniform(0.005, 0.025)
            no_ask_base = 1.0 - yes_ask_base - deficit
        markets.append(
            {
                "condition_id": f"synth_{i:04d}",
                "question": q,
                "yes_token": f"yes_{i:04d}",
                "no_token": f"no_{i:04d}",
                "volume": random.uniform(200_000, 5_000_000),
                "outcomes": ["Yes", "No"],
                "_synth_yes_ask": yes_ask_base,
                "_synth_no_ask": no_ask_base,
            }
        )
    return markets


def synth_orderbook(base_price):
    """Generate realistic synthetic orderbook."""
    spread = random.uniform(0.002, 0.015)
    ask = base_price + spread / 2
    bid = base_price - spread / 2
    ask = max(0.01, min(0.99, ask + random.gauss(0, 0.003)))
    bid = max(0.01, min(ask - 0.002, bid + random.gauss(0, 0.003)))
    asks = [
        {"price": str(round(ask + i * 0.003, 4)), "size": str(round(random.uniform(50, 500), 1))}
        for i in range(5)
    ]
    bids = [
        {"price": str(round(bid - i * 0.003, 4)), "size": str(round(random.uniform(50, 500), 1))}
        for i in range(5)
    ]
    return {"asks": asks, "bids": bids}


# ─────────────────────────────────────────────
# MAIN SCAN LOOP (one iteration)
# NOTE: Must remain a top-level function and behavior must remain unchanged.
# ─────────────────────────────────────────────
def scan_markets_once(markets: list, params: dict):
    """Scan all markets for arb, return results list."""
    threshold = params["profit_threshold_bps"] / 10000
    results = []

    for m in markets:
        q = m["question"]
        cid = m["condition_id"]
        synth = cid.startswith("synth_")

        if synth:
            base_yes = m.get("_synth_yes_ask", 0.5)
            base_no = m.get("_synth_no_ask", 0.5)
            # random walk
            m["_synth_yes_ask"] = max(0.02, min(0.97, base_yes + random.gauss(0, 0.004)))
            m["_synth_no_ask"] = max(0.02, min(0.97, base_no + random.gauss(0, 0.004)))
            ob_yes = synth_orderbook(m["_synth_yes_ask"])
            ob_no = synth_orderbook(m["_synth_no_ask"])
        else:
            ob_yes = fetch_orderbook(m["yes_token"])
            ob_no = fetch_orderbook(m["no_token"])
            time.sleep(0.2)  # rate limit courtesy

        a_yes = best_ask(ob_yes)
        a_no = best_ask(ob_no)
        b_yes = best_bid(ob_yes)
        b_no = best_bid(ob_no)

        if a_yes is None or a_no is None:
            results.append(
                {
                    "question": q[:60],
                    "yes_ask": None,
                    "no_ask": None,
                    "raw_edge": None,
                    "net_edge": None,
                    "status": "NO DATA",
                    "pnl": 0,
                    "condition_id": cid,
                }
            )
            continue

        eff = get_effective_prices(a_yes, b_yes or 0, a_no, b_no or 0)
        buy_yes = eff["effective_buy_yes"]
        buy_no = eff["effective_buy_no"]

        raw_edge, net_edge = compute_edge(
            buy_yes,
            buy_no,
            clob_fee=params["clob_fee_pct"] / 100,
            gas_usd=params["gas_merge_usd"],
            swap_spread=params["swap_spread_pct"] / 100,
            buffer_bps=params["buffer_bps"],
            trade_size_usd=params["min_trade_usd"],
        )

        st.session_state.edge_history.append(
            {
                "ts": time.time(),
                "market": q[:30],
                "raw_edge_pct": raw_edge * 100,
                "net_edge_pct": net_edge * 100,
            }
        )

        status = "COLD"
        sim_pnl = 0.0

        if net_edge > threshold:
            st.session_state.total_opps += 1
            status = "HOT 🔥"
            exec_result = simulate_execution(buy_yes, buy_no, net_edge, params)
            if exec_result:
                sim_pnl = exec_result["net_pnl"]
                st.session_state.total_pnl += sim_pnl
                st.session_state.total_trades += 1
                ts = datetime.now().strftime("%H:%M:%S")
                trade = {
                    "ts": ts,
                    "question": q[:50],
                    "buy_yes": buy_yes,
                    "buy_no": buy_no,
                    "raw_edge_pct": raw_edge * 100,
                    "net_edge_pct": net_edge * 100,
                    "net_pnl": sim_pnl,
                    "trade_size": exec_result["trade_size_usd"],
                    "fill_pct": exec_result["fill_pct"],
                }
                st.session_state.trade_history.append(trade)
                st.session_state.pnl_series.append({"ts": ts, "cumulative_pnl": st.session_state.total_pnl})
                log(
                    f"[ARB] {q[:45]}... | edge={net_edge*100:.2f}bps | PnL=+${sim_pnl:.2f}",
                    "arb",
                )
                status = "EXECUTED ✓"
        elif raw_edge > 0:
            status = "WARM"

        results.append(
            {
                "question": q[:60],
                "yes_ask": a_yes,
                "no_ask": a_no,
                "raw_edge": raw_edge * 100,
                "net_edge": net_edge * 100,
                "status": status,
                "pnl": sim_pnl,
                "condition_id": cid,
                "volume": m.get("volume", 0),
            }
        )

    return results


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
    <div style='font-family: JetBrains Mono; font-size: 0.65rem; color: #7d8590;
                text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 0.5rem;'>
    ⚡ POLYMARKET ARB
    </div>
    """,
        unsafe_allow_html=True,
    )

    mode = st.toggle(
        "🌐 Live Polymarket Data",
        value=st.session_state.live_mode,
        help="OFF = Synthetic random walk. ON = Real public Polymarket APIs (no auth)",
    )
    st.session_state.live_mode = mode

    if mode:
        st.caption("Using real Gamma + CLOB public endpoints")
    else:
        st.caption("Using synthetic random walk simulation")

    st.divider()
    st.markdown("**⚙️ Market Filters**")

    st.session_state.refresh_interval_sec = st.slider(
        "Refresh interval (sec)",
        3,
        60,
        int(st.session_state.refresh_interval_sec),
    )

    st.session_state.min_volume_usd = st.number_input(
        "Min Volume ($)",
        0,
        10_000_000,
        int(st.session_state.min_volume_usd),
        step=50_000,
    )

    st.session_state.max_markets = st.slider(
        "Max markets to monitor (0 = ALL)",
        0,
        250,
        int(st.session_state.max_markets),
        step=5,
    )

    st.session_state.absolute_max_markets = st.number_input(
        "ABSOLUTE_MAX safety cap (only when max_markets=0)",
        min_value=50,
        max_value=20_000,
        value=int(st.session_state.absolute_max_markets),
        step=50,
        help="Prevents accidental huge scans when max_markets=0 (ALL).",
    )

    st.divider()
    st.markdown("**📌 Pinned Market**")
    st.session_state.pinned_slug = (
        st.text_input(
            "Pinned market slug (always included in LIVE scans)",
            value=str(st.session_state.pinned_slug),
            help="Example: btc-updown-5m-1771611600",
        ).strip()
        or DEFAULT_PINNED_SLUG
    )

    st.divider()
    st.markdown("**💰 Cost Model**")
    st.session_state.profit_threshold_bps = st.slider(
        "Profit threshold (bps)",
        5,
        200,
        int(st.session_state.profit_threshold_bps),
    )
    st.session_state.clob_fee_pct = st.number_input(
        "CLOB fee (%)",
        0.0,
        1.0,
        float(st.session_state.clob_fee_pct),
        0.005,
        format="%.3f",
    )
    st.session_state.gas_merge_usd = st.number_input(
        "Gas/merge cost ($)",
        0.0,
        5.0,
        float(st.session_state.gas_merge_usd),
        0.1,
        format="%.2f",
    )
    st.session_state.swap_spread_pct = st.number_input(
        "Swap spread (%)",
        0.0,
        1.0,
        float(st.session_state.swap_spread_pct),
        0.005,
        format="%.3f",
    )
    st.session_state.buffer_bps = st.slider(
        "Safety buffer (bps)",
        0,
        50,
        int(st.session_state.buffer_bps),
    )

    st.divider()
    st.markdown("**📐 Execution**")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.min_trade_usd = st.number_input(
            "Min trade $",
            10,
            1000,
            int(st.session_state.min_trade_usd),
            10,
        )
    with c2:
        st.session_state.max_trade_usd = st.number_input(
            "Max trade $",
            100,
            50_000,
            int(st.session_state.max_trade_usd),
            100,
        )
    st.session_state.slippage_pct = st.number_input(
        "Max slippage (%)",
        0.0,
        5.0,
        float(st.session_state.slippage_pct),
        0.1,
        format="%.1f",
    )

    st.divider()
    if st.button("🗑 Reset Session"):
        for k in [
            "trade_history",
            "pnl_series",
            "logs",
            "total_pnl",
            "total_trades",
            "total_opps",
            "edge_history",
        ]:
            if k in ["trade_history", "pnl_series", "edge_history"]:
                st.session_state[k] = []
            elif k == "logs":
                st.session_state[k] = deque(maxlen=150)
            else:
                st.session_state[k] = 0.0
        st.session_state.session_start = time.time()
        st.rerun()

    if st.session_state.live_mode and int(st.session_state.max_markets) == 0:
        st.warning(
            "max_markets=0 scans ALL markets (capped by ABSOLUTE_MAX). "
            "This can be slow due to per-market CLOB orderbook calls."
        )

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown(
        """
    <p class="hero-title">Polymarket Arbitrage Simulator</p>
    <p class="hero-sub">LIVE PAPER-TRADER · PUBLIC APIs ONLY · JAKUB'S 2026 FRAMEWORK</p>
    """,
        unsafe_allow_html=True,
    )
with col_h2:
    is_live = st.session_state.live_mode
    status_html = (
        '<span class="status-dot dot-green"></span> LIVE POLYMARKET'
        if is_live
        else '<span class="status-dot dot-gray"></span> SYNTHETIC SIM'
    )
    st.markdown(
        f"""
    <div style='text-align:right; margin-top:1.5rem; font-family: JetBrains Mono;
                font-size:0.75rem; color: {"#00ff88" if is_live else "#7d8590"}'>
    {status_html}
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("---")

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tabs = st.tabs(["⚡ Paper Trader", "📐 Theory & Invariant", "📊 Analytics", "🧑‍💻 Code Reference"])

# ══════════════════════════════════════════════════════
# TAB 1 — LIVE PAPER TRADER
# ══════════════════════════════════════════════════════
with tabs[0]:
    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
    with c1:
        if st.session_state.running:
            if st.button("⏸ Pause Scanner", use_container_width=True):
                st.session_state.running = False
                log("Scanner paused", "warn")
                st.rerun()
        else:
            if st.button("▶ Start Scanner", use_container_width=True):
                st.session_state.running = True
                log(f"Scanner started — {'LIVE' if st.session_state.live_mode else 'SYNTHETIC'} mode")
                st.rerun()

    with c2:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-val {'red' if st.session_state.total_pnl < 0 else ''}">${st.session_state.total_pnl:.2f}</div>
            <div class="metric-label">Simulated PnL</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-val blue">{st.session_state.total_trades}</div>
            <div class="metric-label">Trades Executed</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-val warn">{st.session_state.total_opps}</div>
            <div class="metric-label">Opportunities Found</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    with c5:
        elapsed = int(time.time() - st.session_state.session_start)
        mins, secs = divmod(elapsed, 60)
        st.markdown(
            f"""
        <div class="metric-card">
            <div class="metric-val">{mins:02d}:{secs:02d}</div>
            <div class="metric-label">Session Time</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if st.session_state.running:
        now = time.time()
        interval = int(st.session_state.refresh_interval_sec)

        if now - st.session_state.last_fetch >= interval:
            st.session_state.last_fetch = now

            with st.spinner("🔍 Fetching markets & scanning orderbooks..."):
                if st.session_state.live_mode:
                    markets = fetch_markets(
                        min_volume=st.session_state.min_volume_usd,
                        limit=int(st.session_state.max_markets),
                        absolute_max=int(st.session_state.absolute_max_markets),
                    )
                    if markets is None:
                        markets = []

                    markets = ensure_pinned_market(markets, st.session_state.pinned_slug)

                    if not markets:
                        st.warning("No live markets available (including pinned).")
                else:
                    n = int(st.session_state.max_markets) if int(st.session_state.max_markets) > 0 else 10
                    markets = generate_synthetic_markets(n)

                if markets:
                    params = {k: st.session_state[k] for k in DEFAULT_PARAMS}
                    results = scan_markets_once(markets, params)
                    st.session_state["last_results"] = results
                    log(f"Scan complete: {len(results)} markets checked")
        else:
            countdown = interval - int(now - st.session_state.last_fetch)
            st.caption(f"⏱ Next scan in {countdown}s")

        time.sleep(0.5)
        st.rerun()

    results = st.session_state.get("last_results", [])
    pinned_market = st.session_state.get("pinned_market", {})
    pinned_cid = pinned_market.get("condition_id")

    if results:
        st.markdown("### 📋 Market Scan Results")

        rows = []
        for r in results:
            is_pinned = bool(pinned_cid and r.get("condition_id") == pinned_cid)
            pinned_prefix = "📌 " if is_pinned else ""

            if r["yes_ask"] is None:
                rows.append(
                    {
                        "Market": pinned_prefix + r["question"],
                        "YES Ask": "—",
                        "NO Ask": "—",
                        "Raw Edge": "—",
                        "Net Edge": "—",
                        "Status": r["status"],
                        "Sim PnL": "$0.00",
                        "Vol ($M)": f"{r.get('volume', 0)/1e6:.1f}",
                    }
                )
                continue

            ne = r["net_edge"] or 0
            re = r["raw_edge"] or 0
            rows.append(
                {
                    "Market": pinned_prefix + r["question"],
                    "YES Ask": f"{r['yes_ask']:.4f}",
                    "NO Ask": f"{r['no_ask']:.4f}",
                    "Raw Edge": f"{re:.2f}%",
                    "Net Edge": f"{ne:.2f}%",
                    "Status": r["status"],
                    "Sim PnL": f"${r['pnl']:.2f}" if r["pnl"] != 0 else "—",
                    "Vol ($M)": f"{r.get('volume', 0)/1e6:.1f}",
                }
            )

        df = pd.DataFrame(rows)

        def style_row(row):
            styles = [""] * len(row)
            status_val = str(row.get("Status", ""))
            if "HOT" in status_val or "EXEC" in status_val:
                return ["background-color: rgba(0,255,136,0.05); color: #00ff88"] * len(row)
            if "WARM" in status_val:
                return ["background-color: rgba(245,158,11,0.04); color: #f59e0b"] * len(row)
            return styles

        styled = df.style.apply(style_row, axis=1)
        st.dataframe(styled, use_container_width=True, height=min(400, 50 + 35 * len(df)))

        if pinned_market:
            st.caption(
                f"📌 Pinned: {pinned_market.get('question','')} · YES {str(pinned_market.get('yes_token',''))[:10]}… · NO {str(pinned_market.get('no_token',''))[:10]}…"
            )

    elif not st.session_state.running:
        st.info("▶ Press **Start Scanner** to begin monitoring markets for arbitrage opportunities.")

    if st.session_state.trade_history:
        st.markdown("### 💼 Recent Simulated Executions")
        recent = list(reversed(st.session_state.trade_history[-20:]))
        trade_df = pd.DataFrame(recent)[
            ["ts", "question", "buy_yes", "buy_no", "raw_edge_pct", "net_edge_pct", "net_pnl", "trade_size", "fill_pct"]
        ]
        trade_df.columns = ["Time", "Market", "YES Ask", "NO Ask", "Raw Edge%", "Net Edge%", "Net PnL", "Size $", "Fill%"]
        trade_df["Net PnL"] = trade_df["Net PnL"].map("${:.2f}".format)
        trade_df["Size $"] = trade_df["Size $"].map("${:.0f}".format)
        trade_df["Fill%"] = trade_df["Fill%"].map("{:.0f}%".format)
        st.dataframe(trade_df, use_container_width=True, height=250)

    if len(st.session_state.pnl_series) >= 2:
        st.markdown("### 📈 Cumulative Simulated P&L")
        pnl_df = pd.DataFrame(st.session_state.pnl_series)
        pnl_df["idx"] = range(len(pnl_df))
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=pnl_df["idx"],
                y=pnl_df["cumulative_pnl"],
                mode="lines+markers",
                line=dict(color="#00ff88", width=2),
                marker=dict(size=4, color="#00ff88"),
                fill="tozeroy",
                fillcolor="rgba(0,255,136,0.06)",
                name="Cum. PnL",
            )
        )
        fig.add_hline(y=0, line_dash="dash", line_color="#7d8590", line_width=1)
        fig.update_layout(
            paper_bgcolor="#090c10",
            plot_bgcolor="#0d1117",
            font=dict(family="JetBrains Mono", color="#7d8590", size=11),
            xaxis=dict(title="Trade #", gridcolor="#161b22", zeroline=False),
            yaxis=dict(title="Cumulative PnL ($)", gridcolor="#161b22", zeroline=False),
            margin=dict(l=40, r=20, t=20, b=40),
            showlegend=False,
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 🗒 Activity Log")
    if st.session_state.logs:
        log_html = ""
        for entry in list(st.session_state.logs)[:20]:
            css = "log-entry"
            if entry["level"] == "arb":
                css += " arb"
            elif entry["level"] == "warn":
                css += " warn"
            elif entry["level"] == "err":
                css += " err"
            log_html += f'<div class="{css}">[{entry["ts"]}] {entry["msg"]}</div>'
        st.markdown(log_html, unsafe_allow_html=True)
    else:
        st.caption("Log will appear here once scanning starts.")

# ══════════════════════════════════════════════════════
# TAB 2 — THEORY & INVARIANT
# ══════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("## 📐 The $1.00 Invariant & Arbitrage Mathematics")

    st.markdown(
        """
    <div class="formula-box">
    <strong style="color:#00ff88; font-family: Syne;">The Core Principle</strong><br><br>
    Polymarket markets are implemented as <strong>ERC-1155 tokens on Polygon</strong>, backed by 
    the Conditional Tokens Framework (CTF). At resolution, the winning outcome token redeems 
    to <code>$1.00</code>; all losing tokens redeem to <code>$0.00</code>.
    </div>
    """,
        unsafe_allow_html=True,
    )

    st.markdown("### The Key Invariant")
    st.latex(r"1 \text{ YES token} + 1 \text{ NO token} \xrightarrow{\text{merge}} \approx \$1.00 \text{ collateral}")

    st.markdown(
        """
    A **full set** (one token of every outcome) can always be merged back into ~$1.00 of collateral.
    This creates a structural arbitrage when prices diverge:
    """
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
        <div class="formula-box">
        <strong style="color:#0ea5e9;">Long Arbitrage (Buy Both Sides)</strong><br>
        Triggered when total cost of a full set &lt; $1.00
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.latex(r"\text{Cost} = P_{\text{YES}}^{\text{ask}} + P_{\text{NO}}^{\text{ask}}")
        st.latex(r"\text{long\_edge} = 1.0 - (P_{\text{YES}} + P_{\text{NO}})")
        st.markdown("*Example: YES $0.60 + NO $0.38 = $0.98 → edge = $0.02 pre-fee*")

    with col2:
        st.markdown(
            """
        <div class="formula-box">
        <strong style="color:#f59e0b;">Short Arbitrage (Sell Both Sides)</strong><br>
        Triggered when combined sell revenue &gt; $1.00
        </div>
        """,
            unsafe_allow_html=True,
        )
        st.latex(r"\text{Revenue} = P_{\text{YES}}^{\text{bid}} + P_{\text{NO}}^{\text{bid}}")
        st.latex(r"\text{short\_edge} = (P_{\text{YES}}^{\text{bid}} + P_{\text{NO}}^{\text{bid}}) - 1.0")
        st.markdown("*Requires holding both YES and NO positions*")

    st.markdown("---")
    st.markdown("### Full Cost Model (What the Threshold Really Means)")
    st.markdown(
        """
    The article emphasizes: **arbitrage lives or dies on 5–50 basis points**. 
    The full fee-adjusted edge formula is:
    """
    )
    st.latex(r"\text{edge} = 1.0 - (P_{\text{YES}}^{\text{buy}} + P_{\text{NO}}^{\text{buy}}) - f_{\text{clob}} - g_{\text{merge}} - s_{\text{spread}} - b")

    param_data = {
        "Parameter": ["$P_{YES}^{buy} + P_{NO}^{buy}$", "$f_{clob}$", "$g_{merge}$", "$s_{spread}$", "$b$"],
        "Symbol": ["Total buy cost", "CLOB fees (both legs)", "Gas for on-chain merge", "Swap spread (USDC↔USDC.e)", "Safety buffer"],
        "Typical Value": ["0.97–0.998", "~0.075% × 2", "$0.30–$1.00", "~0.02%", "10–20 bps"],
    }
    st.table(pd.DataFrame(param_data))

    st.warning(
        """
    ⚠️ **Critical**: The edge computed is **pre-fee** by default. In production, subtract CLOB fees, 
    merge gas, swap spread, and keep a safety buffer for slippage/partial fills.  
    Also, merge size = min(filled_YES, filled_NO) — not the intended order size.
    """
    )

    st.markdown("---")
    st.markdown("### Interactive Edge Calculator")

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        calc_yes = st.slider("YES Ask Price", 0.01, 0.99, 0.48, 0.01)
    with cc2:
        calc_no = st.slider("NO Ask Price", 0.01, 0.99, 0.51, 0.01)
    with cc3:
        calc_size = st.number_input("Trade Size ($)", 100, 10000, 1000, 100)

    raw_e, net_e = compute_edge(
        calc_yes,
        calc_no,
        clob_fee=st.session_state.clob_fee_pct / 100,
        gas_usd=st.session_state.gas_merge_usd,
        swap_spread=st.session_state.swap_spread_pct / 100,
        buffer_bps=st.session_state.buffer_bps,
        trade_size_usd=calc_size,
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.metric("Total Cost", f"${calc_yes + calc_no:.4f}", delta=f"{calc_yes+calc_no-1:.4f} vs $1")
    with mc2:
        st.metric("Raw Edge", f"{raw_e*100:.2f}%", delta=f"{raw_e*100:.2f} bps")
    with mc3:
        st.metric("Net Edge (after fees)", f"{net_e*100:.2f}%")
    with mc4:
        gross_profit = raw_e * calc_size
        net_profit = net_e * calc_size
        st.metric("Est. Net Profit", f"${net_profit:.2f}", delta=f"Gross: ${gross_profit:.2f}")

    if net_e > st.session_state.profit_threshold_bps / 10000:
        st.success(
            f"✅ OPPORTUNITY DETECTED — Net edge {net_e*100:.2f}% exceeds threshold {st.session_state.profit_threshold_bps}bps"
        )
    elif raw_e > 0:
        st.warning(f"⚠️ Raw edge exists but fees consume it. Need {st.session_state.profit_threshold_bps}bps net.")
    else:
        st.error("❌ No arbitrage opportunity at current prices.")

# ══════════════════════════════════════════════════════
# TAB 3 — ANALYTICS & BACKTEST
# ══════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("## 📊 Analytics & Session Performance")

    if not st.session_state.trade_history:
        st.info("No trades yet. Start the scanner to generate data.")
    else:
        trades = st.session_state.trade_history
        pnls = [t["net_pnl"] for t in trades]
        edges = [t["net_edge_pct"] for t in trades]

        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(pnls) * 100 if pnls else 0
        avg_pnl = np.mean(pnls) if pnls else 0
        std_pnl = np.std(pnls) if len(pnls) > 1 else 0
        sharpe = (avg_pnl / std_pnl * np.sqrt(252)) if std_pnl > 0 else 0
        total = sum(pnls)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Trades", len(pnls))
        c2.metric("Win Rate", f"{win_rate:.1f}%")
        c3.metric("Avg PnL / Trade", f"${avg_pnl:.2f}")
        c4.metric("Session PnL", f"${total:.2f}")
        c5.metric("Sharpe (annl.)", f"{sharpe:.2f}")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown("#### Edge Distribution")
            edge_df = pd.DataFrame({"Net Edge (%)": edges})
            fig_hist = px.histogram(edge_df, x="Net Edge (%)", nbins=20, color_discrete_sequence=["#00ff88"])
            fig_hist.add_vline(
                x=st.session_state.profit_threshold_bps / 100,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="Threshold",
                annotation_font_color="#f59e0b",
            )
            fig_hist.update_layout(
                paper_bgcolor="#090c10",
                plot_bgcolor="#0d1117",
                font=dict(family="JetBrains Mono", color="#7d8590", size=11),
                margin=dict(l=30, r=10, t=30, b=30),
                height=280,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_b:
            st.markdown("#### Trade PnL Distribution")
            pnl_df2 = pd.DataFrame({"PnL ($)": pnls})
            fig_pnl = px.histogram(pnl_df2, x="PnL ($)", nbins=20, color_discrete_sequence=["#0ea5e9"])
            fig_pnl.add_vline(x=0, line_dash="dash", line_color="#ff4444")
            fig_pnl.update_layout(
                paper_bgcolor="#090c10",
                plot_bgcolor="#0d1117",
                font=dict(family="JetBrains Mono", color="#7d8590", size=11),
                margin=dict(l=30, r=10, t=30, b=30),
                height=280,
            )
            st.plotly_chart(fig_pnl, use_container_width=True)

    st.markdown("---")
    st.markdown("## 🔬 Parameter Sweep")
    st.markdown("Simulate performance across different threshold settings using current session data or synthetic runs.")

    sw1, sw2, sw3 = st.columns(3)
    with sw1:
        sweep_runs = st.slider("Synthetic runs per threshold", 10, 200, 50)
    with sw2:
        sweep_min = st.slider("Threshold min (bps)", 5, 50, 10)
    with sw3:
        sweep_max = st.slider("Threshold max (bps)", 20, 200, 100)

    if st.button("🔬 Run Parameter Sweep"):
        thresholds = np.linspace(sweep_min, sweep_max, 15)
        sweep_results = []

        for thr_bps in thresholds:
            thr = thr_bps / 10000
            total_p = 0
            n_trades = 0
            wins_s = 0
            for _ in range(sweep_runs):
                markets = generate_synthetic_markets(5)
                for m in markets:
                    by = m["_synth_yes_ask"] + random.gauss(0, 0.01)
                    bn = m["_synth_no_ask"] + random.gauss(0, 0.01)
                    _, net = compute_edge(
                        by,
                        bn,
                        clob_fee=st.session_state.clob_fee_pct / 100,
                        gas_usd=st.session_state.gas_merge_usd,
                        swap_spread=st.session_state.swap_spread_pct / 100,
                        buffer_bps=st.session_state.buffer_bps,
                        trade_size_usd=st.session_state.min_trade_usd,
                    )
                    if net > thr:
                        res = simulate_execution(
                            by,
                            bn,
                            net,
                            {**DEFAULT_PARAMS, **{k: st.session_state[k] for k in DEFAULT_PARAMS}},
                        )
                        if res:
                            total_p += res["net_pnl"]
                            n_trades += 1
                            if res["net_pnl"] > 0:
                                wins_s += 1

            sweep_results.append(
                {
                    "Threshold (bps)": float(thr_bps),
                    "Trades": int(n_trades),
                    "Total PnL ($)": round(float(total_p), 2),
                    "Win Rate": round(wins_s / n_trades * 100, 1) if n_trades else 0,
                    "Avg PnL": round(total_p / n_trades, 3) if n_trades else 0,
                }
            )

        sw_df = pd.DataFrame(sweep_results)
        st.dataframe(sw_df, use_container_width=True)

        fig_sw = go.Figure()
        fig_sw.add_trace(
            go.Scatter(
                x=sw_df["Threshold (bps)"],
                y=sw_df["Total PnL ($)"],
                mode="lines+markers",
                name="Total PnL",
                line=dict(color="#00ff88", width=2),
                marker=dict(size=6),
            )
        )
        fig_sw.add_trace(
            go.Scatter(
                x=sw_df["Threshold (bps)"],
                y=sw_df["Trades"],
                mode="lines+markers",
                name="# Trades",
                line=dict(color="#0ea5e9", width=2),
                marker=dict(size=6),
                yaxis="y2",
            )
        )
        fig_sw.update_layout(
            paper_bgcolor="#090c10",
            plot_bgcolor="#0d1117",
            font=dict(family="JetBrains Mono", color="#7d8590"),
            xaxis=dict(title="Threshold (bps)", gridcolor="#161b22"),
            yaxis=dict(title="Total PnL ($)", gridcolor="#161b22", titlefont_color="#00ff88"),
            yaxis2=dict(title="# Trades", overlaying="y", side="right", titlefont_color="#0ea5e9"),
            legend=dict(bgcolor="#0d1117", bordercolor="#21262d"),
            margin=dict(l=40, r=60, t=20, b=40),
            height=320,
        )
        st.plotly_chart(fig_sw, use_container_width=True)

# ══════════════════════════════════════════════════════
# TAB 4 — CODE REFERENCE
# ══════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("## 🧑‍💻 Reference Implementation")
    st.markdown(
        """
    Adapted from Jakub's ArbitrageStrategy — using **public REST endpoints** instead of WebSockets.
    This simulator uses anonymous `requests.get()` calls to Gamma API + CLOB API.
    """
    )

    with st.expander("📦 Public API Fetching (No Auth Required)"):
        st.code(
            """
import requests

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API  = "https://clob.polymarket.com"

# Fetch markets (public, no key)
def fetch_markets(min_volume=100_000, limit=20):
    r = requests.get(f"{GAMMA_API}/markets", params={
        "active": "true",
        "closed": "false",
        "limit": limit,
        "order": "volume",
        "ascending": "false",
    }, timeout=10)
    data = r.json()
    binary = [m for m in data
              if len(m.get("outcomes",[])) == 2
              and len(m.get("clobTokenIds",[])) == 2
              and float(m.get("volume",0)) >= min_volume]
    return binary

# Fetch order book for a token (public, no key)
def fetch_orderbook(token_id: str):
    r = requests.get(f"{CLOB_API}/book",
                     params={"token_id": token_id}, timeout=6)
    return r.json()  # {"bids": [...], "asks": [...]}
            """,
            language="python",
        )

    st.markdown("---")
    st.markdown(
        """
    <div style='font-family: JetBrains Mono; font-size: 0.72rem; color: #7d8590; text-align: center;
                padding: 1rem; border-top: 1px solid #21262d; margin-top: 1rem;'>
    Uses public Gamma + CLOB read endpoints — no keys, no trading, simulation/paper only<br>
    Educational & profitability testing · Based on Jakub's Polymarket Trading Framework (2026)<br>
    <span style='color: #21262d;'>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</span>
    </div>
    """,
        unsafe_allow_html=True,
    )
