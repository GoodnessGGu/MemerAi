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

    async def extract_features(self, token_address: str, pair_address: str) -> List[float]:
        """
        Extracts trading features for the ML model.
        Returns a feature vector (list of floats).
        """
        logger.info(f"Extracting features for Token: {token_address} | Pair: {pair_address}")
        
        try:
            pair_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pair_address), 
                abi=PAIR_ABI
            )
            
            # Fetch reserves asynchronously
            reserves = await pair_contract.functions.getReserves().call()
            token0 = await pair_contract.functions.token0().call()
            
            # Determine which reserve is WBNB (liquidity approximation)
            if token0 == self.wbnb_address:
                wbnb_reserve = reserves[0]
                token_reserve = reserves[1]
            else:
                wbnb_reserve = reserves[1]
                token_reserve = reserves[0]

            # Convert to standard format (BNB has 18 decimals)
            liquidity_bnb = wbnb_reserve / (10**18)
            
            # Note: For MVP, fully calculating volume growth, buy/sell ratio, and holder count
            # in real time requires querying recent swap events and token transfer events.
            # We insert placeholders for complex metrics that would be continually updated.
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
                float(holder_count)
            ]
            
            return feature_vector
            
        except Exception as e:
            logger.error(f"Error extracting features for {pair_address}: {e}")
    async def get_token_price_bnb(self, pair_address: str) -> float:
        """
        Returns the current price of the token in BNB based on the pair's reserves.
        """
        try:
            pair_contract = self.w3.eth.contract(
                address=self.w3.to_checksum_address(pair_address), 
                abi=PAIR_ABI
            )
            reserves = await pair_contract.functions.getReserves().call()
            token0 = await pair_contract.functions.token0().call()
            
            if token0 == self.wbnb_address:
                wbnb_reserve = reserves[0]
                token_reserve = reserves[1]
            else:
                wbnb_reserve = reserves[1]
                token_reserve = reserves[0]

            if token_reserve == 0: return 0.0
            
            # Price = BNB / Token
            return float(wbnb_reserve / token_reserve)
        except Exception as e:
            logger.error(f"Error getting price for {pair_address}: {e}")
            return 0.0
