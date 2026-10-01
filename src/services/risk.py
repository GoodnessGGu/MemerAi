import logging
logger = logging.getLogger(__name__)

class RiskManager:
    """Manages risk controls, position sizing, dynamic stop-loss/take-profit, and trading circuit breakers."""
    
    def __init__(self):
        self.max_exposure_bnb = 1.0  # Limit maximum trade size to 1.0 BNB
        self.consecutive_losses = 0
        self.max_consecutive_losses_threshold = 3 # Circuit breaker halts trading after 3 consecutive losses

    def check_circuit_breaker(self) -> bool:
        """Returns True if the circuit breaker is active (trading should be halted)."""
        if self.consecutive_losses >= self.max_consecutive_losses_threshold:
            logger.error(f"🚨 CIRCUIT BREAKER ACTIVE: {self.consecutive_losses} consecutive losses. Trading halted.")
            return True
        return False

    def record_trade_result(self, pnl: float):
        """Records the outcome of a trade to track consecutive losses for the circuit breaker."""
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0  # Reset on win

    def reset_circuit_breaker(self):
        """Manually resets the circuit breaker."""
        self.consecutive_losses = 0
        logger.info("Circuit breaker manually reset.")

    def calculate_position_size(
        self,
        ml_probability: float,
        safety_result: dict,
        wallet_result: dict
    ) -> float:
        """
        Calculates position size in BNB using a simplified Kelly Criterion:
        Kelly % = p - (q / b)
          - p: Win probability (ml_probability)
          - q: Loss probability (1 - p)
          - b: Odds (assume 2.0x target, so b = 1.0)
        We then apply a risk fraction (e.g., 0.10 fraction for safety) and scale down based on warnings.
        """
        if self.check_circuit_breaker():
            return 0.0
            
        p = ml_probability
        q = 1.0 - p
        b = 1.0
        
        kelly_fraction = p - (q / b)
        
        if kelly_fraction <= 0:
            return 0.0  # Positive expectation required
            
        # Standard fractional Kelly (10% of full Kelly to avoid over-exposure)
        base_size = kelly_fraction * 0.10 * self.max_exposure_bnb
        
        # Scale down based on safety warning count
        warning_count = safety_result.get("warning_count", 0)
        safety_multiplier = max(0.2, 1.0 - (warning_count * 0.25)) # Lose 25% size per warning
        
        # Scale up based on strong smart wallet backing
        wallet_count = wallet_result.get("count", 0)
        wallet_multiplier = min(1.5, 1.0 + (wallet_count * 0.15))
        
        final_size = base_size * safety_multiplier * wallet_multiplier
        
        # Clamp between 0.01 BNB (minimum trade size) and max exposure limit
        final_size = min(max(final_size, 0.01), self.max_exposure_bnb)
        
        logger.info(
            f"Risk Sizing: Probability={p*100:.1f}% | KellyFraction={kelly_fraction:.2f} | "
            f"Warnings={warning_count} | SmartWallets={wallet_count} | SizedPosition={final_size:.4f} BNB"
        )
        
        return round(final_size, 4)

    def get_trade_parameters(self, narrative_result: dict) -> dict:
        """
        Calculates dynamic TP (Take Profit) and SL (Stop Loss) percentages based on the narrative lifespan phase.
        
        Examples:
          - Early trend (birth, growth): High TP target, wider SL to catch the wave.
          - Late trend (peak, decline): Small TP target, extremely tight SL to exit safely.
        """
        status = narrative_result.get("status", "birth")
        
        # Default parameters
        tp_percent = 50.0   # +50% target
        sl_percent = -15.0  # -15% stop loss
        trailing_stop = True
        
        if status == "birth":
            tp_percent = 100.0   # Early stage trend: shoot for 2x
            sl_percent = -20.0   # Give it room to breathe
        elif status == "growth":
            tp_percent = 75.0
            sl_percent = -15.0
        elif status == "peak":
            tp_percent = 30.0    # Approaching peak: collect small profit quickly
            sl_percent = -10.0   # Tighten stop loss
        elif status == "decline":
            tp_percent = 15.0    # Highly risky phase: quick exits
            sl_percent = -5.0    # Extremely tight stop loss
        elif status == "dead":
            tp_percent = 5.0
            sl_percent = -2.0
            
        return {
            "take_profit_pct": tp_percent,
            "stop_loss_pct": sl_percent,
            "trailing_stop": trailing_stop
        }
