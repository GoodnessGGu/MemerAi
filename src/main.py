import asyncio
import logging
import sys
from web3 import AsyncWeb3
import src.config.settings as settings

from src.core.listener import BlockchainListener
from src.core.gmgn_listener import GMGNListener
from src.core.safety import check_token_safety
from src.core.features import FeatureExtractor
from src.core.decision import DecisionEngine
from src.ml.model import MomentumModel
from src.data.logger import DataLogger
from src.utils.web3_utils import get_async_w3
from src.data.gmgn import GMGNClient

# --- PRETTIFIED LOGGING ---
class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[90m",       # Gray
        logging.INFO: "\033[94m",        # Blue
        logging.WARNING: "\033[93m",     # Yellow
        logging.ERROR: "\033[91m",       # Red
        logging.CRITICAL: "\033[1;91m",  # Bold Red
    }
    RESET = "\033[0m"
    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        record.msg = f"{color}{record.msg}{self.RESET}"
        return super().format(record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColorFormatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logging.root.setLevel(logging.INFO)
logging.root.addHandler(handler)

# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("MainOrchestrator")

tracked_tokens = {}

async def token_monitor_loop():
    client = GMGNClient()
    logger.info("Started Background Token Performance Monitor")
    while True:
        await asyncio.sleep(60)
        if not tracked_tokens:
            continue
        logger.info("\033[1;95m--- 📊 POST-SNIPE TOKEN MONITOR ---\033[0m")
        for token, entry in list(tracked_tokens.items()):
            try:
                info = await client.get_token_info(settings.GMGN_TARGET_CHAIN, token)
                if info:
                    price = float(info.get("price", 0))
                    mc = float(info.get("marketcap") or info.get("fdv") or (info.get("liquidity", 0) * 2))
                    entry_price = float(entry["entry_price"])
                    change = ((price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
                    
                    symbol = info.get("symbol", "UNK")
                    color = "\033[92m+" if change >= 0 else "\033[91m"
                    logger.info(f"💎 {symbol} ({token[:6]}...): {color}{change:.2f}%\033[0m | Price: ${price:<10.6f} | MC: ${mc:,.0f}")
                    
                    # Take Profit Engine
                    if entry.get("is_owned") and not entry.get("tp_triggered"):
                        tp_target = getattr(settings, "TAKE_PROFIT_PERCENT", 30.0)
                        if change >= tp_target:
                            logger.info(f"\033[1;92m💰 TAKE PROFIT TRIGGERED! {symbol} hit +{change:.2f}% (Target: {tp_target}%)\033[0m")
                            entry["tp_triggered"] = True
                            # Phase 2: await trader.execute_sell(token, amount=100%)
                            
                else:
                    logger.warning(f"Failed to fetch update for {token[:6]}...")
            except Exception as e:
                logger.debug(f"Monitor network wait for {token[:6]}: {e}")
        logger.info("\033[1;95m-----------------------------------\033[0m")

async def main():
    logger.info("Initializing Memer AI Core MVP...")
    
    # Initialize components
    w3 = get_async_w3(settings.RPC_URL)
    feature_extractor = FeatureExtractor(w3)
    decision_engine = DecisionEngine()
    model = MomentumModel()
    data_logger = DataLogger("dataset.csv")

    async def process_new_pair(pair_data: dict):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        is_gmgn = pair_data.get("is_gmgn", False)
        gmgn_stats = pair_data.get("gmgn_stats", {})
        
        try:
            # 1. Safety Check
            safety_result = await check_token_safety(token_address)
            is_safe = safety_result.get("is_safe", False)
            
            # 2. Extract Features
            # If GMGN, we can fake KOL signal using smart_degen_count
            smart_degens = gmgn_stats.get("smart_degen_count", 0)
            
            # GMGN sometimes omits 'marketcap' or uses 'fdv' on new trending tokens
            gmgn_mc = gmgn_stats.get("marketcap") or gmgn_stats.get("fdv") or (gmgn_stats.get("liquidity", 0) * 2)
            
            kol_signal = {
                "kol_count": smart_degens, 
                "total_buyers": gmgn_stats.get("swaps", 1) if is_gmgn else 1,
                "is_kol_signal": smart_degens >= 2,
                "gmgn_liquidity_usd": gmgn_stats.get("liquidity", 0),
                "gmgn_marketcap_usd": gmgn_mc
            }
            
            # Track EVERY token found for post-discovery monitoring
            if token_address not in tracked_tokens:
                tracked_tokens[token_address] = {
                    "entry_price": float(gmgn_stats.get("price", 0)) if is_gmgn else 0.0,
                    "is_owned": False,
                    "tp_triggered": False
                }
                # Keep tracking list manageable if it grows huge (optional safeguard)
                if len(tracked_tokens) > 200:
                    oldest_key = next(iter(tracked_tokens))
                    tracked_tokens.pop(oldest_key, None)
                    
            # Extract features from chain as usual, passing our GMGN KOL signal
            features = await feature_extractor.extract_features(token_address, pair_address or "0x0000000000000000000000000000000000000000", kol_signal)
            
            # 3. Predict Probability
            ml_probability = model.predict(features[:6])
            
            # 4. Log Data
            data_logger.log_features(token_address, pair_address, features, is_safe)
            
            # 5. Make Decision (ML Disabled, relying strictly on GMGN API)
            decision = decision_engine.make_decision(
                safety_result, 
                features, 
                ml_probability, 
                ml_enabled=False, 
                kol_signal=kol_signal
            )
            
            if decision:
                logger.info(f"🚀 Execution triggered for token {token_address} (Phase 2 placeholder)")
                if is_gmgn:
                    marketcap = gmgn_mc
                    liquidity = gmgn_stats.get('liquidity', 0)
                    volume = gmgn_stats.get('volume', 0)
                    logger.info(
                        f"==> 🚨 APE IN / SNIPE ALERT! Token: {token_address} | "
                        f"Smart Degens: {smart_degens} | "
                        f"MC: ${marketcap:,.0f} | "
                        f"Liq: ${liquidity:,.0f} | "
                        f"Vol: ${volume:,.0f}"
                    )
                # Mark as purchased for Take Profit tracking
                tracked_tokens[token_address]["is_owned"] = True
                
                # Phase 2: await trader.execute_trade(...)
                
        except Exception as e:
            logger.error(f"Error processing pair {pair_address or token_address}: {e}")

    # Start Background Monitor 
    asyncio.create_task(token_monitor_loop())

    # Start Listener based on Settings
    if getattr(settings, "USE_GMGN_SOURCE", False):
        logger.info("🔔 Using GMGN API Source for Target Discovery (Sniping & Notifications)")
        listener = GMGNListener(callback=process_new_pair)
    else:
        logger.info("Using standard Blockchain Event Listener")
        listener = BlockchainListener(w3=w3, callback=process_new_pair)
    
    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("Gracefully shutting down.")
        listener.stop()

if __name__ == "__main__":
    asyncio.run(main())
