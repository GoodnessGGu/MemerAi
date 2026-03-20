import logging
from src.config.settings import PROBABILITY_THRESHOLD, MIN_LIQUIDITY_BNB

logger = logging.getLogger(__name__)

class DecisionEngine:
    def make_decision(self, safety_result: dict, features: list, ml_probability: float) -> bool:
        """
        Determines if a token is a valid trade candidate based on safety, features, and ML probability.
        """
        is_safe = safety_result.get("is_safe", False)
        
        # features list structure: 
        # [liquidity_bnb, market_cap, buy_sell_ratio, volume_growth, tx_count_growth, holder_count]
        liquidity = features[0] if len(features) > 0 else 0.0
        
        if not is_safe:
            logger.info(f"Trade rejected: Token is not safe. Flags: {safety_result.get('risk_flags')}")
            return False
            
        if liquidity < MIN_LIQUIDITY_BNB:
            logger.info(f"Trade rejected: Insufficient liquidity ({liquidity} BNB < {MIN_LIQUIDITY_BNB} BNB).")
            return False
            
        if ml_probability < PROBABILITY_THRESHOLD:
            logger.info(f"Trade rejected: Low ML probability ({ml_probability:.2f} < {PROBABILITY_THRESHOLD}).")
            return False
            
        logger.info(f"TRADE SIGNAL GENERATED: Probability {ml_probability:.2f}, Liquidity {liquidity:.2f} BNB")
        return True
