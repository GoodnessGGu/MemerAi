import logging
import asyncio
import time
from typing import Callable, Optional
from src.data.gmgn import GMGNClient
from src.config.settings import GMGN_POLL_INTERVAL, GMGN_TARGET_CHAIN

logger = logging.getLogger(__name__)

class GMGNListener:
    """
    Simulates a blockchain listener but uses GMGN trending APIs
    to find high-potential tokens (snipes). Acting as a notification engine.
    """
    def __init__(self, callback: Callable):
        self.callback = callback
        self.client = GMGNClient()
        self.is_running = False
        self.processed_tokens = set()

    async def start(self):
        logger.info(f"Starting GMGN Target Polling Engine on {GMGN_TARGET_CHAIN}...")
        self.is_running = True
        
        while self.is_running:
            try:
                # 1. Fetch top trending tokens (e.g. 5m interval)
                trending_tokens = await self.client.get_trending_tokens(
                    chain=GMGN_TARGET_CHAIN, 
                    interval="5m", 
                    limit=20
                )
                
                if not trending_tokens:
                    logger.debug("No trending tokens returned or API error.")
                else:
                    for token_data in trending_tokens:
                        token_address = token_data.get("address")
                        pool_address = token_data.get("pool_address", None)
                        
                        if not token_address or token_address in self.processed_tokens:
                            continue
                            
                        # If we haven't processed this token recently
                        self.processed_tokens.add(token_address)
                        
                        # 2. Enrich with additional token info
                        # We could fetch smart_degen_count here or pass it to process_new_pair
                        # GMGN trending API sometimes includes 'smart_degen_count' natively.
                        smart_degen_count = token_data.get("smart_degen_count", 0)
                        
                        logger.debug(f"GMGN Notification: Detected trending token {token_address[:8]} with {smart_degen_count} Smart Degens.")
                        
                        timestamp = int(time.time())
                        pair_data = {
                            "token_address": token_address,
                            "pair_address": pool_address,
                            "timestamp": timestamp,
                            "block_number": 0,
                            "is_gmgn": True,
                            "gmgn_stats": token_data
                        }
                        
                        if self.callback:
                            asyncio.create_task(self.callback(pair_data))
                            
            except Exception as e:
                logger.error(f"Error checking GMGN trending: {e}")
                
            # Wait before the next poll
            await asyncio.sleep(GMGN_POLL_INTERVAL)
            
    def stop(self):
        self.is_running = False

