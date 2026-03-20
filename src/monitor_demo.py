import asyncio
import logging
import sys
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

logger = logging.getLogger("MonitorDemo")

async def main():
    console.print(Panel.fit(
        "[bold cyan]MEMER AI - REAL-TIME MONITORING DASHBOARD[/bold cyan]\n"
        "[dim]Tracking BSC Launches, Safety, and PnL[/dim]",
        border_style="cyan"
    ))
    
    w3 = get_async_w3(settings.RPC_URL)
    feature_extractor = FeatureExtractor(w3)
    decision_engine = DecisionEngine()
    model = MomentumModel()
    data_logger = DataLogger("paper_trades.csv")
    paper_trader = PaperTrader(feature_extractor)

    async def process_new_pair(pair_data: dict):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        
        try:
            # 1. Safety Check
            safety_result = await check_token_safety(token_address)
            is_safe = safety_result.get("is_safe", False)
            
            # 2. Extract Features
            features = await feature_extractor.extract_features(token_address, pair_address)
            liq_bnb = features[0]
            mcap_usd = features[1]
            
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
                await paper_trader.add_trade(token_address, pair_address, name, symbol, mcap_usd, liq_bnb)
            else:
                pass # Silent rejection to keep dashboard clean
                
        except Exception as e:
            logger.error(f"Error processing {token_address[:8]}: {e}")

    listener = BlockchainListener(w3=w3, callback=process_new_pair)
    
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
