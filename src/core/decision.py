import logging
from src.config.settings import MIN_LIQUIDITY_BNB, PERMISSIVE_MODE

logger = logging.getLogger(__name__)

class DecisionEngine:
    def make_decision(self, safety_result: dict, features: list, ml_probability: float, symbol: str = "", ml_enabled: bool = True) -> bool:
        """
        Decision logic based on safety categories, ML filtering, and symbol noise.
        """
        # 0. Symbol Noise Filter
        if symbol.upper() == "USDT" or "USDT" in symbol.upper():
            logger.info(f"Rejected: Symbol '{symbol}' is in blacklist (USDT)")
            return False

        # 1. ML Filter (Conditional)
        if ml_enabled and ml_probability < 0.80:
            logger.info(f"Rejected: ML Probability ({ml_probability*100:.1f}%) < 80%")
            return False

        is_safe = safety_result.get("is_safe", False)
        fatal_count = safety_result.get("fatal_count", 99)
        warning_count = safety_result.get("warning_count", 0)
        liquidity = features[0] if len(features) > 0 else 0.0
        
        if liquidity < MIN_LIQUIDITY_BNB:
            logger.info(f"Rejected: Low liquidity ({liquidity:.2f} BNB)")
            return False

        if PERMISSIVE_MODE:
            # In Permissive mode, we only block FATAL risks
            if fatal_count > 0:
                logger.info(f"Rejected: {fatal_count} FATAL issues found.")
                return False
        else:
            # Strict mode: any risk flag rejects
            if not is_safe or warning_count > 0 or fatal_count > 0:
                logger.info(f"Rejected: Risk flags found: {safety_result.get('risk_flags')}")
                return False
            
        logger.info(f"✅ SIGNAL: Liq={liquidity:.2f} BNB | Safety OK | ML={ml_probability*100:.1f}%")
        return True
