import asyncio
import logging
import sys
import httpx
from web3 import AsyncWeb3
from rich.logging import RichHandler
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import src.config.settings as settings
from src.core.listener import BlockchainListener
from src.core.safety import check_token_safety
from src.core.features import FeatureExtractor
from src.core.kol_tracker import KOLTracker
from src.data.logger import DataLogger
from src.execution.paper_trader import PaperTrader
from src.execution.trader import RealTrader
from src.utils.web3_utils import get_async_w3

# Import newly evolved modular intelligence services
from src.services.db import KnowledgeDatabase
from src.services.narrative import NarrativeEngine
from src.services.attention import AttentionEngine
from src.services.event import EventEngine
from src.services.wallet import WalletIntelligenceEngine, DEFAULT_SMART_WALLETS
from src.services.feature_generator import FeatureGenerator
from src.services.ml_ensemble import MLEnsembleEngine
from src.services.risk import RiskManager

# Use Rich for specialized logging
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console, show_path=False)]
)

# Suppress noisy HTTP request logs from httpx / telegram internals
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)

logger = logging.getLogger("MonitorDemo")
db = KnowledgeDatabase()

async def main():
    console.print(Panel.fit(
        "[bold cyan]MEMER AI - REAL-TIME MONITORING DASHBOARD[/bold cyan]\n"
        "[dim]Tracking BSC Launches, Safety, and PnL[/dim]",
        border_style="cyan"
    ))
    
    from src.ui.telegram_bot import MemerTelegramBot
    
    w3 = get_async_w3(settings.RPC_URL)
    feature_extractor = FeatureExtractor(w3)
    
    # Track stats for TG
    stats = {"scanned": 0, "rejected": 0, "meta_counts": {}}
    
    # Initialize TG Bot Wrapper
    tg_bot = MemerTelegramBot(None) # Will set paper_trader later
    tg_bot.market_stats = stats # Link stats
    
    async def handle_trade_event(event_type: str, trade: dict):
        """Format and send TG alerts for Paper Trades."""
        if event_type == "BUY":
            text = (
                f"🚀 *POSITION OPENED*\n\n"
                f"💎 *Asset:* `{trade['symbol']} ({trade['name'][:15]})`\n"
                f"💰 *Entry:* `{trade['buy_price']:.8f} BNB`\n"
                f"📊 *MC:* `${trade['mcap']:,.0f}` | 🌊 *Liq:* `{trade['liquidity']:.2f}`\n"
                f"🛡️ *Safety:* `{trade.get('meta', 'Generic')}`\n"
                f"📍 `CA: {trade['token']}`"
            )
        else: # SELL
            profit = (trade["current_price"] - trade["buy_price"]) / trade["buy_price"] * 100
            status = trade.get("status", "CLOSED")
            emoji = "🎯" if "HIT_20" in status else "💀" if "STOP" in status else "🏁"
            
            text = (
                f"{emoji} *TRADE CLOSED ({status})*\n\n"
                f"💎 *Asset:* `{trade['symbol']}`\n"
                f"📈 *Outcome:* `{profit:+.2f}%` PnL\n"
                f"💵 *Sim Balance:* `${paper_trader.balance:.2f}`"
            )
        await tg_bot.send_alert(text)

    paper_trader = PaperTrader(feature_extractor, on_event=handle_trade_event)
    real_trader = RealTrader(w3)
    tg_bot.paper_trader = paper_trader # Link back
    
    # Start Telegram Bot
    await tg_bot.start()

    # Initialize modular intelligence services
    narrative_engine = NarrativeEngine(db)
    attention_engine = AttentionEngine()
    event_engine = EventEngine(db)
    wallet_engine = WalletIntelligenceEngine(db)
    from src.services.ip_detector import IPRightsEngine
    ip_engine = IPRightsEngine(db)
    feature_generator = FeatureGenerator()
    ml_ensemble = MLEnsembleEngine()
    risk_manager = RiskManager()

    kol_tracker = KOLTracker(w3)
    data_logger = DataLogger("paper_trades.csv")

    # Run one narrative discovery cycle on startup
    try:
        await narrative_engine.discover_narratives()
    except Exception as e:
        logger.warning(f"Initial narrative discovery failed: {e}")

    async def process_new_pair(pair_data: dict, client: httpx.AsyncClient):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        stats["scanned"] += 1
        
        try:
            # 1. Safety Check (Now uses shared client/w3)
            safety_result = await check_token_safety(token_address, pair_address, client=client, w3=w3)
            is_safe = safety_result.get("is_safe", False)
            
            # Fetch Metadata
            metadata = await feature_extractor.get_token_metadata(token_address)
            name, symbol = metadata["name"], metadata["symbol"]
            
            # 2. Evaluate Dynamic Narrative
            narrative_res = narrative_engine.evaluate_token_narrative(name, symbol)
            
            # 3. Check Active Events
            event_res = event_engine.get_active_event_impact(narrative_res["category"])
            
            # 4. Form active wallets cluster (KOL tracking)
            kol_signal = await kol_tracker.detect_kol_signal(pair_address)
            kol_count = kol_signal.get("kol_count", 0)
            kol_signal.setdefault("age_hours", 0.1)
            
            active_wallet_list = []
            if kol_count > 0:
                active_wallet_list = list(DEFAULT_SMART_WALLETS.keys())[:kol_count]
                
            wallet_res = wallet_engine.evaluate_wallet_cluster(active_wallet_list, narrative_res["category"])
            kol_signal["smart_money_score"] = wallet_res["reputation_score"]

            # 5. Extract Features
            features = await feature_extractor.extract_features(token_address, pair_address, kol_signal=kol_signal)
            liq_bnb, mcap_bnb = features[0], features[1]

            # Fetch BNB price for correct USD conversions
            bnb_price = await feature_extractor.get_bnb_price()
            mcap_usd = mcap_bnb * bnb_price
            logger.info(f"DEBUG: token={symbol} features={features} bnb_price={bnb_price} mcap_usd={mcap_usd}")

            # Approximate USD liquidity for metrics
            if not kol_signal.get("gmgn_liquidity_usd") and not kol_signal.get("liquidity_usd"):
                kol_signal["gmgn_liquidity_usd"] = float(liq_bnb) * float(bnb_price)
            
            # 6. Calculate Attention Analytics
            attention_res = attention_engine.calculate_attention(features, kol_signal)
            
            # 6b. Verify IP Rights
            ip_res = await ip_engine.verify_ip_rights(token_address, symbol, name)
            
            # 7. Generate Enriched Features
            enriched_features = feature_generator.generate_enriched_features(
                features,
                narrative_res,
                attention_res,
                event_res,
                wallet_res,
                ip_result=ip_res,
                token_info={"website": None, "twitter": None, "telegram": None}
            )
            
            # 8. ML Ensemble Decision
            ensemble_res = ml_ensemble.predict_ensemble(enriched_features)
            ml_probability = ensemble_res["probability"]
            
            meta = narrative_res.get("category", "Generic")
            stats["meta_counts"][meta] = stats["meta_counts"].get(meta, 0) + 1
            
            # Print per-token scan summary
            fatal_count = safety_result.get("fatal_count", 0)
            warning_count = safety_result.get("warning_count", 0)
            
            if fatal_count > 0:
                safety_label = f"[bold red]❌ FATAL ({fatal_count})[/bold red]"
            elif warning_count > 0:
                safety_label = f"[bold yellow]⚠️ WARN ({warning_count})[/bold yellow]"
            else:
                safety_label = "[bold green]✅ CLEAN[/bold green]"

            meta_label = f" [dim]| {meta}[/dim]" if meta != "Generic" else ""
            
            # Pre-compute score for console
            smart_score = wallet_res["reputation_score"]
            score_label = f" | [bold magenta]SM:{smart_score:.0f}[/bold magenta]"
            kol_label = f" | [bold gold1]💎 KOLs: {kol_count}[/bold gold1]" if kol_count > 0 else ""
            ip_label = " | [bold gold1]🏷️ IP VERIFIED[/bold gold1]" if ip_res.get("is_ip_verified") else ""
            console.print(
                f"[dim]🔍[/dim] [bold cyan]{symbol}[/bold cyan] [dim]({name[:15]})[/dim] | "
                f"MC:[magenta]${mcap_usd:,.0f}[/magenta] | "
                f"Liq:[yellow]{liq_bnb:.1f}BNB[/yellow] | "
                f"{safety_label}{meta_label}{score_label}{kol_label}{ip_label} | "
                f"[dim]{token_address[:8]}...[/dim]"
            )
            
            # 9. Log Data
            data_logger.log_features(token_address, pair_address, features, is_safe)
            
            # 10. Risk sizing & dynamic trade parameters
            position_size = risk_manager.calculate_position_size(ml_probability, safety_result, wallet_res)
            trade_params = risk_manager.get_trade_parameters(narrative_res)
            
            decision = (position_size > 0) and is_safe
            
            if decision:
                enter_type = "PERMISSIVE ENTER" if warning_count > 0 else "SAFE ENTER"
                current_mode = tg_bot.paper_trader.trading_mode
                sm = wallet_res["reputation_score"]
                
                console.print(
                    f"  [bold green]↳ {enter_type} ({current_mode}) SM={sm:.1f} →[/bold green] "
                    f"[bold cyan]{symbol}[/bold cyan]"
                )
                logger.info(f"Final Decision Justification:\n{ensemble_res['explainability']}")
                
                if current_mode == "REAL":
                    # Determine Trade Amount
                    if paper_trader.amount_currency == "USD":
                        trade_amt = paper_trader.trade_amount_usd / bnb_price
                        logger.info(f"USD Mode: ${paper_trader.trade_amount_usd} -> {trade_amt:.4f} BNB (at ${bnb_price:,.0f})")
                    else:
                        trade_amt = paper_trader.trade_amount_bnb

                    # Execute on-chain
                    tx_hash = await real_trader.buy_token(token_address, trade_amt)
                    if tx_hash:
                        logger.warning(f"REAL TRADE EXECUTED: {symbol} | TX: {tx_hash}")
                else:
                    # Execute in simulation
                    # Dynamically inject dynamic take profit and stop loss to paper trader
                    await paper_trader.add_trade(
                        token_address, pair_address, name, symbol, mcap_usd, liq_bnb,
                        ml_prob=ml_probability, meta=meta
                    )
                    # Override SL/TP target for this trade in paper trader active tracking state
                    for active in paper_trader.active_trades:
                        if active["token"] == token_address:
                            active["tp_target"] = trade_params["take_profit_pct"]
                            active["sl_target"] = trade_params["stop_loss_pct"]
            else:
                stats["rejected"] += 1
                
        except Exception as e:
            logger.error(f"Error processing {token_address[:8]}: {e}")
 
    # Update TG Bot Market Stats
    original_button_handler = tg_bot._button_handler
    async def custom_button_handler(update, context):
        if update.message.text == "📈 Market Stats":
            msg = (
                f"📈 *Market Analytics*\n\n"
                f"Scanned: `{stats['scanned']}`\n"
                f"Rejected: `{stats['rejected']}`\n"
                f"Conversion: `{(len(paper_trader.active_trades)+len(paper_trader.history))/max(1, stats['scanned'])*100:.1f}%`"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await original_button_handler(update, context)
    
    tg_bot._button_handler = custom_button_handler

    # Periodically run narrative discovery in background
    async def narrative_background_task():
        while True:
            await asyncio.sleep(1800)
            try:
                await narrative_engine.discover_narratives()
                narrative_engine.decay_narratives()
            except Exception as e:
                logger.error(f"Error in narrative loop: {e}")

    asyncio.create_task(narrative_background_task())

    # Periodically scan Solana launches via GMGN
    async def solana_background_scanner():
        from src.data.gmgn import GMGNClient
        gmgn_client = GMGNClient()
        seen_sol_tokens = set()
        while True:
            try:
                tokens = await gmgn_client.get_trending_tokens(chain="sol", interval="1m", limit=10)
                for t in tokens:
                    if not isinstance(t, dict): continue
                    addr = t.get("address") or t.get("token_address")
                    if not addr or addr in seen_sol_tokens: continue
                    seen_sol_tokens.add(addr)
                    
                    symbol = t.get("symbol", "SOL_TOKEN")[:10]
                    name = t.get("name", "Solana Token")[:15]
                    mcap = float(t.get("marketcap") or t.get("market_cap") or 0)
                    liq = float(t.get("liquidity") or 0)
                    
                    is_safe = (liq >= 1000) and (t.get("is_honeypot") != "1")
                    safety_label = "[bold green]✅ CLEAN[/bold green]" if is_safe else "[bold red]❌ FATAL (1)[/bold red]"
                    
                    # Evaluate Dynamic Narrative & IP Rights
                    narrative_res = narrative_engine.evaluate_token_narrative(name, symbol)
                    ip_res = await ip_engine.verify_ip_rights(addr, symbol, name)
                    
                    meta = narrative_res.get("category", "Generic")
                    narrative_score = narrative_res.get("confidence", 0.0) * 100.0
                    is_ip_verified = ip_res.get("is_ip_verified", False)
                    
                    meta_label = f" [dim]| {meta}[/dim]" if meta != "Generic" else ""
                    ip_label = " | [bold gold1]🏷️ IP VERIFIED[/bold gold1]" if is_ip_verified else ""
                    
                    console.print(
                        f"[dim]🔍 [SOLANA][/dim] [bold purple]{symbol}[/bold purple] [dim]({name})[/dim] | "
                        f"MC:[magenta]${mcap:,.0f}[/magenta] | "
                        f"Liq:[yellow]${liq:,.0f}[/yellow] | "
                        f"{safety_label}{meta_label}{ip_label} | "
                        f"[dim]{addr[:8]}...[/dim]"
                    )

                    # STRICT ENTRY FILTER: Require Verified IP Rights OR High Narrative Score (>= 60%)
                    should_buy = is_safe and mcap >= 5000 and (is_ip_verified or narrative_score >= 60.0 or meta != "Generic")
                    
                    if should_buy and len(paper_trader.active_trades) < 5:
                        console.print(
                            f"  [bold green]↳ HIGH-ALPHA ENTER (PAPER) Meta={meta} | IP={is_ip_verified} →[/bold green] "
                            f"[bold purple]{symbol}[/bold purple]"
                        )
                        await paper_trader.add_trade(
                            addr, addr, name, symbol, mcap, max(1.0, liq / 500.0),
                            ml_prob=0.85 if is_ip_verified else 0.70, meta=meta
                        )
                    elif is_safe and not should_buy:
                        console.print(f"  [dim]⏭️ SKIPPED (Generic Narrative / Unverified IP)[/dim] → {symbol}")
            except Exception as e:
                logger.error(f"Error in Solana scanner loop: {e}")
            await asyncio.sleep(25)

    asyncio.create_task(solana_background_scanner())

    async with httpx.AsyncClient() as client:
        listener = BlockchainListener(w3=w3, callback=lambda p: process_new_pair(p, client))
        
        # Run with a Live Dashboard
        with Live(console=console, screen=False, refresh_per_second=1) as live:
            # Start background tasks
            listener_task = asyncio.create_task(listener.start())
            
            while True:
                try:
                    # Sync dynamic settings to engine
                    risk_manager.max_exposure_bnb = paper_trader.trade_amount_bnb
                    
                    # Update Dashboard
                    if tg_bot.shutdown_requested:
                        logger.warning("Remote shutdown initiated via Telegram.")
                        break
                        
                    table = await paper_trader.monitor_step()
                    live.update(table)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Error in UI loop: {e}")
                    await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
