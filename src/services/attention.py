import logging
logger = logging.getLogger(__name__)

class AttentionEngine:
    """Calculates attention, momentum, virality, and decay metrics for a token."""

    def calculate_attention(self, features: list, kol_signal: dict = None) -> dict:
        """
        Computes attention analytics based on extracted features and KOL activity.
        
        features array mapping:
          - features[0]: liquidity_bnb
          - features[1]: market_cap
          - features[2]: buy_sell_ratio
          - features[3]: volume_growth
          - features[4]: tx_count_growth
          - features[5]: holder_count
        """
        kol_signal = kol_signal or {}
        
        # Extract features safely
        liq_bnb = float(features[0]) if len(features) > 0 else 0.0
        mcap_bnb = float(features[1]) if len(features) > 1 else 0.0
        buy_sell = float(features[2]) if len(features) > 2 else 1.0
        vol_growth = float(features[3]) if len(features) > 3 else 0.0
        tx_growth = float(features[4]) if len(features) > 4 else 0.0
        holder_count = float(features[5]) if len(features) > 5 else 1.0
        
        # Get KOL stats
        kol_count = float(kol_signal.get("kol_count", 0) or 0)
        smart_score = float(kol_signal.get("smart_money_score", 0) or 0)
        
        # 1. Attention Score (0-100) - measures current active mindshare
        attention = (
            (kol_count * 25.0) 
            + (min(vol_growth, 5.0) * 10.0)
            + (min(tx_growth, 5.0) * 5.0)
        )
        # Cap at 100, but minimum 10 if there is some activity
        attention_score = min(max(attention, 10.0), 100.0)
        
        # 2. Momentum Score (0-100) - rate of acceleration
        momentum = (
            (buy_sell * 15.0) 
            + (tx_growth * 10.0) 
            + (vol_growth * 8.0)
        )
        momentum_score = min(max(momentum, 5.0), 100.0)
        
        # 3. Virality Score (0-100) - growth rate of the network
        virality = (
            (kol_count * 30.0) 
            + (smart_score * 0.5) 
            + (min(holder_count / 100.0, 30.0))
        )
        virality_score = min(max(virality, 5.0), 100.0)
        
        # 4. Decay Score (0.0 to 1.0) - decay velocity of interest
        # High volume/tx growth yields low decay; low activity yields high decay
        decay_score = max(0.01, min(1.0, 1.0 / (1.0 + tx_growth + vol_growth)))
        
        # 5. Confidence Score (0.0 to 1.0) - data completeness index
        confidence_score = 1.0 if liq_bnb > 0 and holder_count > 1 else 0.5
        
        return {
            "attention_score": attention_score,
            "momentum_score": momentum_score,
            "virality_score": virality_score,
            "decay_score": decay_score,
            "confidence_score": confidence_score
        }
