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
    stats = {"scanned": 0, "rejected": 0}
    
    # Initialize TG Bot Wrapper
    tg_bot = MemerTelegramBot(None) # Will set paper_trader later
    
    async def handle_trade_event(event_type: str, trade: dict):
        """Format and send TG alerts for Paper Trades."""
        if event_type == "BUY":
            text = (
                f"🟢 *PAPER BUY ALERT*\n\n"
                f"📌 *Token:* `{trade['symbol']}` ({trade['name']})\n"
                f"💰 *Entry:* `${trade['buy_usd']:.2f}`\n"
                f"📊 *Stats:* MC `${trade['mcap']:,.0f}` | Liq `{trade['liquidity']:.2f} BNB`\n"
                f"🏷️ *Meta:* `{trade.get('meta', 'Unknown')}`\n"
                f"🧠 *ML Prob:* `{trade.get('ml_prob', 0)*100:.1f}%`\n"
                f"🛡️ *Safety:* `MATCHED` ✅\n"
                f"📄 *CA:* `{trade['token']}`"
            )
        else: # SELL
            profit = (trade["current_price"] - trade["buy_price"]) / trade["buy_price"] * 100
            emoji = "🚀" if trade["status"] == "HIT_2X" else "🛑"
            text = (
                f"{emoji} *PAPER SELL ALERT*\n\n"
                f"Token: `{trade['symbol']}`\n"
                f"Status: `{trade['status']}`\n"
                f"PnL: `{profit:+.2f}%`\n"
                f"CA: `{trade['token']}`"
            )
        await tg_bot.send_alert(text)

    paper_trader = PaperTrader(feature_extractor, on_event=handle_trade_event)
    tg_bot.paper_trader = paper_trader # Link back
    
    # Start Telegram Bot
    await tg_bot.start()

    decision_engine = DecisionEngine()
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
            
            # 2. Extract Features
            features = await feature_extractor.extract_features(token_address, pair_address)
            liq_bnb, mcap_usd = features[0], features[1]
            
            # 3. Predict Probability
            ml_probability = model.predict(features)
            
            # 4. Fetch Metadata
            metadata = await feature_extractor.get_token_metadata(token_address)
            name, symbol = metadata["name"], metadata["symbol"]
            
            # 5. Log Data
            data_logger.log_features(token_address, pair_address, features, is_safe)
            
            # 6. Make Decision
            decision = decision_engine.make_decision(safety_result, features, ml_probability)
            
            if decision:
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
