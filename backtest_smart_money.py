"""
Backtester for the weighted Smart Money Score.

Usage:
    python backtest_smart_money.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.core.decision import DecisionEngine
from src.config.settings import SMART_MONEY_MIN_SCORE

# Add more real signals here from your logs
HISTORICAL_SIGNALS = [
    {
        "address": "0xabc1",
        "smart_degen_count": 5,
        "liquidity_usd": 45000,
        "volume": 120000,
        "swaps": 800,
        "age_hours": 0.8,
        "outcome": "win",
    },
    {
        "address": "0xdef2",
        "smart_degen_count": 2,
        "liquidity_usd": 8000,
        "volume": 15000,
        "swaps": 120,
        "age_hours": 3.5,
        "outcome": "loss",
    },
    {
        "address": "0x1233",
        "smart_degen_count": 8,
        "liquidity_usd": 120000,
        "volume": 450000,
        "swaps": 3200,
        "age_hours": 1.2,
        "outcome": "win",
    },
]


def run_backtest():
    engine = DecisionEngine()
    threshold = engine.smart_money_threshold  # from SMART_MONEY_MIN_SCORE
    wins = 0
    total = len(HISTORICAL_SIGNALS)

    print("=== Smart Money Score Backtest ===")
    print(f"Threshold: {threshold:.1f} (SMART_MONEY_MIN_SCORE)\n")

    for s in HISTORICAL_SIGNALS:
        kol = {
            k: s[k]
            for k in ["smart_degen_count", "liquidity_usd", "volume", "swaps", "age_hours"]
            if k in s
        }
        # Normalize to DecisionEngine field names
        kol["kol_count"] = kol.pop("smart_degen_count", 0)
        kol["gmgn_liquidity_usd"] = kol.pop("liquidity_usd", 0)

        score = engine.calculate_smart_money_score(kol)
        predicted = score >= threshold
        actual = s["outcome"] == "win"

        print(
            f"{s['address'][:8]:8} | Score: {score:6.1f} | "
            f"{'BUY' if predicted else 'SKIP':4} | Actual: {s['outcome'].upper()}"
        )
        if predicted == actual:
            wins += 1

    print(f"\nAccuracy: {wins / total * 100:.1f}% ({wins}/{total})")


if __name__ == "__main__":
    run_backtest()
