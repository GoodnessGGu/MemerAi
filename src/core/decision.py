import logging
from src.config.settings import MIN_LIQUIDITY_BNB, PERMISSIVE_MODE

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self):
        self.ml_threshold = 0.60 # Default 60%

    def make_decision(self, safety_result: dict, features: list, ml_probability: float, symbol: str = "", ml_enabled: bool = True, kol_signal: dict = None) -> bool:
        kol_signal = kol_signal or {"kol_count": 0, "is_kol_signal": False}
        kol_count = kol_signal.get("kol_count", 0)

        # 0. Symbol Noise Filter
        if symbol.upper() == "USDT" or "USDT" in symbol.upper():
            logger.info(f"Rejected: Symbol '{symbol}' is in blacklist (USDT)")
            return False

        # 1. KOL Signal Determination
        is_kol_signal = kol_count >= 2
        has_any_kol = kol_count >= 1

        # 2. KOL Boost Logic (For ML)
        # Apply a +10% boost to ML probability if 2+ KOLs are found
        boosted_prob = ml_probability
        if is_kol_signal:
            boosted_prob = min(1.0, ml_probability + 0.10)
            logger.debug(f"KOL Boost Applied: {ml_probability*100:.1f}% -> {boosted_prob*100:.1f}%")

        # 3. ML Filter (Conditional)
        if ml_enabled and boosted_prob < self.ml_threshold:
            # INTEGRATION: When ML is ON, we STILL allow a pass if a strong KOL signal exists regardless of ML score
            if not is_kol_signal:
                logger.debug(f"Rejected: Boosted ML Probability ({boosted_prob*100:.1f}%) < {self.ml_threshold*100:.0f}%")
                return False
            else:
                logger.debug(f"ML bypass activated: Strong KOL signal ({kol_count}) overrides low ML probability.")
        elif not ml_enabled:
            # INTEGRATION: When ML is OFF, we MUST have a strong GMGN API / KOL signal to proceed.
            if not is_kol_signal:
                logger.debug(f"Rejected (ML OFF): Token relies strictly on GMGN API but lacks strong Smart Degen signal ({kol_count} < 2).")
                return False
            else:
                logger.info(f"✅ GMGN Detection Approved: Strong Smart Degen signal ({kol_count} >= 2).")

        is_safe = safety_result.get("is_safe", False)
        fatal_count = safety_result.get("fatal_count", 99)
        warning_count = safety_result.get("warning_count", 0)
        liquidity = features[0] if len(features) > 0 else 0.0
        
        if liquidity < MIN_LIQUIDITY_BNB:
            logger.debug(f"Rejected: Low liquidity ({liquidity:.2f} BNB)")
            return False

        # 4. Final Safety Logic with KOL Integration
        if fatal_count > 0:
            logger.debug(f"Rejected: {fatal_count} FATAL issues found.")
            return False

        if not PERMISSIVE_MODE:
            # Strict mode: Rejects warnings UNLESS a KOL is present (Quality Override)
            if warning_count > 0:
                if has_any_kol:
                    logger.debug(f"Warning Bypass: Token has {warning_count} warnings, but {kol_count} KOL(s) detected. PASS.")
                else:
                    logger.debug(f"Rejected (Strict): {warning_count} Warning issues found and no KOL signal.")
                    return False
            
        logger.info(f"✅ SIGNAL: Liq={liquidity:.2f} BNB | Safety OK | ML={'OFF' if not ml_enabled else f'{boosted_prob*100:.1f}%'} | KOLs={kol_count}")
        return True
