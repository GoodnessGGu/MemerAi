import logging
from typing import List
from web3 import AsyncWeb3
from src.config.settings import WBNB_ADDRESS

logger = logging.getLogger(__name__)

PAIR_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "getReserves",
        "outputs": [
            {"internalType": "uint112", "name": "_reserve0", "type": "uint112"},
            {"internalType": "uint112", "name": "_reserve1", "type": "uint112"},
            {"internalType": "uint32", "name": "_blockTimestampLast", "type": "uint32"}
        ],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function"
    }
]

# ERC20 ABI for Basic Metadata
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"}
]

class FeatureExtractor:
    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3
        self.wbnb_address = self.w3.to_checksum_address(WBNB_ADDRESS)
        self.usdt_address = self.w3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955")

    async def get_token_metadata(self, token_address: str) -> dict:
        """Fetch token name and symbol."""
        try:
            token_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            name = await token_contract.functions.name().call()
            symbol = await token_contract.functions.symbol().call()
            return {"name": name, "symbol": symbol}
        except Exception:
            # Fallback if contract doesn't implement name/symbol correctly
            return {"name": "Unknown", "symbol": "UNK"}

    async def extract_features(self, token_address: str, pair_address: str, kol_signal: dict = None) -> List[float]:
        """
        Extracts trading features for the ML model with optional KOL signal integration.
        Returns a feature vector (list of floats).
        """
        logger.info(f"Extracting features for Token: {token_address} | Pair: {pair_address}")
        kol_signal = kol_signal or {}
        kol_count = float(kol_signal.get("kol_count", 0) or 0)
        total_buyers = float(kol_signal.get("total_buyers", 1) or 1)  # Prevent div by zero
        kol_buy_ratio = kol_count / max(1.0, total_buyers)
        
        if not pair_address or pair_address == "0x0000000000000000000000000000000000000000":
            # If GMGN provides metrics, estimate the BNB values for the decision engine
            liq_usd = float(
                kol_signal.get("gmgn_liquidity_usd")
                or kol_signal.get("liquidity_usd")
                or 0
            )
            mc_usd = float(kol_signal.get("gmgn_marketcap_usd", 0) or 0)
            bnb_price = await self.get_bnb_price()
            liq_bnb = liq_usd / bnb_price if bnb_price > 0 else 0.0
            mc_bnb = mc_usd / bnb_price if bnb_price > 0 else 0.0
            
            # Ensure minimum liquidity so strong GMGN signals don't get rejected simply for missing LP addr
            if kol_count >= 2 and liq_bnb == 0:
                liq_bnb = 10.0  # Fake threshold bypass
                
            return [liq_bnb, mc_bnb, 1.0, 0.0, 0.0, 1.0, kol_count, 0.0, kol_buy_ratio]
            
        try:
            pair_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pair_address), 
                abi=PAIR_ABI
            )
            
            # Fetch reserves asynchronously
            reserves = await pair_contract.functions.getReserves().call()
            token0 = await pair_contract.functions.token0().call()
            token0_checksum = self.w3.to_checksum_address(token0)
            
            is_usdt = False
            if token0_checksum == self.wbnb_address:
                base_reserve = reserves[0]
                token_reserve = reserves[1]
            elif token0_checksum == self.usdt_address:
                base_reserve = reserves[0]
                token_reserve = reserves[1]
                is_usdt = True
            else:
                try:
                    token1 = await pair_contract.functions.token1().call()
                    token1_checksum = self.w3.to_checksum_address(token1)
                except Exception:
                    token1_checksum = None
                
                if token1_checksum == self.usdt_address:
                    base_reserve = reserves[1]
                    token_reserve = reserves[0]
                    is_usdt = True
                else:
                    base_reserve = reserves[1]
                    token_reserve = reserves[0]

            # Convert to standard format (BNB and USDT have 18 decimals)
            base_amount = base_reserve / (10**18)
            if is_usdt:
                bnb_price = await self.get_bnb_price()
                liquidity_bnb = base_amount / bnb_price if bnb_price > 0 else base_amount / 600.0
            else:
                liquidity_bnb = base_amount
            
            # KOL specific features
            avg_kol_buy = 0.0 # Placeholder for future deep analysis
            
            market_cap = liquidity_bnb * 2  # Naive approximation
            buy_sell_ratio = 1.0            # Placeholder
            volume_growth = 0.0             # Placeholder
            tx_count_growth = 0.0           # Placeholder
            holder_count = 1.0              # Placeholder
            
            feature_vector = [
                float(liquidity_bnb),
                float(market_cap),
                float(buy_sell_ratio),
                float(volume_growth),
                float(tx_count_growth),
                float(holder_count),
                kol_count,
                avg_kol_buy,
                kol_buy_ratio
            ]
            
            return feature_vector
            
        except Exception as e:
            logger.error(f"Error extracting features for {pair_address}: {e}")
            return [0.0, 0.0, 1.0, 0.0, 0.0, 1.0, kol_count, 0.0, kol_buy_ratio]

    async def get_token_price_bnb(self, pair_address: str) -> float:
        """Fetch token price in BNB from PancakeSwap V2 or DexScreener for Solana."""
        if not pair_address or not pair_address.startswith("0x"):
            # Fetch real-time price via DexScreener for Solana / non-EVM tokens
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{pair_address}"
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        pairs = data.get("pairs") or []
                        if pairs and len(pairs) > 0:
                            price_usd = float(pairs[0].get("priceUsd") or 0)
                            mcap = float(pairs[0].get("marketCap") or 0)
                            if price_usd > 0:
                                return price_usd
                            elif mcap > 0:
                                return mcap
            except Exception as e:
                logger.warning(f"DexScreener price fetch error for {pair_address[:8]}: {e}")
            return 1.0 
        try:
            pair_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pair_address), 
                abi=PAIR_ABI
            )
            reserves = await pair_contract.functions.getReserves().call()
            token0 = await pair_contract.functions.token0().call()
            token0_checksum = self.w3.to_checksum_address(token0)
            
            is_usdt = False
            if token0_checksum == self.wbnb_address:
                base_reserve = reserves[0]
                token_reserve = reserves[1]
            elif token0_checksum == self.usdt_address:
                base_reserve = reserves[0]
                token_reserve = reserves[1]
                is_usdt = True
            else:
                try:
                    token1 = await pair_contract.functions.token1().call()
                    token1_checksum = self.w3.to_checksum_address(token1)
                except Exception:
                    token1_checksum = None
                
                if token1_checksum == self.usdt_address:
                    base_reserve = reserves[1]
                    token_reserve = reserves[0]
                    is_usdt = True
                else:
                    base_reserve = reserves[1]
                    token_reserve = reserves[0]

            if token_reserve == 0: return 0.0
            
            # Price = Base / Token
            price_base = float(base_reserve / token_reserve)
            if is_usdt:
                bnb_price = await self.get_bnb_price()
                return price_base / bnb_price if bnb_price > 0 else price_base / 600.0
            else:
                return price_base
        except Exception as e:
            logger.error(f"Error getting price for {pair_address}: {e}")
            return 0.0

    async def get_bnb_price(self) -> float:
        """Fetch current BNB price in USDT from PancakeSwap V2."""
        try:
            # WBNB/USDT Pair on BSC V2
            usdt_pair = "0x16b9a82891338f9bA80E2D6970FddA79D1eb0daE"
            # ABI for getReserves
            pair_abi = [{"constant":True,"inputs":[],"name":"getReserves","outputs":[{"internalType":"uint112","name":"_reserve0","type":"uint112"},{"internalType":"uint112","name":"_reserve1","type":"uint112"},{"internalType":"uint32","name":"_blockTimestampLast","type":"uint32"}],"payable":False,"type":"function"}]
            
            contract = self.w3.eth.contract(address=self.w3.to_checksum_address(usdt_pair), abi=pair_abi)
            reserves = await contract.functions.getReserves().call()
            
            # USDT is reserve0, WBNB is reserve1 on this pair (lexicographically: USDT 0x55 < WBNB 0xbb)
            price = (reserves[0] / 10**18) / (reserves[1] / 10**18)
            return float(price)
        except Exception as e:
            logger.error(f"Failed to fetch BNB price: {e}")
            return 600.0 # Fallback
