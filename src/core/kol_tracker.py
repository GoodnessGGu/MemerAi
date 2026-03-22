import json
import os
import logging
from web3 import Web3
from datetime import datetime

logger = logging.getLogger("KOLTracker")

SMART_WALLETS_FILE = "data/smart_wallets.json"

class KOLTracker:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.smart_wallets = self._load_smart_wallets()

    def _load_smart_wallets(self) -> set:
        """Load smart wallet addresses from JSON."""
        if os.path.exists(SMART_WALLETS_FILE):
            try:
                with open(SMART_WALLETS_FILE, "r") as f:
                    wallets = json.load(f)
                    return {w.lower() for w in wallets}
            except Exception as e:
                logger.error(f"Failed to load smart wallets: {e}")
        return set()

    async def get_recent_buyers(self, pair_address: str, blocks_back: int = 50) -> list:
        """
        Fetch recent buyers for a pair using Swap events.
        Decodes buyer from transaction initiator.
        """
        try:
            swap_event_signature = self.w3.keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
            
            latest_block = await self.w3.eth.block_number
            logs = await self.w3.eth.get_logs({
                "fromBlock": latest_block - blocks_back,
                "toBlock": latest_block,
                "address": Web3.to_checksum_address(pair_address),
                "topics": [swap_event_signature]
            })

            buyers = []
            for log in logs:
                tx_hash = log['transactionHash']
                tx = await self.w3.eth.get_transaction(tx_hash)
                if tx:
                    sender = tx['from'].lower()
                    buyers.append(sender)
            
            return list(set(buyers)) # Unique buyers in this window
        except Exception as e:
            logger.error(f"Error fetching recent buyers for {pair_address}: {e}")
            return []

    async def detect_kol_signal(self, pair_address: str) -> dict:
        """
        Analyze recent buyers for KOL presence.
        Returns: {kol_count: int, is_kol_signal: bool, kols: list}
        """
        buyers = await self.get_recent_buyers(pair_address)
        found_kols = [b for b in buyers if b.lower() in self.smart_wallets]
        
        kol_count = len(found_kols)
        # Signal threshold: 2 or more Kols
        is_kol_signal = kol_count >= 2
        
        if kol_count > 0:
            logger.info(f"KOL Signal Detected! Count: {kol_count} | Wallets: {found_kols}")

        return {
            "kol_count": kol_count,
            "is_kol_signal": is_kol_signal,
            "kols": found_kols,
            "total_buyers": len(buyers)
        }
