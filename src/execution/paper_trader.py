import logging
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from src.core.features import FeatureExtractor

logger = logging.getLogger("PaperTrader")
console = Console()

class PaperTrader:
    def __init__(self, feature_extractor: FeatureExtractor):
        self.feature_extractor = feature_extractor
        self.active_trades = [] # List of dicts
        self.history = []       # List of outcomes
        self._live = None

    async def add_trade(self, token_address: str, pair_address: str, name: str, symbol: str, mcap: float, liquidity: float):
        """Simulate a buy at the current price."""
        buy_price = await self.feature_extractor.get_token_price_bnb(pair_address)
        if buy_price == 0:
            return

        trade = {
            "token": token_address,
            "name": name,
            "symbol": symbol,
            "pair": pair_address,
            "buy_price": buy_price,
            "current_price": buy_price,
            "mcap": mcap,
            "liquidity": liquidity,
            "start_time": datetime.now(),
            "max_price": buy_price,
            "status": "OPEN"
        }
        self.active_trades.append(trade)
        console.print(f"[bold green]▶ [PAPER BUY][/bold green] [bold cyan]{symbol}[/bold cyan] | Cap: ${mcap:,.0f} | Liq: {liquidity:.2f} BNB")

    async def monitor_step(self):
        """Check all active trades and return a displayable table."""
        if not self.active_trades:
            return self._generate_summary_table()

        to_remove = []
        for trade in self.active_trades:
            new_price = await self.feature_extractor.get_token_price_bnb(trade["pair"])
            if new_price == 0: continue

            trade["current_price"] = new_price
            trade["max_price"] = max(trade["max_price"], new_price)
            
            profit_pct = (new_price - trade["buy_price"]) / trade["buy_price"] * 100
            elapsed_mins = (datetime.now() - trade["start_time"]).total_seconds() / 60

            if new_price >= trade["buy_price"] * 2.0:
                console.print(f"[bold gold1]🚀 [2X HIT!][/bold gold1] {trade['symbol']} (+{profit_pct:.1f}%)")
                trade["status"] = "HIT_2X"
                to_remove.append(trade)
            elif new_price <= trade["buy_price"] * 0.70:
                console.print(f"[bold red]💀 [STOP LOSS][/bold red] {trade['symbol']} ({profit_pct:.1f}%)")
                trade["status"] = "STOP_LOSS"
                to_remove.append(trade)
            elif elapsed_mins >= 60:
                console.print(f"[bold yellow]🕒 [TIMEOUT][/bold yellow] {trade['symbol']} ({profit_pct:.1f}%)")
                trade["status"] = "TIMEOUT"
                to_remove.append(trade)

        for trade in to_remove:
            if trade in self.active_trades:
                self.active_trades.remove(trade)
                self.history.append(trade)

        return self._generate_active_table()

    def _generate_active_table(self):
        """Generates a table of current open trades."""
        table = Table(title="📡 Active Paper Trades", border_style="blue", expand=True)
        table.add_column("Symbol", style="cyan", no_wrap=True)
        table.add_column("Entry (BNB)", justify="right")
        table.add_column("Current (BNB)", justify="right")
        table.add_column("PnL %", justify="right")
        table.add_column("M.Cap", justify="right", style="magenta")
        table.add_column("Liq (BNB)", justify="right", style="yellow")
        table.add_column("Age", justify="right", style="dim")

        for trade in self.active_trades:
            profit_pct = (trade["current_price"] - trade["buy_price"]) / trade["buy_price"] * 100
            pnl_style = "green" if profit_pct >= 0 else "red"
            age = int((datetime.now() - trade["start_time"]).total_seconds() / 60)
            
            table.add_row(
                trade["symbol"],
                f"{trade['buy_price']:.8f}",
                f"{trade['current_price']:.8f}",
                f"[{pnl_style}]{profit_pct:+.2f}%[/{pnl_style}]",
                f"${trade['mcap']:,.0f}",
                f"{trade['liquidity']:.2f}",
                f"{age}m"
            )
        return table

    def _generate_summary_table(self):
        """Generates a summary of history when no active trades."""
        table = Table(title="📊 Performance Summary", border_style="green")
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="cyan")
        
        successful = len([t for t in self.history if t["status"] == "HIT_2X"])
        total = len(self.history)
        win_rate = (successful / total * 100) if total > 0 else 0
        
        table.add_row("Total Trades", str(total))
        table.add_row("2X Hits", f"[bold gold1]{successful}[/bold gold1]")
        table.add_row("Win Rate", f"{win_rate:.1f}%")
        return table
