import asyncio
import json
import os
import logging
import sys
import time
import httpx
from web3 import AsyncWeb3
import src.config.settings as settings

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from src.core.listener import BlockchainListener
from src.core.gmgn_listener import GMGNListener
from src.core.safety import check_token_safety
from src.core.features import FeatureExtractor
from src.utils.web3_utils import get_async_w3
from src.data.gmgn import GMGNClient

# Import the new evolved modular intelligence services
from src.services.db import KnowledgeDatabase
from src.services.narrative import NarrativeEngine
from src.services.attention import AttentionEngine
from src.services.event import EventEngine
from src.services.wallet import WalletIntelligenceEngine, DEFAULT_SMART_WALLETS
from src.services.feature_generator import FeatureGenerator
from src.services.ml_ensemble import MLEnsembleEngine
from src.services.risk import RiskManager

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
STATE_FILE = "tracked_tokens.json"
tracked_tokens = {}

# Initialize database globally for monitor loop
db = KnowledgeDatabase()

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(tracked_tokens, f)
    except Exception as e:
        logger.error(f"Failed to save state: {e}")

def load_state():
    global tracked_tokens
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                tracked_tokens = json.load(f)
            logger.info(f"Loaded {len(tracked_tokens)} tracked tokens from disk.")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            tracked_tokens = {}

