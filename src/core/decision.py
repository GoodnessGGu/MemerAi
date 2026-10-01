import logging
from src.config.settings import (
    MIN_LIQUIDITY_BNB,
    PERMISSIVE_MODE,
    SMART_MONEY_MIN_SCORE,
    HALLOWEEN_META_BOOST,
    MIN_LIQUIDITY_TO_MCAP_RATIO,
)

logger = logging.getLogger(__name__)


class DecisionEngine:
    def __init__(self):
        self.ml_threshold = 0.60  # Default 60%
        self.smart_money_threshold = SMART_MONEY_MIN_SCORE

    def calculate_smart_money_score(self, kol_signal: dict) -> float:
        """Weighted Smart Money Score (0-100)."""
        if not kol_signal:
            return 0.0

        # Accept either kol_count or smart_degen_count
        smart_count = float(
            kol_signal.get("kol_count")
            or kol_signal.get("smart_degen_count")
            or 0
        )
        # Accept either gmgn_liquidity_usd or liquidity_usd (backtest / GMGN shapes)
        liquidity_usd = float(
            kol_signal.get("gmgn_liquidity_usd")
            or kol_signal.get("liquidity_usd")
            or 0
        )
        volume = float(kol_signal.get("volume", 0) or 0)
        swaps = float(kol_signal.get("swaps", 0) or 0)
        age_hours = float(kol_signal.get("age_hours", 4.0) or 4.0)

        score = (
            smart_count * 12.0
            + (liquidity_usd / 500.0)
            + (volume / 10000.0)
            + (swaps / 50.0)
        )

        # Freshness bonus
        if age_hours < 1.0:
            score += 15.0
        elif age_hours < 2.0:
            score += 8.0

        # Seasonal Halloween Narrative Bonus
        meta = kol_signal.get("meta", "") or ""
        if HALLOWEEN_META_BOOST and "Halloween" in meta:
            score += 15.0
            logger.info("🎃 Halloween Meta Boost applied: +15 to Smart Money Score")

        return min(score, 100.0)

    def make_decision(
        self,
        safety_result: dict,
        features: list,
        ml_probability: float,
        symbol: str = "",
        ml_enabled: bool = True,
        kol_signal: dict = None,
    ) -> bool:
        kol_signal = kol_signal or {"kol_count": 0, "is_kol_signal": False}
        smart_score = self.calculate_smart_money_score(kol_signal)
        kol_count = kol_signal.get("kol_count", 0)
        has_any_kol = kol_count >= 1
        is_kol_signal = kol_count >= 2 or smart_score >= self.smart_money_threshold

        # Stash score for callers / logging
        kol_signal["smart_money_score"] = smart_score
        kol_signal["is_kol_signal"] = is_kol_signal

        logger.info(f"Smart Money Score: {smart_score:.1f}/100 | Degens: {kol_count}")

        # 0. Symbol Noise Filter
        if symbol and (symbol.upper() == "USDT" or "USDT" in symbol.upper()):
            logger.info(f"Rejected: Symbol '{symbol}' is in blacklist (USDT)")
            return False

        # 0.1 Illiquid FDV Trap Check (e.g. $300M market cap with only $50k liquidity)
        mcap_usd = float(kol_signal.get("gmgn_marketcap_usd", 0) or 0)
        liq_usd = float(kol_signal.get("gmgn_liquidity_usd", 0) or 0)
        if mcap_usd > 100_000 and liq_usd > 0:
            liq_ratio = liq_usd / mcap_usd
            if liq_ratio < MIN_LIQUIDITY_TO_MCAP_RATIO:
                logger.info(
                    f"Rejected: Illiquid FDV Trap! Liquidity (${liq_usd:,.0f}) is only {liq_ratio*100:.2f}% of Market Cap (${mcap_usd:,.0f}), minimum {MIN_LIQUIDITY_TO_MCAP_RATIO*100:.1f}% required."
                )
                return False

        # 1. KOL Boost Logic (For ML)
        boosted_prob = ml_probability
        if is_kol_signal:
            boosted_prob = min(1.0, ml_probability + 0.10)
            logger.debug(
                f"KOL/Smart-Money Boost Applied: {ml_probability*100:.1f}% -> {boosted_prob*100:.1f}%"
            )

        # 2. ML / Smart Money Filter
        if ml_enabled and boosted_prob < self.ml_threshold:
            # Strong Smart Money / KOL signal can override a weak ML score
            if not is_kol_signal:
                logger.info(
                    f"Rejected: ML Probability ({boosted_prob*100:.1f}%) < "
                    f"{self.ml_threshold*100:.0f}% and no Smart Money override "
                    f"(score={smart_score:.1f})."
                )
                return False
            logger.info(
                f"ML bypass activated: Smart Money Score {smart_score:.1f} "
                f"(degens={kol_count}) overrides low ML probability."
            )
        elif not ml_enabled:
            # When ML is OFF, require a strong Smart Money Score
            if smart_score < self.smart_money_threshold:
                logger.info(
                    f"Rejected (ML OFF): Smart Money Score too low "
                    f"({smart_score:.1f} < {self.smart_money_threshold})."
                )
                return False
            logger.info(f"✅ GMGN Strong Signal (Score: {smart_score:.1f})")

        # 3. Safety + liquidity (original logic)
        fatal_count = safety_result.get("fatal_count", 99)
        warning_count = safety_result.get("warning_count", 0)
        liquidity = features[0] if len(features) > 0 else 0.0

        if liquidity < MIN_LIQUIDITY_BNB:
            logger.info(
                f"Rejected: Low liquidity ({liquidity:.2f} < {MIN_LIQUIDITY_BNB} BNB)"
            )
            return False

        if fatal_count > 0:
            logger.info(f"Rejected: {fatal_count} FATAL safety issues found.")
            return False

        if not PERMISSIVE_MODE:
            # Strict mode: reject warnings unless a strong smart-money signal exists
            if warning_count > 0:
                if is_kol_signal or has_any_kol:
                    logger.info(
                        f"Warning Bypass: Token has {warning_count} warnings, "
                        f"but Smart Money Score={smart_score:.1f} (degens={kol_count}). PASS."
                    )
                else:
                    logger.info(
                        f"Rejected (Strict): {warning_count} warning issues and no strong KOL/Smart Money."
                    )
                    return False

        logger.info(
            f"✅ FINAL APPROVAL | SmartScore={smart_score:.1f} | "
            f"Liq={liquidity:.2f} BNB | "
            f"ML={'OFF' if not ml_enabled else f'{boosted_prob*100:.1f}%'} | "
            f"KOLs={kol_count}"
        )
        return True
