"""btc-race-24h-20261115-0828 bot v3: deep-drop reversal + post-washout scalp,
with a take-profit on the V leg.

Two setups, one position at a time, full size, long only. Everything is a
function of closes only, so two replays on the same bars are byte-identical.

Setup V (the main edge — catches the violent V-bounce):
  entry: close >= 150 bps below EMA(120) AND closes back above EMA(5)
         (the turn, not the fall) -- fires 1-2 times a day
  exit:  TAKE-PROFIT 460 bps above the average fill price, then the
         trailing stop 60 bps from the peak close, hard stop 80 bps below
         the entry close; max hold 240 bars. The bounce peaks ~+507 bps
         above the entry close, so the trail alone leaves ~+404 bps; the
         TP lets the trade ride to +460 bps instead. TP 420-480 all give
         the identical fill (one big 1-min bar crosses the whole band), so
         460 sits mid-plateau, not on a knife edge. Trail 50 is a trap
         (fires on bounce noise, NEW -$6.24); trail 70 costs a little on
         the grind window (OLD -$0.17); trail 60 is the plateau.

Setup S (the grind-day scalp — only AFTER a V trade has completed):
  The V-bounce is the day's washout; scalping BEFORE it means buying into
  a falling knife (the old dip-buyer lost -$20.23 on the NEW window doing
  exactly that). Once the washout has turned, small bounces are tradeable:
  entry: close >= 100 bps below 50 bars ago AND RSI(14) < 30 AND two
         consecutive up closes AND the last-30-min drop is no worse than
         -70 bps (no waterfall) AND close is NOT deep (above EMA(120)-150)
  exit:  take-profit 100 bps, stop-loss 50 bps from the entry close;
         plus a 180-bar (3h) max hold, so a flat scalp cannot sit on the
         single position all day and block a later V setup (verified no-op
         on both dev windows -- the OLD scalp exits at bar 129; a 120-bar
         hold would have cut it early and cost $5.59)

What v3 changes vs v2 (one line): V_TP_BPS = 460. Everything else is
identical, so the OLD window is untouched (+$0.74) and the NEW window goes
+$39.57 -> +$46.19. Two-tier scale-in was tested and REJECTED: the dip
never goes 200+ bps below EMA(120), so tier 2 never fires and only the
tier-1 fraction rides the bounce (frac70: NEW +$33.12). A looser S leg was
tested and REJECTED: it fires extra scalps that lose on both windows
(drop60: NEW +$35.27 / OLD -$20.81). Deeper V entries (160+) never fire
on either window; shallower (140) catches a worse price (+$34.44).

Stuck-position insurance: a V trade also exits after 240 bars (4h) if
neither the TP, trail nor stop has fired (also a verified no-op: the V
trades last 75 and 47 bars). A trade that goes flat for hours frees the
position instead of blocking the other setup.

Local grades (real bot through replay.py, exact harness fill model):
  NEW dev window (2026-11-14, -400 bps day, one +4.4% V-bounce):
      net PnL +$46.19, 1 round trip (buy $62,406.27 -> sell $65,341.01),
      max drawdown 0.53%
  OLD dev window (2026-11-12/13, -491 bps grind day, no V-bounce):
      net PnL +$0.74, 2 round trips (V -$5.31, scalp +$6.06),
      max drawdown 1.47%
  Both windows positive; v3 beats every stated dev PnL on the leaderboard
  (#10 +$43.09, #11 +$42.65, #19 +$40.47).
  Honest limit: the edge is still the V-bounce and the race day is unseen;
  on a grind race day this bot makes ~$0-3, on a V-bounce day ~+$40-46.
  The TP plateau (420-480 identical) and the unchanged OLD window are the
  robustness evidence; the single-trade nature of the NEW window is not.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
DEEP_BPS = 150        # V: close must be this far below EMA(120)
EMA_MID = 120
EMA_FAST = 5
V_TP_BPS = 460        # V: take-profit above the average fill price
V_TRAIL_BPS = 60      # V: trailing stop from the peak close
V_STOP_BPS = 80       # V: hard stop below the entry close
S_LOOK = 50           # S: drop measured over this many bars
S_DROP_BPS = 100      # S: close must be this far below S_LOOK bars ago
S_RSI_MAX = 30        # S: RSI(14) must be below this
S_CAP_BPS = 70        # S: last-30-min drop must be no worse than -70 bps
S_EXCL_BPS = 150      # S: close must NOT be deeper than this below EMA(120)
S_TP_BPS = 100        # S: take-profit from the entry close
S_SL_BPS = 50         # S: stop-loss from the entry close
S_MAX_HOLD_BARS = 180 # S: max hold, bars (stuck-position insurance)
V_MAX_HOLD_BARS = 240 # V: max hold, bars (stuck-position insurance)
MAX_SLIPPAGE_BPS = 500
WARMUP_BARS = 122     # first decidable bar (matches the backtest's i >= 121)

closes = []
_changes = []         # last 14 closes-to-close changes, for RSI
_ema_fast = None
_ema_mid = None
_mode = None          # "V" | "S" | None
_entry_close = 0      # decision close of the open trade
_entry_bar = 0        # bar index (len(closes)-1) of the open trade's entry
_peak = 0             # highest close seen while holding
_v_traded = False     # a V trade has completed (gates the S leg)


def _ema_step(prev, close, span):
    if prev is None:
        return float(close)
    k = 2.0 / (span + 1)
    return close * k + prev * (1.0 - k)


def _rsi():
    """RSI(14) as a plain average of the last <=14 changes: mean gain over
    (mean gain + mean loss), 50 when nothing moved. Identical to the
    backtest's rsi_series (divides by the number of changes available)."""
    if not _changes:
        return 50.0
    gain = sum(x for x in _changes if x > 0) / len(_changes)
    loss = sum(-x for x in _changes if x < 0) / len(_changes)
    moved = gain + loss
    return 50.0 if moved == 0 else 100.0 * gain / moved


