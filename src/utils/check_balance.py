import asyncio
from src.config import settings
from src.utils.web3_utils import get_async_w3
import logging
import sys
import traceback

# Configure basic logging for this script
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s', stream=sys.stdout)
logger = logging.getLogger("BalanceChecker")

async def check_balance():
    if not settings.WALLET_ADDRESS:
        logger.error("WALLET_ADDRESS not found in .env file.")
        return

    rpcs = [
        # settings.RPC_URL, # Skipping the WS one for now as it's likely the culprit
        "https://bsc-dataseed.binance.org/",
        "https://1rpc.io/bnb",
        "https://binance.llamarpc.com",
        "https://rpc.ankr.com/bsc"
    ]
    
    for rpc in rpcs:
        logger.info(f"Connecting to {rpc}...")
        try:
            w3 = get_async_w3(rpc)
            address = w3.to_checksum_address(settings.WALLET_ADDRESS)
            # Try a direct call instead of is_connected()
            balance_wei = await w3.eth.get_balance(address)
            balance_bnb = w3.from_wei(balance_wei, 'ether')
            
            print("\n" + "="*40)
            print(f"Node:    {rpc}")
            print(f"Wallet:  {address}")
            print(f"Balance: {balance_bnb:.6f} BNB")
            print("="*40 + "\n")
            return
        except Exception as e:
            logger.warning(f"Failed to get balance from {rpc}: {e}")
            logger.debug(traceback.format_exc())
            
    logger.error("All RPC connections failed.")

if __name__ == "__main__":
    asyncio.run(check_balance())
