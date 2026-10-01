import logging
from src.services.db import KnowledgeDatabase

logger = logging.getLogger(__name__)

# Default smart wallets configuration with specialization
DEFAULT_SMART_WALLETS = {
    "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": {
        "label": "Meme Whale Alpha",
        "win_rate": 0.72,
        "total_trades": 85,
        "roi_mean": 2.4,
        "roi_median": 1.8,
        "specialization": "Meme Meta 🐸"
    },
    "0x5e839e93345ea88c74bd2b415a77cc49dccae20d": {
        "label": "PolitiFi Snipe Pro",
        "win_rate": 0.65,
        "total_trades": 42,
        "roi_mean": 3.1,
        "roi_median": 2.0,
        "specialization": "PolitiFi Meta 🇺🇸"
    },
    "0x68eb15e6dbf674e40f702dca0bf99dccaef874f4": {
        "label": "CZ Narrative Frontrunner",
        "win_rate": 0.58,
        "total_trades": 50,
        "roi_mean": 1.9,
        "roi_median": 1.4,
        "specialization": "Binance/CZ Meta 💛"
    },
    "0x0eb425611c28bb3b6dbb9e39cbf0846ba252d58a": {
        "label": "AI Meta Early Adopter",
        "win_rate": 0.81,
        "total_trades": 26,
        "roi_mean": 4.5,
        "roi_median": 3.2,
        "specialization": "AI Meta 🧠"
    }
}

class WalletIntelligenceEngine:
    def __init__(self, db: KnowledgeDatabase = None):
        self.db = db or KnowledgeDatabase()
        self._init_default_wallets()

    def _init_default_wallets(self):
        """Pre-populate the database with default high-performance trackers if not already present."""
        for address, stats in DEFAULT_SMART_WALLETS.items():
            existing = self.db.get_wallet(address)
            if not existing:
                self.db.save_wallet(
                    address=address,
                    label=stats["label"],
                    win_rate=stats["win_rate"],
                    total_trades=stats["total_trades"],
                    roi_mean=stats["roi_mean"],
                    roi_median=stats["roi_median"],
                    specialization=stats["specialization"]
                )

    def evaluate_wallet_cluster(self, active_wallets: list, token_narrative: str = "Generic") -> dict:
        """
        Evaluates a cluster of wallets buying a token.
        Weights each wallet by win rate, ROI, and specialization alignment.
        Returns a dict: {reputation_score, count, specialization_bonus_applied}
        """
        if not active_wallets:
            return {"reputation_score": 0.0, "count": 0, "specialization_bonus": 0.0}

        total_weight = 0.0
        weighted_score_sum = 0.0
        specialization_bonus = 0.0
        
        for addr in active_wallets:
            wallet = self.db.get_wallet(addr)
            if not wallet:
                # Default metrics for untracked wallets (neutral weight)
                win_rate = 0.45
                roi = 1.0
                weight = 1.0
                specialization = "Generic"
            else:
                win_rate = wallet["win_rate"]
                roi = wallet["roi_median"]
                # Higher trade count gives higher weight confidence
                weight = min(2.5, 1.0 + (wallet["total_trades"] / 50.0))
                specialization = wallet["specialization"]

            # Calculate individual wallet score based on ROI and Win Rate
            wallet_score = (win_rate * 60.0) + (min(roi, 5.0) * 8.0)
            
            # Specialization alignment bonus
            if specialization == token_narrative and token_narrative != "Generic":
                wallet_score = min(100.0, wallet_score + 15.0)
                specialization_bonus += 5.0
                
            weighted_score_sum += wallet_score * weight
            total_weight += weight

        reputation_score = (weighted_score_sum / total_weight) if total_weight > 0 else 0.0
        
        # Scale reputation by cluster size (strength in numbers)
        size_multiplier = min(1.3, 1.0 + (len(active_wallets) - 1) * 0.1)
        final_reputation = min(100.0, reputation_score * size_multiplier)
        
        return {
            "reputation_score": round(final_reputation, 1),
            "count": len(active_wallets),
            "specialization_bonus": specialization_bonus
        }

    def record_trade_outcome(self, address: str, roi: float, is_success: bool):
        """Updates a wallet's win rate, trade count, and ROI statistics after a trade completes."""
        wallet = self.db.get_wallet(address)
        if not wallet:
            # Create new wallet entry
            self.db.save_wallet(
                address=address,
                label=f"Trader {address[:6]}",
                win_rate=1.0 if is_success else 0.0,
                total_trades=1,
                roi_mean=roi,
                roi_median=roi,
                specialization="Generic"
            )
        else:
            total = wallet["total_trades"] + 1
            successes = round(wallet["win_rate"] * wallet["total_trades"]) + (1 if is_success else 0)
            new_win_rate = successes / total
            
            # Moving average ROI approximation
            new_mean = ((wallet["roi_mean"] * wallet["total_trades"]) + roi) / total
            new_median = ((wallet["roi_median"] * wallet["total_trades"]) + roi) / total
            
            self.db.save_wallet(
                address=address,
                label=wallet["label"],
                win_rate=new_win_rate,
                total_trades=total,
                roi_mean=new_mean,
                roi_median=new_median,
                specialization=wallet["specialization"]
            )
            logger.info(f"Updated Wallet Stats: {address} | Trades: {total} | WinRate: {new_win_rate:.2f} | Median ROI: {new_median:.2f}x")
        
