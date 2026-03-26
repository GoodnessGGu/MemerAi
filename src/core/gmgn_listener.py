import logging
import asyncio
import time
from typing import Callable, Optional
import src.config.settings as settings
from src.data.gmgn import GMGNClient

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
        logger.info(f"Starting GMGN Target Polling Engine on {settings.GMGN_TARGET_CHAIN}...")
        self.is_running = True
        
        while self.is_running:
            try:
                # 1. Fetch top trending tokens (e.g. 5m interval)
                # We use a short interval to get "Active" tokens
                trending_tokens = await self.client.get_trending_tokens(
                    chain=settings.GMGN_TARGET_CHAIN, 
                    interval="1h", 
                    limit=50,
                    orderby="swaps"
                )
                
                if not trending_tokens:
                    logger.debug("No trending tokens returned or API error.")
                else:
                    current_time = int(time.time())
                    max_age_sec = int(getattr(settings, "GMGN_MAX_AGE_HOURS", 4.0) * 3600)
                    min_cluster = int(getattr(settings, "MIN_SMART_MONEY_CLUSTER", 3))

                    for token_data in trending_tokens:
                        token_address = token_data.get("address")
                        pool_address = token_data.get("pool_address", None)
                        
                        if not token_address or token_address in self.processed_tokens:
                            continue
                            
                        # ---- Pro Filter 1: Age Filter (0 - 4 hrs) ----
                        open_time = token_data.get("open_time") or token_data.get("created_at") or 0
                        if open_time > 0:
                            age_sec = current_time - int(open_time)
                            if age_sec > max_age_sec:
                                logger.debug(f"Skipping {token_address[:8]}: Too old ({age_sec/3600:.1f}h)")
                                continue
                            if age_sec < 0: # Future timestamp?
                                continue
                        
                        # ---- Pro Filter 2: Smart Money Cluster Detection ----
                        smart_degen_count = token_data.get("smart_degen_count", 0)
                        if smart_degen_count < min_cluster:
                            logger.debug(f"Skipping {token_address[:8]}: Low cluster density ({smart_degen_count} < {min_cluster})")
                            continue

                        # If we haven't processed this token recently
                        self.processed_tokens.add(token_address)
                        
                        logger.info(f"🚀 PRO SIGNAL: Detected {token_address[:8]} | Age: {(current_time-int(open_time))/60:.1f}m | Smart Degens: {smart_degen_count}")
                        
                        timestamp = current_time
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
            await asyncio.sleep(settings.GMGN_POLL_INTERVAL)
            
    def stop(self):
        self.is_running = False