async def token_monitor_loop():
    client = GMGNClient()
    logger.info("Started Background Token Performance Monitor")
    while True:
        await asyncio.sleep(60)
        # Only render the table if we have officially sniped/owned tokens
        owned_tokens = {k: v for k, v in tracked_tokens.items() if v.get("is_owned")}
        if not owned_tokens:
            continue
            
        logger.info("\n\033[1;95m" + "="*88 + "\033[0m")
        logger.info("\033[1;95m| {:^10} | {:^15} | {:^10} | {:^10} | {:^12} | {:^15} |\033[0m".format("SYMBOL", "ADDRESS", "PNL (%)", "PEAK (%)", "PRICE", "MARKET CAP"))
        logger.info("\033[1;95m" + "-"*88 + "\033[0m")
        
        for token, entry in list(owned_tokens.items()):
            try:
                info = await client.get_token_info(settings.GMGN_TARGET_CHAIN, token)
                if info:
                    price = float(info.get("price", 0))
                    mc = float(info.get("marketcap") or info.get("fdv") or (info.get("liquidity", 0) * 2))
                    entry_price = float(entry["entry_price"])
                    change = ((price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
                    
                    symbol = info.get("symbol", "UNK")
                    pnl_str = f"{change:+.2f}%"
                    color = "\033[92m" if change >= 0 else "\033[91m"
                    
                    # Track Peak for Trailing SL
                    if "peak_pnl" not in entry or change > entry["peak_pnl"]:
                        entry["peak_pnl"] = change
                    
                    peak_str = f"{entry.get('peak_pnl', 0):+.2f}%"
                    
                    logger.info(f"| {symbol[:10]:<10} | {token[:6]}...{token[-4:]} | {color}{pnl_str:>10}\033[0m | {peak_str:>10} | ${price:<11.6f} | ${mc:>14,.0f} |")
                    
                    # Take Profit Engine
                    if not entry.get("tp_triggered") and not entry.get("sl_triggered"):
                        tp_target = entry.get("tp_target", getattr(settings, "TAKE_PROFIT_PERCENT", 30.0))
                        sl_target = entry.get("sl_target", -abs(getattr(settings, "STOP_LOSS_PERCENT", 20.0)))
                        if isinstance(sl_target, (int, float)) and sl_target > 0:
                            sl_target = -sl_target
                        
                        if change >= tp_target:
                            logger.info(f"\033[1;92m💰 TAKE PROFIT TRIGGERED! {symbol} hit +{change:.2f}% (Target: {tp_target}%)\033[0m")
                            entry["tp_triggered"] = True
                            # Record token outcome
                            db.save_token_outcome(token, symbol, price, change / 100.0 + 1.0, False, 1.0)
                        
                        elif change <= sl_target:
                            logger.warning(f"\033[1;91m🚨 STOP LOSS TRIGGERED! {symbol} hit {change:.2f}% (Limit: {sl_target}%)\033[0m")
                            entry["sl_triggered"] = True
                            db.save_token_outcome(token, symbol, price, change / 100.0 + 1.0, True, 1.0)
                        
                        # ---- Trailing Stop Loss ----
                        elif getattr(settings, "TRAILING_STOP_LOSS_PERCENT", 0) > 0:
                            tsl_offset = getattr(settings, "TRAILING_STOP_LOSS_PERCENT", 15.0)
                            peak = entry.get("peak_pnl", 0)
                            if peak > 10.0: # Only trail if we are in significant profit (>10%)
                                if change <= peak - tsl_offset:
                                    logger.warning(f"\033[1;91m🚨 TRAILING STOP TRIGGERED! {symbol} hit {change:.2f}% (Peak was {peak:.2f}%, Trail: -{tsl_offset}%)\033[0m")
                                    entry["sl_triggered"] = True
                                    db.save_token_outcome(token, symbol, price, change / 100.0 + 1.0, True, 1.0)
                            
                    if entry.get("tp_triggered") or entry.get("sl_triggered"):
                        save_state()
                            
                else:
                    logger.warning(f"Failed to fetch update for {token[:6]}...")
            except Exception as e:
                logger.debug(f"Monitor network wait for {token[:6]}: {e}")
        logger.info("\033[1;95m-----------------------------------\033[0m")

async def narrative_discovery_loop(narrative_engine):
    logger.info("Started Background Narrative Discovery Loop")
    while True:
        try:
            await narrative_engine.discover_narratives()
            narrative_engine.decay_narratives()
        except Exception as e:
            logger.error(f"Error in narrative discovery loop: {e}")
        # Run every 30 minutes
        await asyncio.sleep(1800)

async def main():
    logger.info("Initializing Memer AI Core Production Services...")
    load_state()
    
    # Initialize components
    w3 = get_async_w3(settings.RPC_URL)
    feature_extractor = FeatureExtractor(w3)
    client = httpx.AsyncClient()
    
    # Initialize newly evolved modular intelligence services
    narrative_engine = NarrativeEngine(db)
    attention_engine = AttentionEngine()
    event_engine = EventEngine(db)
    wallet_engine = WalletIntelligenceEngine(db)
    feature_generator = FeatureGenerator()
    ml_ensemble = MLEnsembleEngine()
    risk_manager = RiskManager()

    # Pre-run narrative discovery once on startup so we have data
    try:
        await narrative_engine.discover_narratives()
    except Exception as e:
        logger.warning(f"Initial narrative discovery failed (will retry in background): {e}")

    async def process_new_pair(pair_data: dict):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        is_gmgn = pair_data.get("is_gmgn", False)
        gmgn_stats = pair_data.get("gmgn_stats", {})
        
        try:
            # 1. Safety Check (Passing pair_address, shared client, and w3 to check LP locks)
            safety_result = await check_token_safety(
                token_address, 
                pair_address=pair_address, 
                client=client, 
                w3=w3
            )
            is_safe = safety_result.get("is_safe", False)
            
            # Fetch Metadata
            metadata = await feature_extractor.get_token_metadata(token_address)
            name = metadata.get("name", "Unknown")
            symbol = metadata.get("symbol", "UNK")
            
            # Ignore symbol noise
            if symbol.upper() == "USDT" or "USDT" in symbol.upper():
                logger.info(f"Rejected: Symbol '{symbol}' is in blacklist (USDT)")
                return

            # 2. Evaluate Dynamic Narrative
            narrative_res = narrative_engine.evaluate_token_narrative(name, symbol)
            
            # 3. Check Active Events
            event_res = event_engine.get_active_event_impact(narrative_res["category"])
            
            # 4. Form active wallets cluster (KOL tracking)
            smart_degens = gmgn_stats.get("smart_degen_count", 0)
            active_wallet_list = []
            if smart_degens > 0:
                # Construct cluster from tracked addresses
                active_wallet_list = list(DEFAULT_SMART_WALLETS.keys())[:smart_degens]
                
            wallet_res = wallet_engine.evaluate_wallet_cluster(active_wallet_list, narrative_res["category"])
            
            # Age and Smart Money Info
            age_hours = 4.0
            if is_gmgn:
                open_time = gmgn_stats.get("open_time") or gmgn_stats.get("created_at") or 0
                if open_time:
                    age_hours = max(0.0, (int(time.time()) - int(open_time)) / 3600.0)
            
            kol_signal = {
                "kol_count": smart_degens, 
                "total_buyers": gmgn_stats.get("swaps", 1) if is_gmgn else 1,
                "is_kol_signal": smart_degens >= 2,
                "gmgn_liquidity_usd": gmgn_stats.get("liquidity", 0),
                "gmgn_marketcap_usd": gmgn_stats.get("marketcap") or gmgn_stats.get("fdv") or (gmgn_stats.get("liquidity", 0) * 2),
                "volume": gmgn_stats.get("volume", 0) if is_gmgn else 0,
                "swaps": gmgn_stats.get("swaps", 0) if is_gmgn else 0,
                "age_hours": age_hours,
                "smart_money_score": wallet_res["reputation_score"],
                "meta": narrative_res.get("category", "")
            }
            
            # Track EVERY token found for post-discovery monitoring
            if token_address not in tracked_tokens:
                tracked_tokens[token_address] = {
                    "entry_price": float(gmgn_stats.get("price", 0)) if is_gmgn else 0.0,
                    "is_owned": False,
                    "tp_triggered": False,
                    "sl_triggered": False,
                    "peak_pnl": 0.0
                }
                # Keep tracking list manageable if it grows huge (optional safeguard)
                if len(tracked_tokens) > 200:
                    oldest_key = next(iter(tracked_tokens))
                    tracked_tokens.pop(oldest_key, None)
                save_state()
                    
            # Extract features from chain
            features = await feature_extractor.extract_features(token_address, pair_address or "0x0000000000000000000000000000000000000000", kol_signal)
            
            # 5. Calculate Attention Analytics
            attention_res = attention_engine.calculate_attention(features, kol_signal)
            
            # 6. Generate Feature Generator 2.0 Enriched Features
            enriched_features = feature_generator.generate_enriched_features(
                features,
                narrative_res,
                attention_res,
                event_res,
                wallet_res,
                token_info={"website": gmgn_stats.get("website"), "twitter": gmgn_stats.get("twitter"), "telegram": gmgn_stats.get("telegram")}
            )
            
            # 7. ML Ensemble Decision
            ensemble_res = ml_ensemble.predict_ensemble(enriched_features)
            ml_probability = ensemble_res["probability"]
            
            # 8. Risk Management (Sizing, SL, TP)
            position_size = risk_manager.calculate_position_size(ml_probability, safety_result, wallet_res)
            trade_params = risk_manager.get_trade_parameters(narrative_res)
            
            # Overall Decision Logic: Position size > 0 and Safety check clean
            decision = (position_size > 0) and is_safe
            
            if decision:
                logger.info(f"==> 🚨 APE IN / SNIPE ALERT! Token: {symbol} ({token_address})")
                logger.info("=========================================")
                logger.info(f"Narrative: {narrative_res['category']} ({narrative_res['status']})")
                logger.info(f"Attention Score: {attention_res['attention_score']:.1f} | Momentum: {attention_res['momentum_score']:.1f}")
                logger.info(f"Wallet Cluster Reputation: {wallet_res['reputation_score']:.1f} (KOLs={wallet_res['count']})")
                logger.info(f"Safety: Safe (Warnings: {safety_result.get('warning_count', 0)})")
                logger.info(f"ML Ensemble Probability: {ml_probability*100:.1f}% (Confidence: {ensemble_res['confidence']*100:.1f}%)")
                logger.info(f"Expected Lifespan: {narrative_res['expected_lifespan_hours']} hours")
                logger.info(f"Risk Position Size: {position_size:.4f} BNB | TP: +{trade_params['take_profit_pct']}% | SL: {trade_params['stop_loss_pct']}%")
                logger.info(f"Final Decision Justification:\n{ensemble_res['explainability']}")
                logger.info("=========================================")
                
                # Mark as purchased for performance monitoring
                tracked_tokens[token_address]["is_owned"] = True
                tracked_tokens[token_address]["tp_target"] = trade_params["take_profit_pct"]
                tracked_tokens[token_address]["sl_target"] = trade_params["stop_loss_pct"]
                save_state()
                
                # Phase 2: await trader.execute_trade(...)
            else:
                logger.info(f"Token {symbol} skipped (ML Prob={ml_probability*100:.1f}%, PositionSize={position_size:.4f} BNB, Safe={is_safe})")
                
        except Exception as e:
            logger.error(f"Error processing pair {pair_address or token_address}: {e}")

    # Start Background tasks
    asyncio.create_task(token_monitor_loop())
    asyncio.create_task(narrative_discovery_loop(narrative_engine))

    try:
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
    finally:
        await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