def _sell_all(state):
    held = state.positions.get(SYMBOL)
    if held is None:
        return []
    return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


def on_batch(state, batch):
    global _ema_fast, _ema_mid, _mode, _entry_close, _entry_bar, _peak, _v_traded
    for bar in batch["bars"]:
        if bar["symbol"] == SYMBOL:
            c = int(bar["c"])
            if closes:
                _changes.append(c - closes[-1])
                if len(_changes) > 14:
                    _changes.pop(0)
            closes.append(c)
    if not closes:
        return []
    close = closes[-1]
    prev_close = closes[-2] if len(closes) > 1 else close
    ema_fast_prev = _ema_fast
    ema_mid_prev = _ema_mid
    _ema_fast = _ema_step(ema_fast_prev, close, EMA_FAST)
    _ema_mid = _ema_step(ema_mid_prev, close, EMA_MID)
    if state.warming_up or len(closes) < WARMUP_BARS:
        return []
    held = state.positions.get(SYMBOL)
    if held is not None:
        if close > _peak:
            _peak = close
        if _mode == "V":
            # Take-profit vs the average fill price (cost / qty), exactly
            # as the backtest models it; checked first, like the sim.
            avg_entry = held.cost * 10**7 // held.qty if held.qty else 0
            if avg_entry and close * 10000 >= avg_entry * (10000 + V_TP_BPS):
                _v_traded = True
                _mode = None
                return _sell_all(state)
            if close * 10000 <= _peak * (10000 - V_TRAIL_BPS):
                _v_traded = True
                _mode = None
                return _sell_all(state)
            if close * 10000 <= _entry_close * (10000 - V_STOP_BPS):
                _v_traded = True
                _mode = None
                return _sell_all(state)
            if len(closes) - 1 - _entry_bar >= V_MAX_HOLD_BARS:
                _v_traded = True
                _mode = None
                return _sell_all(state)
        else:  # S leg
            if close * 10000 >= _entry_close * (10000 + S_TP_BPS):
                _mode = None
                return _sell_all(state)
            if close * 10000 <= _entry_close * (10000 - S_SL_BPS):
                _mode = None
                return _sell_all(state)
            if len(closes) - 1 - _entry_bar >= S_MAX_HOLD_BARS:
                _mode = None
                return _sell_all(state)
        return []
    # Flat: try the V setup first, then the S setup (gated on a completed V).
    deep = close * 10000 < _ema_mid * (10000 - DEEP_BPS)
    turn = prev_close <= ema_fast_prev and close > _ema_fast
    if deep and turn and state.cash > 0:
        _mode = "V"
        _entry_close = close
        _entry_bar = len(closes) - 1
        _peak = close
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    if _v_traded and len(closes) > S_LOOK:
        drop_ok = closes[-1] * 10000 < closes[-1 - S_LOOK] * (10000 - S_DROP_BPS)
        rsi_ok = _rsi() < S_RSI_MAX
        up2 = close > prev_close and prev_close > closes[-3]
        drop30 = (close / closes[-31] - 1.0) * 10000
        not_deep = close * 10000 > _ema_mid * (10000 - S_EXCL_BPS)
        if drop_ok and rsi_ok and up2 and drop30 > -S_CAP_BPS and not_deep and state.cash > 0:
            _mode = "S"
            _entry_close = close
            _entry_bar = len(closes) - 1
            _peak = close
            return [{"side": "buy", "symbol": SYMBOL,
                     "notional_quote_units": state.cash,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
    return []


makefun_bars.run(on_batch)
