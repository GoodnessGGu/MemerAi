import asyncio
import logging
from web3 import AsyncWeb3
from src.config.settings import PANCAKE_FACTORY_ADDRESS

logger = logging.getLogger(__name__)

# Minimal Factory ABI for PairCreated event
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "arg3", "type": "uint256"}
        ],
        "name": "PairCreated",
        "type": "event"
    }
]

class HistoryExtractor:
    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3
        self.factory_address = w3.to_checksum_address(PANCAKE_FACTORY_ADDRESS)
        self.factory_contract = w3.eth.contract(address=self.factory_address, abi=FACTORY_ABI)

    async def get_historical_pairs(self, blocks_back: int = 5000) -> list:
        """Fetch PairCreated events from the last N blocks."""
        try:
            current_block = await self.w3.eth.block_number
            from_block = current_block - blocks_back
            
            logger.info(f"Fetching historical pairs from block {from_block} to {current_block}...")
            
            # Use get_logs for bulk historical data
            logs = await self.factory_contract.events.PairCreated().get_logs(
                from_block=from_block,
                to_block=current_block
            )
            
            pairs = []
            for log in logs:
                pairs.append({
                    "token0": log["args"]["token0"],
                    "token1": log["args"]["token1"],
                    "pair": log["args"]["pair"],
                    "block": log["blockNumber"]
                })
            
            logger.info(f"Found {len(pairs)} historical pairs.")
            return pairs
        except Exception as e:
            logger.error(f"Error fetching historical pairs: {e}")
            return []

if __name__ == "__main__":
    from src.utils.web3_utils import get_async_w3
    from src.config.settings import RPC_URL
    
    async def test():
        w3 = get_async_w3(RPC_URL)
        extractor = HistoryExtractor(w3)
        pairs = await extractor.get_historical_pairs(1000)
        for p in pairs[:5]:
            print(p)
            
    asyncio.run(test())
