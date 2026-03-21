import logging
from src.config.settings import MIN_LIQUIDITY_BNB

logger = logging.getLogger(__name__)

class DecisionEngine:
    def make_decision(self, safety_result: dict, features: list, ml_probability: float) -> bool:
        """
        SAFETY-ONLY MODE: Enters any token that passes safety + liquidity checks.
        ML probability gate is DISABLED.
        """
        is_safe = safety_result.get("is_safe", False)
        liquidity = features[0] if len(features) > 0 else 0.0
        
        if not is_safe:
            logger.info(f"Rejected: {safety_result.get('risk_flags')}")
            return False
            
        if liquidity < MIN_LIQUIDITY_BNB:
            logger.info(f"Rejected: Low liquidity ({liquidity:.2f} BNB)")
            return False
            
        logger.info(f"✅ SIGNAL: Liq={liquidity:.2f} BNB | Safety OK (ML bypassed)")
        return True
