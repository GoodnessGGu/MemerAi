import logging
import asyncio
from web3 import AsyncWeb3
from src.config.settings import FACTORY_ADDRESS, WBNB_ADDRESS

logger = logging.getLogger(__name__)

# Minimal ABI to decode PairCreated event from PancakeSwap Factory
FACTORY_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "token0", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "token1", "type": "address"},
            {"indexed": False, "internalType": "address", "name": "pair", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "PairCreated",
        "type": "event"
    }
]

class BlockchainListener:
    def __init__(self, w3: AsyncWeb3, callback):
        self.w3 = w3
        self.factory_contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(FACTORY_ADDRESS), 
            abi=FACTORY_ABI
        )
        self.callback = callback
        self.is_running = False

    async def start(self):
        if not await self.w3.is_connected():
            logger.error("Failed to connect to BSC RPC.")
            return

        logger.info("Connected to BSC RPC. Starting Blockchain Listener...")
        self.is_running = True
        
        last_block = await self.w3.eth.block_number
        logger.info(f"Starting to sync from block: {last_block}")

        while self.is_running:
            try:
                current_block = await self.w3.eth.block_number
                if current_block > last_block:
                    # Fetch PairCreated logs
                    events = await self.factory_contract.events.PairCreated.get_logs(
                        from_block=last_block + 1,
                        to_block=current_block
                    )
                    
                    for event in events:
                        await self._process_event(event)
                        
                    last_block = current_block
                
                # Wait before polling next blocks to avoid throttling
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Error fetching block data: {e}")
                await asyncio.sleep(5)
                
    def stop(self):
        self.is_running = False

    async def _process_event(self, event):
        """Extracts token details from the PairCreated event."""
        # The args dictionary contains the decoded event data
        args = event.get('args', {})
        token0 = args.get('token0')
        token1 = args.get('token1')
        pair_address = args.get('pair')
        
        # We want to identify the new meme token, assuming it's paired with WBNB.
        # Often newly launched tokens trade against WBNB or BUSD/USDT.
        wbnb_checksum = self.w3.to_checksum_address(WBNB_ADDRESS)
        
        if token0 == wbnb_checksum:
            new_token = token1
        elif token1 == wbnb_checksum:
            new_token = token0
        else:
            # Pair doesn't include WBNB directly, might be tricky to value or trade simply
            new_token = token0 # arbitrarily pick token0 for now or skip
            
        timestamp = await self._get_block_timestamp(event.get('blockNumber'))
        
        pair_data = {
            "token_address": new_token,
            "pair_address": pair_address,
            "timestamp": timestamp,
            "block_number": event.get('blockNumber')
        }
        
        logger.info(f"New pair detected: Token {new_token} | Pair {pair_address}")
        
        # Dispatch to the callback for async processing
        if self.callback:
            # Create a task to avoid blocking the listener loop
            asyncio.create_task(self.callback(pair_data))

    async def _get_block_timestamp(self, block_number):
        try:
            block = await self.w3.eth.get_block(block_number)
            return block.get('timestamp')
        except Exception:
            import time
            return int(time.time())

