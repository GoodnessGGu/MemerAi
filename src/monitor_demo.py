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

import src.config.settings as settings
from src.core.listener import BlockchainListener
from src.core.safety import check_token_safety
from src.core.features import FeatureExtractor
from src.core.decision import DecisionEngine
from src.core.kol_tracker import KOLTracker
from src.ml.model import MomentumModel
from src.data.logger import DataLogger
from src.execution.paper_trader import PaperTrader
from src.utils.web3_utils import get_async_w3

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
    tg_bot.paper_trader = paper_trader # Link back
    
    # Start Telegram Bot
    await tg_bot.start()

    decision_engine = DecisionEngine()
    kol_tracker = KOLTracker(w3)
    model = MomentumModel()
    data_logger = DataLogger("paper_trades.csv")

    async def process_new_pair(pair_data: dict, client: httpx.AsyncClient):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        stats["scanned"] += 1
        
        try:
            # 1. Safety Check (Now uses shared client/w3)
            safety_result = await check_token_safety(token_address, pair_address, client=client, w3=w3)
            is_safe = safety_result.get("is_safe", False)
            
            # 2. KOL Tracking
            kol_signal = await kol_tracker.detect_kol_signal(pair_address)
            kol_count = kol_signal.get("kol_count", 0)

            # 3. Extract Features
            features = await feature_extractor.extract_features(token_address, pair_address, kol_signal=kol_signal)
            liq_bnb, mcap_usd = features[0], features[1]
            
            # 4. Predict Probability
            ml_probability = model.predict(features)
            
            # 4. Fetch Metadata
            metadata = await feature_extractor.get_token_metadata(token_address)
            name, symbol = metadata["name"], metadata["symbol"]
            
            stats["scanned"] += 1
            meta = safety_result.get("meta", "Generic")
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
            
            kol_label = f" | [bold gold1]💎 KOLs: {kol_count}[/bold gold1]" if kol_count > 0 else ""
            console.print(
                f"[dim]🔍[/dim] [bold cyan]{symbol}[/bold cyan] [dim]({name[:15]})[/dim] | "
                f"MC:[magenta]${mcap_usd:,.0f}[/magenta] | "
                f"Liq:[yellow]{liq_bnb:.1f}BNB[/yellow] | "
                f"{safety_label}{meta_label}{kol_label} | "
                f"[dim]{token_address[:8]}...[/dim]"
            )
            
            # 5. Log Data
            data_logger.log_features(token_address, pair_address, features, is_safe)
            
            # 7. Make Decision
            decision = decision_engine.make_decision(
                safety_result, features, ml_probability, symbol=symbol,
                ml_enabled=tg_bot.paper_trader.ml_filter_enabled,
                kol_signal=kol_signal
            )
            
            if decision:
                enter_type = "PERMISSIVE ENTER" if warning_count > 0 else "SAFE ENTER"
                console.print(f"  [bold green]↳ {enter_type} →[/bold green] [bold cyan]{symbol}[/bold cyan]")
                await paper_trader.add_trade(
                    token_address, pair_address, name, symbol, mcap_usd, liq_bnb,
                    ml_prob=ml_probability, meta=safety_result.get("meta", "Generic")
                )
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

    async with httpx.AsyncClient() as client:
        listener = BlockchainListener(w3=w3, callback=lambda p: process_new_pair(p, client))
        
        # Run with a Live Dashboard
        with Live(console=console, screen=False, refresh_per_second=1) as live:
            # Start background tasks
            listener_task = asyncio.create_task(listener.start())
            
            while True:
                try:
                    # Update Dashboard
                    if tg_bot.shutdown_requested:
                        logger.warning("Remote shutdown initiated via Telegram.")
                        break
                        
                    table = await paper_trader.monitor_step()
                    live.update(table)
                    await asyncio.sleep(5)
                except Exception as e:
                    logger.error(f"Monitor error: {e}")
                    await asyncio.sleep(10)
                except KeyboardInterrupt:
                    break

        listener.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Stopping Memer AI... Goodbye![/bold red]")
