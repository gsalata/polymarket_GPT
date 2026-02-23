"""
Polymarket 5-Minute Crypto Market Bot
Monitors BTC/ETH/SOL/XRP up-or-down 5-minute markets with three strategies:
  1. Long Arbitrage  — buy YES + NO for total < 1.0 - fees
  2. Last-15s Snipe  — buy highest-probability side in final 15 seconds
  3. Mispriced Order — find order-book outliers far below cluster price

Public APIs only — no authentication, no live trading. Pure paper simulation.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
import time
import json
import random
from collections import deque
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto 5M Bot",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
# DARK THEME CSS
# ─────────────────────────────────────────────
st.markdown("""
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
    --purple: #a78bfa;
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
.metric-val.purple { color: var(--purple); }

.metric-label {
    font-size: 0.7rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
}

.crypto-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 0.6rem;
}

.crypto-card.alert-arb { border-color: #00ff88; box-shadow: 0 0 12px rgba(0,255,136,0.2); }
.crypto-card.alert-snipe { border-color: #f59e0b; box-shadow: 0 0 12px rgba(245,158,11,0.2); }
.crypto-card.alert-mispriced { border-color: #a78bfa; box-shadow: 0 0 12px rgba(167,139,250,0.2); }

.crypto-name {
    font-family: 'Syne', sans-serif;
    font-size: 1.4rem;
    font-weight: 800;
    letter-spacing: 0.05em;
}

.countdown {
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.1rem;
    font-weight: 700;
}

.countdown.urgent { color: var(--danger); animation: pulse 1s infinite; }
.countdown.warn { color: var(--warn); }
.countdown.ok { color: var(--accent); }

.ob-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
    margin: 1px 0;
}

.ob-ask { background: rgba(255,68,68,0.08); border-left: 2px solid rgba(255,68,68,0.4); }
.ob-bid { background: rgba(0,255,136,0.08); border-left: 2px solid rgba(0,255,136,0.4); }
.ob-mispriced { background: rgba(167,139,250,0.2); border-left: 3px solid #a78bfa; font-weight: 700; }

.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 99px;
    font-size: 0.65rem;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.badge-arb { background: rgba(0,255,136,0.15); color: #00ff88; border: 1px solid rgba(0,255,136,0.3); }
.badge-snipe { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.badge-mispriced { background: rgba(167,139,250,0.15); color: #a78bfa; border: 1px solid rgba(167,139,250,0.3); }
.badge-exec { background: rgba(14,165,233,0.15); color: #0ea5e9; border: 1px solid rgba(14,165,233,0.3); }
.badge-cold { background: rgba(125,133,144,0.1); color: #7d8590; border: 1px solid rgba(125,133,144,0.2); }

.log-entry {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    padding: 4px 8px;
    border-left: 2px solid var(--border);
    margin: 2px 0;
    color: var(--muted);
}

.log-entry.arb { border-color: var(--accent); color: var(--text); }
.log-entry.snipe { border-color: var(--warn); color: var(--text); }
.log-entry.mispriced { border-color: var(--purple); color: var(--text); }
.log-entry.warn { border-color: var(--warn); }
.log-entry.err { border-color: var(--danger); }

.hero-title {
    font-family: 'Syne', sans-serif;
    font-size: 2.2rem;
    font-weight: 800;
    background: linear-gradient(135deg, #00ff88 0%, #0ea5e9 50%, #a78bfa 100%);
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
.dot-yellow { background: var(--warn); box-shadow: 0 0 8px var(--warn); animation: pulse 1s infinite; }
.dot-red { background: var(--danger); }
.dot-gray { background: var(--muted); }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
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

.formula-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent2);
    border-radius: 6px;
    padding: 1.2rem 1.5rem;
    margin: 1rem 0;
}

[data-testid="stMetric"] {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.8rem 1rem;
}

hr { border-color: var(--border) !important; }

div[data-testid="stExpander"] {
    background: var(--surface2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
}

.period-bar {
    height: 6px;
    border-radius: 3px;
    background: var(--border);
    overflow: hidden;
    margin: 4px 0;
}

.period-fill {
    height: 100%;
    border-radius: 3px;
    background: linear-gradient(90deg, #00ff88, #0ea5e9);
    transition: width 0.5s ease;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Known 5-minute crypto market prefixes (slug pattern: {PREFIX}-updown-5m-{start_ts})
CRYPTO_MARKETS = {
    "BTC": {"prefix": "btc", "emoji": "₿", "color": "#f59e0b"},
    "ETH": {"prefix": "eth", "emoji": "Ξ", "color": "#0ea5e9"},
    "SOL": {"prefix": "sol", "emoji": "◎", "color": "#a78bfa"},
    "XRP": {"prefix": "xrp", "emoji": "✕", "color": "#00ff88"},
}

PERIOD_SECS = 300  # 5-minute markets

# Strategy defaults
DEFAULT_PARAMS = {
    # Cost model
    "clob_fee_pct":      0.00075,   # 0.075% per leg
    "gas_merge_usd":     0.50,      # merge gas cost
    "swap_spread_pct":   0.0002,    # USDC swap spread
    "buffer_bps":        10,        # safety buffer bps
    # Thresholds
    "arb_threshold_bps": 20,        # min net edge for arb strategy (bps)
    "snipe_threshold":   0.05,      # min edge for last-15s snipe (per share)
    "mispriced_ratio":   0.50,      # ask must be ≤ this fraction of cluster to flag
    "mispriced_min_size":10.0,      # min order size to flag (USD)
    # Execution simulation
    "min_trade_usd":     50.0,
    "max_trade_usd":     2000.0,
    "slippage_pct":      0.3,
    # Monitor
    "refresh_interval":  3,         # seconds between scans
    "last_15s_window":   15,        # seconds before close to activate snipe
}


# ─────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────
def init_state():
    defaults = {
        "running": False,
        "market_data": {},          # crypto -> full market data dict
        "orderbooks": {},           # crypto -> {yes: ob, no: ob}
        "opportunities": deque(maxlen=200),
        "trade_history": [],
        "pnl_series": [],
        "logs": deque(maxlen=200),
        "total_pnl": 0.0,
        "total_trades": 0,
        "total_opps": 0,
        "session_start": time.time(),
        "last_scan_ts": 0.0,
        "current_period_start": 0,  # the start_ts being monitored
        "period_transitions": 0,    # how many 5-min periods have been tracked
        "strategy_stats": {
            "arb": {"opps": 0, "trades": 0, "pnl": 0.0},
            "snipe": {"opps": 0, "trades": 0, "pnl": 0.0},
            "mispriced": {"opps": 0, "trades": 0, "pnl": 0.0},
        },
        **DEFAULT_PARAMS,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# ─────────────────────────────────────────────
# TIME HELPERS
# ─────────────────────────────────────────────
def get_period_start(ts: float | None = None) -> int:
    """Returns the start UNIX timestamp of the current 5-min period."""
    t = int(ts if ts is not None else time.time())
    return (t // PERIOD_SECS) * PERIOD_SECS


def get_period_end(start_ts: int) -> int:
    return start_ts + PERIOD_SECS


def time_left_in_period(start_ts: int) -> float:
    """Seconds remaining until the current period ends."""
    end_ts = get_period_end(start_ts)
    return max(0.0, end_ts - time.time())


def format_countdown(secs: float) -> str:
    s = int(secs)
    return f"{s // 60}:{s % 60:02d}"


def period_elapsed_frac(start_ts: int) -> float:
    """0.0 = just started, 1.0 = closed."""
    elapsed = time.time() - start_ts
    return min(1.0, max(0.0, elapsed / PERIOD_SECS))


def get_slug(prefix: str, start_ts: int) -> str:
    return f"{prefix}-updown-5m-{start_ts}"


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
def log(msg: str, level: str = "info"):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.logs.appendleft({"ts": ts, "msg": msg, "level": level})


# ─────────────────────────────────────────────
# API HELPERS
# ─────────────────────────────────────────────
def _http_get(url: str, params=None, timeout=8, retries=3):
    """GET with exponential back-off on 429."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.3))
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            if attempt == retries - 1:
                raise
            time.sleep(0.5)
    return None


def fetch_5m_market(prefix: str, start_ts: int) -> dict | None:
    """Fetch market metadata from Gamma for a specific 5-min market."""
    slug = get_slug(prefix, start_ts)
    try:
        r = _http_get(f"{GAMMA_API}/markets", params={"slug": slug}, timeout=8)
        if not r:
            return None
        data = r.json()
        if not data:
            return None
        m = data[0] if isinstance(data, list) else data

        outcomes = m.get("outcomes", [])
        clob_ids = m.get("clobTokenIds", [])
        if not isinstance(outcomes, list):
            outcomes = json.loads(outcomes)
        if not isinstance(clob_ids, list):
            clob_ids = json.loads(clob_ids)

        if len(outcomes) != 2 or len(clob_ids) != 2:
            return None

        prices = m.get("outcomePrices", "[]")
        if not isinstance(prices, list):
            prices = json.loads(prices)

        return {
            "slug":       slug,
            "prefix":     prefix,
            "question":   m.get("question", slug),
            "yes_token":  clob_ids[0],
            "no_token":   clob_ids[1],
            "end_date":   m.get("endDate", ""),
            "active":     m.get("active", False),
            "closed":     m.get("closed", False),
            "yes_price":  float(prices[0]) if prices else 0.5,
            "no_price":   float(prices[1]) if len(prices) > 1 else 0.5,
            "volume":     float(m.get("volume", 0) or 0),
            "start_ts":   start_ts,
        }
    except Exception as e:
        log(f"[API] fetch market {slug}: {e}", "err")
        return None


def fetch_orderbook(token_id: str) -> dict | None:
    """Fetch CLOB order book for a token."""
    if not token_id:
        return None
    try:
        r = _http_get(f"{CLOB_API}/book", params={"token_id": token_id}, timeout=6)
        if not r:
            return None
        data = r.json() or {}
        asks = data.get("asks", data.get("sells", []))
        bids = data.get("bids", [])
        return {"asks": asks, "bids": bids}
    except Exception as e:
        log(f"[API] orderbook {token_id[:12]}…: {e}", "err")
        return None


def best_ask_price(ob: dict | None) -> float | None:
    """Cheapest available ask (minimum ask price)."""
    if not ob:
        return None
    asks = ob.get("asks", [])
    if not asks:
        return None
    try:
        return min(float(a["price"]) for a in asks)
    except Exception:
        return None


def best_bid_price(ob: dict | None) -> float | None:
    """Highest available bid (maximum bid price)."""
    if not ob:
        return None
    bids = ob.get("bids", [])
    if not bids:
        return None
    try:
        return max(float(b["price"]) for b in bids)
    except Exception:
        return None


def effective_buy_price(ob: dict | None) -> float | None:
    """
    Best price to BUY the token.
    Prefer best ask; fall back to 1 - best_bid of complement (not used here).
    """
    return best_ask_price(ob)


# ─────────────────────────────────────────────
# COST MODEL
# ─────────────────────────────────────────────
def total_fees(trade_size_usd: float, p: dict) -> float:
    """Total cost fractions for a single completed arb round-trip."""
    clob = p["clob_fee_pct"] * 2         # fee on YES leg + NO leg
    gas  = p["gas_merge_usd"] / trade_size_usd if trade_size_usd > 0 else 0
    swap = p["swap_spread_pct"] * 2
    buf  = p["buffer_bps"] / 10_000
    return clob + gas + swap + buf


def compute_arb_edge(yes_cost: float, no_cost: float, trade_size: float, p: dict):
    """
    Long arb edge:  net_edge = 1 - (yes_cost + no_cost) - total_fees
    Returns (raw_edge, net_edge).
    """
    raw  = 1.0 - (yes_cost + no_cost)
    fees = total_fees(trade_size, p)
    net  = raw - fees
    return raw, net


# ─────────────────────────────────────────────
# STRATEGY 1 — LONG ARBITRAGE
# ─────────────────────────────────────────────
def check_arb_strategy(crypto: str, yes_ob: dict, no_ob: dict, p: dict) -> dict | None:
    """Buy YES + NO for total < 1 - fees. Returns opportunity dict or None."""
    yes_ask = effective_buy_price(yes_ob)
    no_ask  = effective_buy_price(no_ob)

    if yes_ask is None or no_ask is None:
        return None
    if yes_ask <= 0 or no_ask <= 0:
        return None

    trade_size = (p["min_trade_usd"] + p["max_trade_usd"]) / 2
    raw_edge, net_edge = compute_arb_edge(yes_ask, no_ask, trade_size, p)
    threshold = p["arb_threshold_bps"] / 10_000

    if net_edge < threshold:
        return None

    return {
        "strategy":  "arb",
        "crypto":    crypto,
        "yes_price": yes_ask,
        "no_price":  no_ask,
        "total":     yes_ask + no_ask,
        "raw_edge":  raw_edge,
        "net_edge":  net_edge,
        "label":     f"ARB {crypto}: YES@{yes_ask:.3f} + NO@{no_ask:.3f} = {yes_ask+no_ask:.3f}",
    }


# ─────────────────────────────────────────────
# STRATEGY 2 — LAST-15s SNIPE
# ─────────────────────────────────────────────
def check_snipe_strategy(
    crypto: str, yes_ob: dict, no_ob: dict,
    time_left: float, p: dict
) -> dict | None:
    """
    In the last N seconds, the outcome is nearly determined.
    If best ask < (1.0 - fees), we can buy the winning side and profit at resolution.
    """
    window = p["last_15s_window"]
    if time_left > window:
        return None

    yes_ask = effective_buy_price(yes_ob)
    no_ask  = effective_buy_price(no_ob)

    candidates = []
    fees = p["clob_fee_pct"] + p["gas_merge_usd"] / p["max_trade_usd"] + p["swap_spread_pct"] + p["buffer_bps"] / 10_000

    if yes_ask is not None and yes_ask > 0:
        edge_yes = 1.0 - yes_ask - fees
        if edge_yes >= p["snipe_threshold"]:
            yes_bid = best_bid_price(yes_ob) or 0
            candidates.append({
                "token": "YES", "price": yes_ask,
                "edge": edge_yes, "confidence": yes_ask,
            })

    if no_ask is not None and no_ask > 0:
        edge_no = 1.0 - no_ask - fees
        if edge_no >= p["snipe_threshold"]:
            candidates.append({
                "token": "NO", "price": no_ask,
                "edge": edge_no, "confidence": no_ask,
            })

    if not candidates:
        return None

    # Pick the highest confidence (most likely to win) with positive edge
    best = max(candidates, key=lambda c: c["confidence"])

    return {
        "strategy":    "snipe",
        "crypto":      crypto,
        "token":       best["token"],
        "price":       best["price"],
        "edge":        best["edge"],
        "time_left":   time_left,
        "label": (
            f"SNIPE {crypto}: BUY {best['token']}@{best['price']:.3f} "
            f"({time_left:.0f}s left, edge={best['edge']*100:.1f}¢)"
        ),
    }


# ─────────────────────────────────────────────
# STRATEGY 3 — MISPRICED ORDERS
# ─────────────────────────────────────────────
def find_mispriced_orders(asks: list, ratio_threshold: float, min_size: float) -> list:
    """
    Scan an order book's asks for prices far below the cluster.
    Returns list of mispriced entries with discount info.

    Example: Most asks at 0.97, but 5 at 0.04 → flag those 0.04 asks.
    """
    if not asks or len(asks) < 2:
        return []

    try:
        entries = [(float(a["price"]), float(a["size"])) for a in asks]
    except Exception:
        return []

    prices = [e[0] for e in entries]
    sizes  = [e[1] for e in entries]

    # Cluster price = price level with highest total volume
    price_vol: dict[float, float] = {}
    for p, s in entries:
        price_vol[p] = price_vol.get(p, 0) + s

    cluster_price = max(price_vol, key=price_vol.get)

    # Only flag asks ≤ ratio_threshold * cluster_price
    mispriced = []
    for p_val, s_val in entries:
        if s_val < min_size:
            continue
        if p_val <= cluster_price * ratio_threshold and p_val < cluster_price - 0.10:
            discount = (cluster_price - p_val) / cluster_price
            est_profit = cluster_price - p_val  # conservative: sell at cluster
            mispriced.append({
                "price":         p_val,
                "size":          s_val,
                "cluster_price": cluster_price,
                "discount_pct":  discount * 100,
                "est_profit_per_share": est_profit,
            })

    return sorted(mispriced, key=lambda x: x["price"])


def check_mispriced_strategy(
    crypto: str, yes_ob: dict, no_ob: dict, p: dict
) -> list[dict]:
    """Check both YES and NO books for mispriced orders."""
    opps = []

    for token_label, ob in [("YES", yes_ob), ("NO", no_ob)]:
        if not ob:
            continue
        asks = ob.get("asks", [])
        mispx = find_mispriced_orders(asks, p["mispriced_ratio"], p["mispriced_min_size"])
        for m in mispx:
            opps.append({
                "strategy":    "mispriced",
                "crypto":      crypto,
                "token":       token_label,
                "price":       m["price"],
                "size":        m["size"],
                "cluster_price": m["cluster_price"],
                "discount_pct":  m["discount_pct"],
                "est_profit":    m["est_profit_per_share"],
                "label": (
                    f"MISPRICED {crypto} {token_label}@{m['price']:.3f} "
                    f"(cluster={m['cluster_price']:.3f}, "
                    f"discount={m['discount_pct']:.0f}%)"
                ),
            })

    return opps


# ─────────────────────────────────────────────
# EXECUTION SIMULATION
# ─────────────────────────────────────────────
def simulate_trade(opp: dict, p: dict) -> dict:
    """Simulate paper-trade execution for an opportunity."""
    slip   = random.uniform(0, p["slippage_pct"] / 100)
    fill   = random.uniform(0.75, 1.0)
    size   = random.uniform(p["min_trade_usd"], min(p["max_trade_usd"], 1500))

    if opp["strategy"] == "arb":
        cost_per = opp["yes_price"] + opp["no_price"] + slip
        if cost_per >= 1.0:
            return {"status": "rejected", "reason": "slippage killed edge"}
        shares   = (size * fill) / cost_per
        gross    = shares * (1.0 - cost_per)
        net      = gross - p["gas_merge_usd"]
        return {
            "status": "filled", "strategy": "arb",
            "crypto": opp["crypto"],
            "size_usd": size * fill,
            "shares": shares,
            "cost_per": cost_per,
            "gross_pnl": gross,
            "net_pnl": net,
            "edge_pct": opp["net_edge"] * 100,
        }

    elif opp["strategy"] == "snipe":
        cost = opp["price"] + slip
        if cost >= 1.0:
            return {"status": "rejected", "reason": "cost >= 1.0"}
        shares   = (size * fill) / cost
        gross    = shares * (1.0 - cost)
        net      = gross - p["gas_merge_usd"] / 2
        return {
            "status": "filled", "strategy": "snipe",
            "crypto": opp["crypto"], "token": opp["token"],
            "size_usd": size * fill,
            "shares": shares,
            "cost": cost,
            "gross_pnl": gross,
            "net_pnl": net,
            "edge_pct": opp["edge"] * 100,
        }

    elif opp["strategy"] == "mispriced":
        cost  = opp["price"] + slip
        avail = min(size * fill / cost, opp["size"])
        # Assume instant sell at cluster price (optimistic)
        gross = avail * (opp["cluster_price"] - cost)
        net   = gross - p["gas_merge_usd"] / 4
        return {
            "status": "filled", "strategy": "mispriced",
            "crypto": opp["crypto"], "token": opp["token"],
            "size_usd": avail * cost,
            "shares": avail,
            "buy_price": cost,
            "sell_price": opp["cluster_price"],
            "gross_pnl": gross,
            "net_pnl": net,
            "discount_pct": opp["discount_pct"],
        }

    return {"status": "unknown"}


# ─────────────────────────────────────────────
# MARKET DISCOVERY & ROTATION
# ─────────────────────────────────────────────
def refresh_market_data(period_start: int):
    """
    Fetch fresh metadata + order books for all 4 crypto markets in this period.
    Updates st.session_state.market_data and .orderbooks in place.
    """
    for sym, info in CRYPTO_MARKETS.items():
        md = fetch_5m_market(info["prefix"], period_start)
        if md:
            st.session_state.market_data[sym] = md
        else:
            # Market might not exist yet (transition window)
            if sym in st.session_state.market_data:
                st.session_state.market_data[sym]["closed"] = True

        time.sleep(0.15)  # gentle rate limiting

    # Fetch order books
    for sym in CRYPTO_MARKETS:
        md = st.session_state.market_data.get(sym)
        if not md:
            continue
        yes_ob = fetch_orderbook(md["yes_token"])
        time.sleep(0.1)
        no_ob  = fetch_orderbook(md["no_token"])
        time.sleep(0.1)
        st.session_state.orderbooks[sym] = {"yes": yes_ob, "no": no_ob}


def refresh_orderbooks_only():
    """Faster refresh — only update order books (not market metadata)."""
    for sym in CRYPTO_MARKETS:
        md = st.session_state.market_data.get(sym)
        if not md or md.get("closed"):
            continue
        yes_ob = fetch_orderbook(md["yes_token"])
        time.sleep(0.1)
        no_ob  = fetch_orderbook(md["no_token"])
        time.sleep(0.1)
        st.session_state.orderbooks[sym] = {"yes": yes_ob, "no": no_ob}


# ─────────────────────────────────────────────
# MAIN SCAN LOOP
# ─────────────────────────────────────────────
def run_scan():
    """
    Core scan: check period rotation, fetch data, run all 3 strategies,
    log opportunities, simulate trades.
    """
    p = {k: st.session_state[k] for k in DEFAULT_PARAMS}
    now_start = get_period_start()

    # --- Period rotation ---
    prev_start = st.session_state.current_period_start
    if now_start != prev_start:
        log(
            f"[PERIOD] New 5-min window: start={now_start} "
            f"({datetime.fromtimestamp(now_start, tz=timezone.utc).strftime('%H:%M')} UTC)",
            "arb",
        )
        st.session_state.current_period_start = now_start
        st.session_state.period_transitions += 1
        # Clear stale data
        st.session_state.market_data = {}
        st.session_state.orderbooks  = {}
        refresh_market_data(now_start)
    else:
        # Only refresh order books every cycle (faster)
        if not st.session_state.market_data:
            refresh_market_data(now_start)
        else:
            refresh_orderbooks_only()

    time_left = time_left_in_period(now_start)
    all_opps  = []

    # --- Run strategies for each market ---
    for sym in CRYPTO_MARKETS:
        ob = st.session_state.orderbooks.get(sym, {})
        yes_ob = ob.get("yes")
        no_ob  = ob.get("no")

        if not yes_ob and not no_ob:
            continue

        # Strategy 1: Long Arbitrage
        arb = check_arb_strategy(sym, yes_ob, no_ob, p)
        if arb:
            all_opps.append(arb)
            log(arb["label"], "arb")
            st.session_state.strategy_stats["arb"]["opps"] += 1

        # Strategy 2: Last-15s Snipe
        snipe = check_snipe_strategy(sym, yes_ob, no_ob, time_left, p)
        if snipe:
            all_opps.append(snipe)
            log(snipe["label"], "snipe")
            st.session_state.strategy_stats["snipe"]["opps"] += 1

        # Strategy 3: Mispriced Orders
        mispx = check_mispriced_strategy(sym, yes_ob, no_ob, p)
        for m in mispx:
            all_opps.append(m)
            log(m["label"], "mispriced")
            st.session_state.strategy_stats["mispriced"]["opps"] += 1

    # Update total opportunity count
    st.session_state.total_opps += len(all_opps)

    # --- Record opportunities & simulate trades ---
    for opp in all_opps:
        opp["ts"] = datetime.now().strftime("%H:%M:%S")
        opp["time_left"] = time_left
        st.session_state.opportunities.appendleft(opp)

        # Simulate execution
        result = simulate_trade(opp, p)
        if result.get("status") == "filled":
            result["ts"]     = opp["ts"]
            result["time_left"] = time_left
            pnl = result.get("net_pnl", 0)

            st.session_state.trade_history.append(result)
            st.session_state.total_trades += 1
            st.session_state.total_pnl    += pnl
            st.session_state.pnl_series.append({
                "ts":  result["ts"],
                "pnl": st.session_state.total_pnl,
            })

            strat = opp["strategy"]
            st.session_state.strategy_stats[strat]["trades"] += 1
            st.session_state.strategy_stats[strat]["pnl"]    += pnl

            log(
                f"[EXEC] {strat.upper()} {opp['crypto']} → PnL ${pnl:+.2f}",
                "arb" if pnl > 0 else "err",
            )

    st.session_state.last_scan_ts = time.time()


# ─────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────
def render_orderbook_html(ob: dict | None, token_label: str, max_rows=6) -> str:
    """Render a compact order book as HTML rows."""
    if not ob:
        return f'<div style="color:#7d8590;font-size:0.7rem">No {token_label} data</div>'

    asks = sorted(ob.get("asks", []), key=lambda x: float(x.get("price", 0)), reverse=True)
    bids = sorted(ob.get("bids", []), key=lambda x: float(x.get("price", 0)), reverse=True)

    # Mispriced detection for highlights
    mispriced_prices = set()
    if asks and len(asks) >= 2:
        all_prices = [float(a["price"]) for a in asks]
        all_sizes  = [float(a.get("size", 0)) for a in asks]
        if all_sizes:
            max_size = max(all_sizes)
            cluster  = all_prices[all_sizes.index(max_size)]
            for a in asks:
                if float(a["price"]) <= cluster * 0.50 and float(a["price"]) < cluster - 0.10:
                    mispriced_prices.add(float(a["price"]))

    html = f'<div style="font-size:0.65rem;color:#7d8590;margin-bottom:2px;font-family:\'JetBrains Mono\';">{token_label} ORDER BOOK</div>'

    # Asks (sell orders — red)
    for a in asks[:max_rows]:
        p_val = float(a.get("price", 0))
        s_val = float(a.get("size", 0))
        cls   = "ob-mispriced" if p_val in mispriced_prices else "ob-ask"
        star  = " ⚡" if p_val in mispriced_prices else ""
        bar_w = min(100, int(s_val / 500 * 100))
        html += (
            f'<div class="{cls} ob-row">'
            f'<span style="color:#ff4444">{p_val:.3f}{star}</span>'
            f'<span style="color:#7d8590">{s_val:,.0f}</span>'
            f'<div style="width:{bar_w}px;height:3px;background:rgba(255,68,68,0.4);border-radius:2px"></div>'
            f"</div>"
        )

    if asks and bids:
        html += '<div style="border-top:1px solid #21262d;margin:3px 0"></div>'

    # Bids (buy orders — green)
    for b in bids[:max_rows]:
        p_val = float(b.get("price", 0))
        s_val = float(b.get("size", 0))
        bar_w = min(100, int(s_val / 500 * 100))
        html += (
            f'<div class="ob-bid ob-row">'
            f'<span style="color:#00ff88">{p_val:.3f}</span>'
            f'<span style="color:#7d8590">{s_val:,.0f}</span>'
            f'<div style="width:{bar_w}px;height:3px;background:rgba(0,255,136,0.4);border-radius:2px"></div>'
            f"</div>"
        )

    return html


def countdown_class(secs: float) -> str:
    if secs <= 15:
        return "urgent"
    elif secs <= 60:
        return "warn"
    return "ok"


def pct_bar(frac: float, color: str = "#00ff88") -> str:
    pct = int(frac * 100)
    return (
        f'<div class="period-bar">'
        f'<div class="period-fill" style="width:{pct}%;background:{color}"></div>'
        f"</div>"
    )


# ─────────────────────────────────────────────
# ──  S I D E B A R  ──
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown('<p class="hero-title" style="font-size:1.4rem">🔮 Crypto 5M Bot</p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">5-min BTC/ETH/SOL/XRP markets</p>', unsafe_allow_html=True)
    st.markdown("---")

    # ── Start / Stop ──
    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶ Start" if not st.session_state.running else "⏸ Pause"):
            st.session_state.running = not st.session_state.running
            # On start, reset period so we fetch fresh data immediately
            if st.session_state.running:
                st.session_state.current_period_start = 0
            log("Scanner " + ("started" if st.session_state.running else "paused"))
    with col2:
        if st.button("↺ Reset"):
            for k in ["trade_history", "pnl_series", "total_pnl", "total_trades",
                      "total_opps", "logs", "opportunities", "market_data",
                      "orderbooks", "current_period_start", "period_transitions"]:
                if k in ["trade_history", "pnl_series"]:
                    st.session_state[k] = []
                elif k in ["total_pnl", "total_trades", "total_opps",
                           "current_period_start", "period_transitions"]:
                    st.session_state[k] = 0
                elif k in ["market_data", "orderbooks"]:
                    st.session_state[k] = {}
                elif k == "logs":
                    st.session_state[k] = deque(maxlen=200)
                elif k == "opportunities":
                    st.session_state[k] = deque(maxlen=200)
            st.session_state.strategy_stats = {
                "arb":       {"opps": 0, "trades": 0, "pnl": 0.0},
                "snipe":     {"opps": 0, "trades": 0, "pnl": 0.0},
                "mispriced": {"opps": 0, "trades": 0, "pnl": 0.0},
            }
            st.session_state.session_start = time.time()
            log("Session reset")
            st.rerun()

    st.markdown("---")

    # ── Strategy Toggles ──
    st.markdown("**🎯 Strategies**")
    st.session_state["arb_enabled"]       = st.checkbox("1 — Long Arbitrage (YES+NO < 1)", value=True)
    st.session_state["snipe_enabled"]     = st.checkbox("2 — Last-15s Snipe", value=True)
    st.session_state["mispriced_enabled"] = st.checkbox("3 — Mispriced Orders", value=True)

    st.markdown("---")

    # ── Refresh ──
    st.session_state.refresh_interval = st.slider(
        "Refresh interval (s)", 2, 30,
        int(st.session_state.refresh_interval), step=1
    )

    st.session_state.last_15s_window = st.slider(
        "Snipe window (s before close)", 5, 30,
        int(st.session_state.last_15s_window), step=1
    )

    st.markdown("---")

    # ── Cost Model ──
    with st.expander("⚙ Cost Model"):
        st.session_state.arb_threshold_bps = st.slider(
            "Min arb edge (bps)", 5, 100,
            int(st.session_state.arb_threshold_bps), step=5
        )
        st.session_state.snipe_threshold = st.slider(
            "Min snipe edge (¢)", 1, 20,
            int(st.session_state.snipe_threshold * 100), step=1
        ) / 100
        st.session_state.mispriced_ratio = st.slider(
            "Mispriced ratio (ask ≤ X × cluster)", 10, 70,
            int(st.session_state.mispriced_ratio * 100), step=5
        ) / 100
        st.session_state.mispriced_min_size = st.slider(
            "Mispriced min size ($)", 1, 100,
            int(st.session_state.mispriced_min_size), step=1
        )
        st.session_state.clob_fee_pct = st.number_input(
            "CLOB fee per leg", value=st.session_state.clob_fee_pct,
            format="%.5f", step=0.0001
        )
        st.session_state.gas_merge_usd = st.number_input(
            "Gas/merge cost (USD)", value=st.session_state.gas_merge_usd,
            format="%.2f", step=0.1
        )

    with st.expander("💰 Trade Size"):
        st.session_state.min_trade_usd = st.slider(
            "Min trade (USD)", 10, 500,
            int(st.session_state.min_trade_usd), step=10
        )
        st.session_state.max_trade_usd = st.slider(
            "Max trade (USD)", 100, 5000,
            int(st.session_state.max_trade_usd), step=100
        )
        st.session_state.slippage_pct = st.slider(
            "Slippage (%)", 0.0, 2.0,
            float(st.session_state.slippage_pct), step=0.1
        )

    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.65rem;color:#7d8590;font-family:\'JetBrains Mono\'">'
        'Public APIs only — no keys, no live trading.<br>'
        'Simulation only for educational use.</p>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────
# ──  M A I N   C O N T E N T  ──
# ─────────────────────────────────────────────

# Header
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.markdown('<h1 class="hero-title">🔮 Crypto 5-Minute Bot</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">BTC · ETH · SOL · XRP — up-or-down every 5 minutes</p>',
        unsafe_allow_html=True
    )
with col_h2:
    dot_color = "dot-green" if st.session_state.running else "dot-gray"
    status_txt = "SCANNING" if st.session_state.running else "PAUSED"
    st.markdown(
        f'<div style="text-align:right;padding-top:0.8rem;">'
        f'<span class="status-dot {dot_color}"></span>'
        f'<span style="font-family:\'JetBrains Mono\';font-size:0.8rem;color:#e6edf3">{status_txt}</span>'
        f'<br><span style="font-size:0.65rem;color:#7d8590">{utc_now_str()}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

# KPI row
now_start    = get_period_start()
t_left       = time_left_in_period(now_start)
elapsed_frac = period_elapsed_frac(now_start)
session_mins = (time.time() - st.session_state.session_start) / 60

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total PnL", f"${st.session_state.total_pnl:+.2f}")
k2.metric("Trades",    st.session_state.total_trades)
k3.metric("Opps Found", st.session_state.total_opps)
k4.metric("Periods",   st.session_state.period_transitions)
k5.metric("Time Left",  format_countdown(t_left))
k6.metric("Session",    f"{session_mins:.0f}m")

# Period progress bar
period_dt = datetime.fromtimestamp(now_start, tz=timezone.utc).strftime("%H:%M")
period_end_dt = datetime.fromtimestamp(now_start + PERIOD_SECS, tz=timezone.utc).strftime("%H:%M")
bar_color = "#ff4444" if t_left <= 15 else ("#f59e0b" if t_left <= 60 else "#00ff88")
st.markdown(
    f'<div style="margin:0.3rem 0;font-family:\'JetBrains Mono\';font-size:0.72rem;color:#7d8590">'
    f'Current period: {period_dt} → {period_end_dt} UTC &nbsp;|&nbsp; '
    f'<span class="countdown {countdown_class(t_left)}">{format_countdown(t_left)} remaining</span>'
    f'</div>'
    + pct_bar(elapsed_frac, bar_color),
    unsafe_allow_html=True
)

st.markdown("---")

# ── Tabs ──
tab_monitor, tab_opps, tab_history, tab_theory = st.tabs([
    "📡  Live Monitor",
    "⚡  Opportunities",
    "📋  Trade History",
    "📐  Theory",
])


# ─────────────────────────────────────────────
# TAB 1 — LIVE MONITOR
# ─────────────────────────────────────────────
with tab_monitor:
    st.markdown("#### Live Market Monitor — All 5-Minute Crypto Markets")
    st.markdown(
        '<p style="color:#7d8590;font-size:0.75rem;font-family:\'JetBrains Mono\'">'
        'Real-time order books for each market. ⚡ marks mispriced orders.</p>',
        unsafe_allow_html=True
    )

    cols = st.columns(len(CRYPTO_MARKETS))

    for col, (sym, info) in zip(cols, CRYPTO_MARKETS.items()):
        md  = st.session_state.market_data.get(sym, {})
        obs = st.session_state.orderbooks.get(sym, {})
        yes_ob = obs.get("yes")
        no_ob  = obs.get("no")

        yes_ask = best_ask_price(yes_ob)
        no_ask  = best_ask_price(no_ob)
        total   = (yes_ask or 0) + (no_ask or 0)

        # Determine alert class
        alert_cls = ""
        if yes_ask and no_ask:
            p_vals = {k: st.session_state[k] for k in DEFAULT_PARAMS}
            _, net_edge = compute_arb_edge(yes_ask, no_ask, 500, p_vals)
            if net_edge >= p_vals["arb_threshold_bps"] / 10_000:
                alert_cls = "alert-arb"
            elif t_left <= p_vals["last_15s_window"]:
                alert_cls = "alert-snipe"

        with col:
            color = info["color"]
            yes_price_disp = f"{yes_ask:.3f}" if yes_ask else "—"
            no_price_disp  = f"{no_ask:.3f}"  if no_ask  else "—"
            total_disp     = f"{total:.3f}"    if (yes_ask and no_ask) else "—"
            arb_disp = (
                f'<span style="color:#00ff88">ARB {((1-total)*100):.1f}¢</span>'
                if (yes_ask and no_ask and total < 0.99) else
                f'<span style="color:#7d8590">{total_disp}</span>'
            )

            st.markdown(
                f'<div class="crypto-card {alert_cls}">'
                f'<div class="crypto-name" style="color:{color}">{info["emoji"]} {sym}</div>'
                f'<div style="font-size:0.7rem;color:#7d8590;margin-bottom:0.5rem">'
                f'period {period_dt}→{period_end_dt}</div>'
                f'<table style="width:100%;font-family:\'JetBrains Mono\';font-size:0.75rem">'
                f'<tr><td style="color:#7d8590">YES ask</td>'
                f'<td style="text-align:right;color:#e6edf3">{yes_price_disp}</td></tr>'
                f'<tr><td style="color:#7d8590">NO ask</td>'
                f'<td style="text-align:right;color:#e6edf3">{no_price_disp}</td></tr>'
                f'<tr><td style="color:#7d8590">Total</td>'
                f'<td style="text-align:right">{arb_disp}</td></tr>'
                f'</table>'
                f'</div>',
                unsafe_allow_html=True
            )

            # Order books
            with st.expander(f"{sym} YES Book", expanded=False):
                st.markdown(render_orderbook_html(yes_ob, "YES"), unsafe_allow_html=True)
            with st.expander(f"{sym} NO Book", expanded=False):
                st.markdown(render_orderbook_html(no_ob, "NO"), unsafe_allow_html=True)

    st.markdown("---")

    # Activity log
    st.markdown("**Activity Log**")
    log_html = ""
    for entry in list(st.session_state.logs)[:30]:
        cls = entry.get("level", "info")
        log_html += (
            f'<div class="log-entry {cls}">'
            f'<span style="color:#7d8590">[{entry["ts"]}]</span> {entry["msg"]}'
            f'</div>'
        )
    st.markdown(log_html or '<div style="color:#7d8590">No log entries yet.</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────
# TAB 2 — OPPORTUNITIES
# ─────────────────────────────────────────────
with tab_opps:
    st.markdown("#### Detected Opportunities")

    # Strategy stats
    ss = st.session_state.strategy_stats
    sc1, sc2, sc3 = st.columns(3)

    with sc1:
        st.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:0.65rem;color:#7d8590;margin-bottom:4px">'
            f'<span class="badge badge-arb">LONG ARB</span></div>'
            f'<div class="metric-val">{ss["arb"]["opps"]}</div>'
            f'<div class="metric-label">opportunities</div>'
            f'<div style="font-size:0.75rem;color:#00ff88;margin-top:4px">'
            f'{ss["arb"]["trades"]} trades · ${ss["arb"]["pnl"]:+.2f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with sc2:
        st.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:0.65rem;color:#7d8590;margin-bottom:4px">'
            f'<span class="badge badge-snipe">LAST-15s SNIPE</span></div>'
            f'<div class="metric-val warn">{ss["snipe"]["opps"]}</div>'
            f'<div class="metric-label">opportunities</div>'
            f'<div style="font-size:0.75rem;color:#f59e0b;margin-top:4px">'
            f'{ss["snipe"]["trades"]} trades · ${ss["snipe"]["pnl"]:+.2f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    with sc3:
        st.markdown(
            f'<div class="metric-card">'
            f'<div style="font-size:0.65rem;color:#7d8590;margin-bottom:4px">'
            f'<span class="badge badge-mispriced">MISPRICED</span></div>'
            f'<div class="metric-val purple">{ss["mispriced"]["opps"]}</div>'
            f'<div class="metric-label">opportunities</div>'
            f'<div style="font-size:0.75rem;color:#a78bfa;margin-top:4px">'
            f'{ss["mispriced"]["trades"]} trades · ${ss["mispriced"]["pnl"]:+.2f}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Opportunity table
    opps_list = list(st.session_state.opportunities)
    if not opps_list:
        st.markdown('<p style="color:#7d8590;font-family:\'JetBrains Mono\'">No opportunities detected yet. Start the scanner.</p>', unsafe_allow_html=True)
    else:
        rows = []
        for opp in opps_list[:50]:
            strat = opp.get("strategy", "")
            badge = {
                "arb":       '<span class="badge badge-arb">ARB</span>',
                "snipe":     '<span class="badge badge-snipe">SNIPE</span>',
                "mispriced": '<span class="badge badge-mispriced">MISPRICED</span>',
            }.get(strat, "")

            row = {
                "Time":     opp.get("ts", ""),
                "Strategy": strat.upper(),
                "Crypto":   opp.get("crypto", ""),
                "Detail":   opp.get("label", "")[:70],
                "T-left(s)": f"{opp.get('time_left', 0):.0f}s",
            }
            if strat == "arb":
                row["Edge"] = f"{opp.get('net_edge', 0)*100:.2f}¢"
            elif strat == "snipe":
                row["Edge"] = f"{opp.get('edge', 0)*100:.1f}¢"
            elif strat == "mispriced":
                row["Edge"] = f"−{opp.get('discount_pct', 0):.0f}%"
            rows.append(row)

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────
# TAB 3 — TRADE HISTORY
# ─────────────────────────────────────────────
with tab_history:
    st.markdown("#### Paper Trade History")

    if not st.session_state.trade_history:
        st.markdown(
            '<p style="color:#7d8590;font-family:\'JetBrains Mono\'">No trades yet.</p>',
            unsafe_allow_html=True
        )
    else:
        # P&L chart
        if len(st.session_state.pnl_series) > 1:
            pnl_df = pd.DataFrame(st.session_state.pnl_series)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=pnl_df["ts"], y=pnl_df["pnl"],
                mode="lines", name="Cumulative PnL",
                line=dict(color="#00ff88", width=2),
                fill="tozeroy",
                fillcolor="rgba(0,255,136,0.05)",
            ))
            fig.update_layout(
                paper_bgcolor="#090c10", plot_bgcolor="#0d1117",
                font=dict(color="#e6edf3", family="JetBrains Mono"),
                height=220, margin=dict(l=40, r=10, t=30, b=30),
                xaxis=dict(showgrid=False, color="#7d8590"),
                yaxis=dict(gridcolor="#21262d", color="#7d8590", tickprefix="$"),
                title=dict(text="Cumulative PnL", font=dict(color="#e6edf3", size=13)),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Trade table
        trades_df = pd.DataFrame([
            {
                "Time":        t.get("ts", ""),
                "Strategy":    t.get("strategy", "").upper(),
                "Crypto":      t.get("crypto", ""),
                "Token":       t.get("token", "PAIR"),
                "Size($)":     f"{t.get('size_usd', 0):.0f}",
                "Net PnL($)":  f"{t.get('net_pnl', 0):+.3f}",
                "T-left":      f"{t.get('time_left', 0):.0f}s",
            }
            for t in reversed(st.session_state.trade_history[-100:])
        ])
        st.dataframe(trades_df, use_container_width=True, hide_index=True)

        # Per-strategy breakdown
        st.markdown("**Strategy Breakdown**")
        bc1, bc2, bc3 = st.columns(3)
        strategies = [
            ("arb",       "#00ff88", "Long Arb"),
            ("snipe",     "#f59e0b", "Last-15s Snipe"),
            ("mispriced", "#a78bfa", "Mispriced"),
        ]
        for col, (strat, color, label) in zip([bc1, bc2, bc3], strategies):
            strat_trades = [t for t in st.session_state.trade_history if t.get("strategy") == strat]
            s_pnl  = sum(t.get("net_pnl", 0) for t in strat_trades)
            s_wins = sum(1 for t in strat_trades if t.get("net_pnl", 0) > 0)
            s_n    = len(strat_trades)
            wr     = (s_wins / s_n * 100) if s_n > 0 else 0
            col.metric(label, f"${s_pnl:+.2f}", f"{s_n} trades, {wr:.0f}% win")


# ─────────────────────────────────────────────
# TAB 4 — THEORY
# ─────────────────────────────────────────────
with tab_theory:
    st.markdown("""
## How the 5-Minute Crypto Bot Works

### Market Structure

Polymarket creates a new **up-or-down** binary market for BTC, ETH, SOL, and XRP every
5 minutes.  Each market has exactly two outcomes:

| Token | Resolves to $1.00 if… | Resolves to $0.00 if… |
|-------|------------------------|------------------------|
| **YES** | crypto price is higher at close | crypto price is same or lower |
| **NO**  | crypto price is same/lower at close | crypto price is higher |

Markets are named `{crypto}-updown-5m-{start_unix_timestamp}` where the timestamp is
the UNIX epoch at which the 5-minute window **opens**.

### Market Discovery Algorithm

```python
import time

def get_current_slug(crypto_prefix):
    # Floor current timestamp to nearest 5-minute boundary
    start_ts = (int(time.time()) // 300) * 300
    return f"{crypto_prefix}-updown-5m-{start_ts}"

# Next market = start_ts + 300 (5 minutes)
def get_next_slug(crypto_prefix, current_start_ts):
    return f"{crypto_prefix}-updown-5m-{current_start_ts + 300}"
```

The bot continuously monitors the current period and **auto-rotates** when a new
5-minute boundary is crossed.

---

### Strategy 1 — Long Arbitrage

The $1.00 invariant: `1 YES + 1 NO = $1.00` at resolution.

If you can buy both sides for less than $1.00 minus all costs, you lock in risk-free profit:

```
net_edge = 1.0 - (best_YES_ask + best_NO_ask) - total_fees
total_fees = CLOB_fee×2 + gas/trade_size + swap_spread + safety_buffer
```

**Example**: YES ask = 0.48, NO ask = 0.49, total = 0.97.
With fees ~0.003, net_edge ≈ 0.027 (2.7 cents per $1 invested).

---

### Strategy 2 — Last-15s Snipe

In the final 15 seconds, the outcome is nearly certain (price is 90%+).
If someone left a stale limit order at a discount, you can buy the winning side cheaply:

```
edge = 1.0 - best_ask_of_likely_winner - fees
```

**Example**: BTC is clearly up (+1.8% in the 5-min window). YES asks at 0.94.
Edge = 1.0 - 0.94 - 0.003 ≈ 5.7 cents profit per share at resolution.

---

### Strategy 3 — Mispriced Order Detection

Scan the entire order book for asks far below the cluster:

```
cluster_price = price level with maximum total volume
flag if: ask_price ≤ cluster_price × mispriced_ratio
         AND ask_size ≥ minimum_size
```

**Example**: NO asks cluster at $0.33 (YES at 67%).
One seller placed a NO ask at $0.04 (error or stale order).
Buy it at $0.04; fair value is $0.33 → instant profit of $0.29/share.

---

### Cost Model

| Component | Value | Notes |
|-----------|-------|-------|
| CLOB fee | 0.075% per leg | Charged on each buy |
| Gas/merge | $0.50 flat | On-chain bundle merge |
| Swap spread | 0.02% | USDC↔USDC.e conversion |
| Safety buffer | 10 bps | Slippage cushion |
| **Total** | ~0.3% + $0.50 | Scales with trade size |

""")


# ─────────────────────────────────────────────
# ──  S C A N   L O O P  ──
# ─────────────────────────────────────────────
if st.session_state.running:
    run_scan()
    interval = int(st.session_state.refresh_interval)
    time.sleep(interval)
    st.rerun()
elif not st.session_state.market_data:
    # Even when paused, pre-load market data once for the monitor view
    period_start = get_period_start()
    if period_start != st.session_state.current_period_start:
        st.session_state.current_period_start = period_start
        with st.spinner("Loading market data…"):
            refresh_market_data(period_start)
        st.rerun()
