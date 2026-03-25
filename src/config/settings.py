import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# RPC and Wallet Configuration
RPC_URL = os.getenv("RPC_URL", "https://bsc-dataseed.binance.org/")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")

# Contract Addresses (BSC Mainnet)
PANCAKE_FACTORY_ADDRESS = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
PANCAKE_ROUTER_ADDRESS = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"

# Aliases
FACTORY_ADDRESS = PANCAKE_FACTORY_ADDRESS
ROUTER_ADDRESS = PANCAKE_ROUTER_ADDRESS

# Trading Thresholds
PROBABILITY_THRESHOLD = 0.40  # Lowered for Demo/Paper Trading without trained model
MIN_LIQUIDITY_BNB = 1.0       # Lowered for Demo/Paper Trading
MAX_BUY_TAX = 15.0            # Maximum allowed buy tax (%)
MAX_SELL_TAX = 15.0           # Maximum allowed sell tax (%)

# Execution Limits (Phase 2)
SLIPPAGE_TOLERANCE_PERCENT = 5.0
TAKE_PROFIT_PERCENT = float(os.getenv("TAKE_PROFIT_PERCENT", "30.0")) # Target 20%-40% range
TAKE_PROFIT_MULTIPLIER = 1.0 + (TAKE_PROFIT_PERCENT / 100.0)
STOP_LOSS_PERCENT = 30.0      # -30% stop loss

# Simulation / Action Settings
PERMISSIVE_MODE = True        # If True, allows tokens with "Warning" risks (Unlocked LP, Whales)

# GMGN AI Integration Settings
USE_GMGN_SOURCE = os.getenv("USE_GMGN_SOURCE", "True").lower() == "true"
GMGN_API_KEY = os.getenv("GMGN_API_KEY", "")
# Polling interval in seconds for GMGN Sniping Notifications
GMGN_POLL_INTERVAL = int(os.getenv("GMGN_POLL_INTERVAL", "60"))
GMGN_TARGET_CHAIN = os.getenv("GMGN_TARGET_CHAIN", "bsc") # sol / bsc / base
