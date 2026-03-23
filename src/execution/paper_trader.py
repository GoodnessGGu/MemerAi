import json
import asyncio
import logging
import csv
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from src.core.features import FeatureExtractor

logger = logging.getLogger("PaperTrader")
console = Console()

OUTCOMES_FILE = "data/outcomes.csv"
SIM_STATE_FILE = "data/simulation.json"
INITIAL_BALANCE = 100.0  # USD
TRADE_AMOUNT = 2.0      # USD

class PaperTrader:
    def __init__(self, feature_extractor: FeatureExtractor, on_event=None):
        self.feature_extractor = feature_extractor
        self.on_event = on_event # Callback for TG alerts
        self.active_trades = [] # List of dicts
        self.history = []       # List of outcomes
        self.balance = INITIAL_BALANCE
        self.tp_multiplier = 1.20 # Default +20%
        self.ml_filter_enabled = True # Default ON
        self.ml_threshold = 0.60 # Default 60%
        self.trading_mode = "PAPER" # Default Simulation
        self.trade_amount_bnb = 0.001 # Default 0.001 BNB
        self.trade_amount_usd = 10.0 # Default $10
        self.amount_currency = "BNB" # Default BNB mode
        self._initialize_log()
        self._load_sim_state()

    def _initialize_log(self):
        """Ensure the outcomes file exists with headers."""
        os.makedirs("data", exist_ok=True)
        if not os.path.exists(OUTCOMES_FILE):
            with open(OUTCOMES_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "token", "symbol", "buy_price_bnb", 
                    "exit_price_bnb", "pnl_pct", "pnl_usd", "status", "duration_mins"
                ])

    def _load_sim_state(self):
        """Load persistent balance and TP from JSON."""
        if os.path.exists(SIM_STATE_FILE):
            try:
                with open(SIM_STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.balance = data.get("balance", INITIAL_BALANCE)
                    self.tp_multiplier = data.get("tp_multiplier", 1.20)
                    self.ml_filter_enabled = data.get("ml_filter_enabled", True)
                    self.ml_threshold = data.get("ml_threshold", 0.60)
                    self.trading_mode = data.get("trading_mode", "PAPER")
                    self.trade_amount_bnb = data.get("trade_amount_bnb", 0.001)
                    self.trade_amount_usd = data.get("trade_amount_usd", 10.0)
                    self.amount_currency = data.get("amount_currency", "BNB")
                    logger.info(f"Loaded Sim State: Mode={self.trading_mode}, Amt={self.trade_amount_bnb} BNB / ${self.trade_amount_usd} ({self.amount_currency})")
            except Exception as e:
                logger.error(f"Failed to load sim state: {e}")

    def _save_sim_state(self):
        """Save persistent state to JSON."""
        try:
            with open(SIM_STATE_FILE, "w") as f:
                json.dump({
                    "balance": self.balance, 
                    "tp_multiplier": self.tp_multiplier,
                    "ml_filter_enabled": self.ml_filter_enabled,
                    "ml_threshold": self.ml_threshold,
                    "trading_mode": self.trading_mode,
                    "trade_amount_bnb": self.trade_amount_bnb,
                    "trade_amount_usd": self.trade_amount_usd,
                    "amount_currency": self.amount_currency,
                    "last_updated": datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Failed to save sim state: {e}")

    async def add_trade(self, token_address: str, pair_address: str, name: str, symbol: str, mcap: float, liquidity: float, ml_prob: float = 0, meta: str = "Generic"):
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
            "buy_usd": TRADE_AMOUNT,
            "mcap": mcap,
            "liquidity": liquidity,
            "ml_prob": ml_prob,
            "meta": meta,
            "start_time": datetime.now(),
            "max_price": buy_price,
            "status": "OPEN"
        }
        self.active_trades.append(trade)
        self.balance -= TRADE_AMOUNT
        self._save_sim_state()
        
        console.print(f"[bold green]▶ [PAPER BUY][/bold green] [bold cyan]{symbol}[/bold cyan] | Entry: ${TRADE_AMOUNT:.2f} | Cap: ${mcap:,.0f} | Liq: {liquidity:.2f} BNB")
        
        if self.on_event:
            asyncio.create_task(self.on_event("BUY", trade))

    async def manual_close(self, symbol: str):
        """Allow manual exit from Telegram."""
        target_trade = None
        for trade in self.active_trades:
            if trade["symbol"].upper() == symbol.upper():
                target_trade = trade
                break
        
        if target_trade:
            # Refresh price one last time
            new_price = await self.feature_extractor.get_token_price_bnb(target_trade["pair"])
            if new_price > 0:
                target_trade["current_price"] = new_price
            
            target_trade["status"] = "MANUAL_CLOSE"
            self.active_trades.remove(target_trade)
            self.history.append(target_trade)
            self._log_outcome(target_trade)
            if self.on_event:
                asyncio.create_task(self.on_event("SELL", target_trade))
            return True
        return False

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

            if new_price >= trade["buy_price"] * self.tp_multiplier:
                tp_pct = (self.tp_multiplier - 1) * 100
                console.print(f"[bold gold1]🎯 [+{tp_pct:.0f}% HIT!][/bold gold1] {trade['symbol']} (+{profit_pct:.1f}%)")
                trade["status"] = f"HIT_{tp_pct:.0f}PCT"
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
                self._log_outcome(trade)
                if self.on_event:
                    asyncio.create_task(self.on_event("SELL", trade))

        return self._generate_active_table()

    def _log_outcome(self, trade):
        """Write the finished trade to CSV and update balance."""
        duration = (datetime.now() - trade["start_time"]).total_seconds() / 60
        profit_pct = (trade["current_price"] - trade["buy_price"]) / trade["buy_price"]
        profit_usd = trade["buy_usd"] * (1 + profit_pct)
        
        # Update simulation balance
        self.balance += profit_usd
        self._save_sim_state()

        try:
            with open(OUTCOMES_FILE, "a", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    datetime.now().isoformat(),
                    trade["token"],
                    trade["symbol"],
                    f"{trade['buy_price']:.18f}",
                    f"{trade['current_price']:.18f}",
                    f"{profit_pct*100:.2f}",
                    f"{profit_usd - trade['buy_usd']:.2f}",
                    trade["status"],
                    f"{duration:.1f}"
                ])
        except Exception as e:
            logger.error(f"Failed to log outcome: {e}")

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
    async def manual_close(self, token_address):
        """Force close a trade manually via TG."""
        target_trade = None
        for t in self.active_trades:
            if t["token"].lower() == token_address.lower():
                target_trade = t
                break
        
        if target_trade:
            # Update price one last time
            new_price = await self.feature_extractor.get_token_price_bnb(target_trade["pair"])
            if new_price > 0:
                target_trade["current_price"] = new_price
            
            target_trade["status"] = "MANUAL_CLOSE"
            self.active_trades.remove(target_trade)
            self.history.append(target_trade)
            self._log_outcome(target_trade)
            
            if self.on_event:
                asyncio.create_task(self.on_event("SELL", target_trade))
            return True
        return False

    def _generate_summary_table(self):
        """Generates a summary of history from CSV for persistent stats."""
        total = 0
        hits = 0
        
        try:
            if os.path.exists(OUTCOMES_FILE):
                with open(OUTCOMES_FILE, "r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        total += 1
                        if row["status"] == "HIT_20PCT":
                            hits += 1
        except Exception:
            pass

        table = Table(title="📊 Lifetime Performance Summary", border_style="green")
        table.add_column("Metric", style="white")
        table.add_column("Value", justify="right", style="cyan")
        
        win_rate = (hits / total * 100) if total > 0 else 0
        
        table.add_row("Total Trades", str(total))
        table.add_row("+20% Hits", f"[bold gold1]{hits}[/bold gold1]")
        table.add_row("Win Rate", f"{win_rate:.1f}%")
        table.add_row("Virtual Balance", f"[bold green]${self.balance:.2f}[/bold green]")
        return table
