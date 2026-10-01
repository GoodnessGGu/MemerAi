import logging
logger = logging.getLogger(__name__)

class FeatureGenerator:
    """Combines raw token metrics with narrative, attention, event, and wallet intelligence into enriched feature sets."""
    
    def generate_enriched_features(
        self,
        raw_features: list,
        narrative_result: dict,
        attention_result: dict,
        event_result: dict,
        wallet_result: dict,
        ip_result: dict = None,
        token_info: dict = None
    ) -> dict:
        """
        Consolidates metrics and computes advanced velocity and growth indicators.
        
        raw_features maps:
          [liquidity_bnb, market_cap, buy_sell_ratio, volume_growth, tx_count_growth, holder_count]
        """
        token_info = token_info or {}
        
        # Extract raw components
        liq_bnb = float(raw_features[0]) if len(raw_features) > 0 else 0.0
        mcap_bnb = float(raw_features[1]) if len(raw_features) > 1 else 0.0
        buy_sell = float(raw_features[2]) if len(raw_features) > 2 else 1.0
        vol_growth = float(raw_features[3]) if len(raw_features) > 3 else 0.0
        tx_growth = float(raw_features[4]) if len(raw_features) > 4 else 0.0
        holder_count = float(raw_features[5]) if len(raw_features) > 5 else 1.0
        
        # Calculate dynamic velocities & LP depth ratio
        # Velocity = growth relative to base size
        liq_velocity = (liq_bnb / 100.0) if liq_bnb > 0 else 0.0
        holder_velocity = (tx_growth / holder_count) if holder_count > 0 else 0.0
        swap_velocity = tx_growth * buy_sell
        liq_to_mcap_ratio = (liq_bnb / mcap_bnb) if mcap_bnb > 0 else 0.50
        
        # Event impact booster
        event_boost = event_result.get("impact_score", 0.0) if event_result.get("has_active_event") else 0.0
        
        # Aggregate sentiment approximation
        # Sentiment = buy_sell_ratio adjusted by active events and KOL density
        base_sentiment = min(1.0, buy_sell / 2.0)
        event_sentiment = (event_boost / 10.0) * 0.3
        kol_sentiment = (wallet_result.get("count", 0) * 0.1)
        sentiment_score = min(1.0, base_sentiment + event_sentiment + kol_sentiment)
        
        # Web & Social quality mock metrics (to be expanded in production)
        website_quality = 0.8 if token_info.get("website") else 0.3
        social_presence = 0.9 if token_info.get("twitter") or token_info.get("telegram") else 0.2
        community_quality = (social_presence * 0.6) + (website_quality * 0.4)
        
        extended_features = {
            # Base features (for ML backwards compatibility)
            "liquidity_bnb": liq_bnb,
            "market_cap_bnb": mcap_bnb,
            "buy_sell_ratio": buy_sell,
            "volume_growth": vol_growth,
            "tx_count_growth": tx_growth,
            "holder_count": holder_count,
            
            # Narrative features
            "narrative_category": narrative_result.get("category", "Generic"),
            "narrative_score": narrative_result.get("score", 10.0),
            "narrative_status": narrative_result.get("status", "birth"),
            "narrative_lifespan_hours": narrative_result.get("expected_lifespan_hours", 24.0),
            "trend_growth": narrative_result.get("growth_rate", 0.0),
            
            # Attention features
            "attention_score": attention_result.get("attention_score", 10.0),
            "momentum_score": attention_result.get("momentum_score", 5.0),
            "virality_score": attention_result.get("virality_score", 5.0),
            "decay_score": attention_result.get("decay_score", 0.5),
            
            # Event features
            "active_event_impact": event_boost,
            
            # Wallet features
            "wallet_reputation": wallet_result.get("reputation_score", 0.0),
            "kol_count": wallet_result.get("count", 0),
            
            # Velocity metrics
            "liquidity_velocity": liq_velocity,
            "liquidity_to_mcap_ratio": liq_to_mcap_ratio,
            "holder_velocity": holder_velocity,
            "swap_velocity": swap_velocity,
            
            # Social and Website indicators
            "sentiment": sentiment_score,
            "website_quality": website_quality,
            "social_presence": social_presence,
            "community_quality": community_quality,
            
            # Intellectual Property (IP) Rights
            "is_ip_verified": (ip_result or {}).get("is_ip_verified", False),
            "ip_score": (ip_result or {}).get("ip_score", 0.0)
        }
        
        return extended_features
