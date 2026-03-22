import logging
import time
from web3 import AsyncWeb3
from src.config.settings import ROUTER_ADDRESS, WBNB_ADDRESS, PRIVATE_KEY, WALLET_ADDRESS, SLIPPAGE_TOLERANCE_PERCENT

logger = logging.getLogger("RealTrader")

# Standard Uniswap V2 Router ABI for Swaps
ROUTER_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactETHForTokensSupportingFeeOnTransferTokens",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
        ],
        "name": "swapExactTokensForETHSupportingFeeOnTransferTokens",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

class RealTrader:
    def __init__(self, w3: AsyncWeb3):
        self.w3 = w3
        self.router_address = self.w3.to_checksum_address(ROUTER_ADDRESS)
        self.wbnb_address = self.w3.to_checksum_address(WBNB_ADDRESS)
        self.private_key = PRIVATE_KEY
        self.wallet_address = self.w3.to_checksum_address(WALLET_ADDRESS)
        
        self.router = self.w3.eth.contract(address=self.router_address, abi=ROUTER_ABI)

    async def buy_token(self, token_address: str, amount_bnb: float) -> str:
        """Execute a buy transaction on BSC."""
        if not self.private_key:
            logger.error("No private key found. Real trades disabled.")
            return None

        try:
            token_address = self.w3.to_checksum_address(token_address)
            amount_in_wei = self.w3.to_wei(amount_bnb, 'ether')
            
            # 1. Prepare Path
            path = [self.wbnb_address, token_address]
            
            # 2. Build Transaction
            nonce = await self.w3.eth.get_transaction_count(self.wallet_address)
            gas_price = await self.w3.eth.gas_price
            
            # Add a 10% premium to gas price for faster execution
            gas_price = int(gas_price * 1.1)

            tx = await self.router.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
                0, # amountOutMin (Set to 0 for maximum speed/volatility, user should adjust)
                path,
                self.wallet_address,
                int(time.time()) + 120 # 2 minute deadline
            ).build_transaction({
                'from': self.wallet_address,
                'value': amount_in_wei,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })

            # 3. Sign and Send
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"💰 Real Buy Executed! TX Hash: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logger.error(f"Failed to execute real buy: {e}")
            return None

    async def sell_token(self, token_address: str, token_balance_wei: int) -> str:
        """Execute a sell transaction on BSC."""
        if not self.private_key:
            return None

        try:
            token_address = self.w3.to_checksum_address(token_address)
            
            # 1. Prepare Path
            path = [token_address, self.wbnb_address]
            
            # 2. Build Transaction
            nonce = await self.w3.eth.get_transaction_count(self.wallet_address)
            gas_price = await self.w3.eth.gas_price
            gas_price = int(gas_price * 1.1)

            tx = await self.router.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                token_balance_wei,
                0, # amountOutMin
                path,
                self.wallet_address,
                int(time.time()) + 120
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 300000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })

            # 3. Sign and Send
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
            tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"💰 Real Sell Executed! TX Hash: {tx_hash.hex()}")
            return tx_hash.hex()

        except Exception as e:
            logger.error(f"Failed to execute real sell: {e}")
            return None
