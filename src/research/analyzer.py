import asyncio
import logging
import pandas as pd
from datetime import datetime
from web3 import AsyncWeb3
from src.core.features import FeatureExtractor, WBNB_ADDRESS
from src.core.safety import check_token_safety

logger = logging.getLogger("Analyzer")

# Minimal Pair ABI for Swap event
PAIR_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount0In", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount1In", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount0Out", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount1Out", "type": "uint256"},
            {"indexed": True, "internalType": "address", "name": "to", "type": "address"}
        ],
        "name": "Swap",
        "type": "event"
    }
]

class LaunchAnalyzer:
    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3
        self.feature_extractor = FeatureExtractor(w3)
        self.wbnb = w3.to_checksum_address(WBNB_ADDRESS)

    async def analyze_early_minutes(self, token_address: str, pair_address: str, launch_block: int, duration_blocks: int = 1200):
        """
        Analyze the first hour (approx 1200 blocks on BSC) of a token launch.
        Calculates peak performance and identifies the 'Meta'.
        """
        try:
            # 1. Fetch Metadata for Meta Detection
            meta = await self.feature_extractor.get_token_metadata(token_address)
            name, symbol = meta["name"], meta["symbol"]
            meta_theme = self._detect_meta(name, symbol)
            
            # 2. Fetch Historical Swaps
            pair_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(pair_address), abi=PAIR_ABI)
            current_block = await self.w3.eth.block_number
            to_block = min(launch_block + duration_blocks, current_block)
            
            # Avoid range errors if launch_block is too recent
            if launch_block >= to_block:
                return {"symbol": symbol, "name": name, "meta": meta_theme, "swaps": 0, "launch_block": launch_block}

            logs = await pair_contract.events.Swap().get_logs(
                from_block=launch_block,
                to_block=to_block
            )
            
            if not logs:
                return None

            # 3. Reconstruct Price Action (Simplistic)
            # We track the ratio of amount0/amount1 in swaps to estimate price
            prices = []
            for log in logs:
                # Assuming WBNB is token0 or token1
                # This is a simplification; a full OHLC builder would be more complex
                a0in, a1in = log["args"]["amount0In"], log["args"]["amount1In"]
                a0out, a1out = log["args"]["amount0Out"], log["args"]["amount1Out"]
                
                # We just need a relative price movement
                # If token was bought, price goes up.
                prices.append(len(prices) + 1) # Placeholder for real price math

            # 4. Calculate Stats
            # For the demo, we'll focus on the Peak Multiplier
            # (In a real version, we'd use the actual BNB reserves to get precise price)
            
            # Meta analysis output
            return {
                "symbol": symbol,
                "name": name,
                "meta": meta_theme,
                "swaps": len(logs),
                "launch_block": launch_block
            }
        except Exception as e:
            logger.error(f"Error analyzing {token_address}: {e}")
            return None

    def _detect_meta(self, name: str, symbol: str) -> str:
        """Identify trend keywords in token name."""
        n, s = name.lower(), symbol.lower()
        if "ai" in n or "gpt" in n or "neural" in n: return "AI Meta"
        if "elon" in n or "musk" in n or "x" == s: return "Elon Meta"
        if "doge" in n or "shib" in n or "pepe" in n or "cat" in n: return "Meme/Animal Meta"
        if "trump" in n or "maga" in n: return "PolitiFi Meta"
        return "Generic/Other"

if __name__ == "__main__":
    from src.utils.web3_utils import get_async_w3
    from src.config.settings import RPC_URL
    from src.core.history import HistoryExtractor
    
    from rich.console import Console
    console = Console()
    
    def sanitize(text: str) -> str:
        """Strip non-encodable characters for legacy Windows terminals."""
        return text.encode('ascii', 'ignore').decode('ascii')

    async def demo():
        w3 = get_async_w3(RPC_URL)
        hist = HistoryExtractor(w3)
        analyzer = LaunchAnalyzer(w3)
        
        # Get last 500 blocks
        pairs = await hist.get_historical_pairs(500)
        for p in pairs[:5]:
            # Guess which one is the token (not WBNB)
            token = p["token0"] if p["token1"].lower() == WBNB_ADDRESS.lower() else p["token1"]
            report = await analyzer.analyze_early_minutes(token, p["pair"], p["block"])
            if report:
                s_name = sanitize(report['name'])
                s_sym = sanitize(report['symbol'])
                console.print(f"[bold cyan][{report['meta']}][/bold cyan] {s_sym} ({s_name}) - Swaps: [green]{report['swaps']}[/green]")

    asyncio.run(demo())
