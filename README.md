# btc-race-24h-20261115-0828 v3

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/Endijuan33/btc-race-24h-20261115-0828-v3/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/Endijuan33/btc-race-24h-20261115-0828-v3/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

A bot for the [make.fun bounty](https://make.fun/bounty/btc-race-24h-20261115-0828): race a BTC trading bot live for 24 hours on cbBTC 1-minute bars, $1,000 paper money. v3 of the submitted "Neutral Mosaic" entry — same V-bounce edge and post-washout scalp, plus a 460 bps take-profit on the V leg that lets the bounce run to +460 bps instead of trailing out at +404 bps.

Pure Python, **stdlib only** — the kit's SDK shim is vendored under `vendor/`. Run as `python3 -P -s main.py` (the harness speaks `agent-fun/bars-replay/v1` over stdio).

## Strategy

Two setups, one position at a time, full size, long only:

- **V — deep-drop reversal.** Entry when the close is ≥150 bps below EMA(120) and closes back above EMA(5). Exit at a 460 bps take-profit above the average fill price, or a 60 bps trailing stop from the peak close, or an 80 bps hard stop. The bounce peaks ~+507 bps, so the TP captures +460 bps where the trail alone left +404 bps. TP 420–480 all give the identical fill — a plateau, not a spike.
- **S — grind-day scalp, only after a V trade has completed.** Scalping before the washout means buying into a falling knife (the old dip-buyer lost −$20.23 on the NEW window doing that). Once the washout has turned: entry when the close is ≥100 bps below 50 bars ago, RSI(14) < 30, two consecutive up closes, the last-30-min drop is no worse than −70 bps, and the close is not deep (above EMA(120) − 150 bps). Exit at +100 bps take-profit or −50 bps stop.

## Local grades (real bot through replay.py, exact harness fill model)

| Window | Day shape | Net PnL | Trades | Max DD |
|---|---|---|---|---|
| NEW dev (2026-11-14) | −400 bps, one +4.4% V-bounce | **+$46.19** | 2 | 0.53% |
| OLD dev (2026-11-12/13) | −491 bps grind, no bounce | **+$0.74** | 4 | 1.47% |

Both windows positive (v2 was +$39.57 / +$0.74). Deterministic: two replays byte-identical. The V take-profit is a plateau — TP 420–480, trail 60, stop 60–120 all give the identical +$46.19 / +$0.74. Two-tier scale-in and a looser scalp leg were tested and rejected (they lose on one or both windows).
