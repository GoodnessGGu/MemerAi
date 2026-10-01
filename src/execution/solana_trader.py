import os
import json
import logging
import httpx
import base58
from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solana.rpc.async_api import AsyncClient

logger = logging.getLogger(__name__)

# Constants
SOL_MINT = "So11111111111111111111111111111111111111112"
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"
JUPITER_SWAP_API = "https://quote-api.jup.ag/v6/swap"

class SolanaTrader:
    """Automated Solana Trader utilizing Jupiter Aggregator V6 API."""
    
    def __init__(self, private_key_b58: str = None, rpc_url: str = "https://api.mainnet-beta.solana.com"):
        self.rpc_url = rpc_url
        self.client = AsyncClient(rpc_url)
        self.keypair = None
        self.public_key_str = ""
        
        if private_key_b58:
            try:
                # Private key can be base58 string or raw JSON byte array string
                if private_key_b58.startswith("[") and private_key_b58.endswith("]"):
                    secret_bytes = bytes(json.loads(private_key_b58))
                else:
                    secret_bytes = base58.b58decode(private_key_b58)
                    
                self.keypair = Keypair.from_bytes(secret_bytes)
                self.public_key_str = str(self.keypair.pubkey())
                logger.info(f"Solana Trader initialized for wallet: {self.public_key_str}")
            except Exception as e:
                logger.error(f"Failed to parse Solana private key: {e}")
                
    def is_wallet_connected(self) -> bool:
        return self.keypair is not None

    async def get_sol_balance(self) -> float:
        """Fetch SOL balance for the connected wallet."""
        if not self.keypair:
            return 0.0
        try:
            res = await self.client.get_balance(self.keypair.pubkey())
            lamports = res.value
            return lamports / 1e9
        except Exception as e:
            logger.error(f"Error fetching SOL balance: {e}")
            return 0.0

    async def execute_trade(
        self,
        token_mint: str,
        amount_sol: float,
        is_buy: bool = True,
        slippage_bps: int = 300 # 3.0% default slippage
    ) -> dict:
        """
        Executes a swap via Jupiter Aggregator V6.
        If is_buy=True: SOL -> Token
        If is_buy=False: Token -> SOL
        """
        if not self.keypair:
            return {
                "success": False,
                "tx_hash": None,
                "error": "Solana wallet not connected. Add SOLANA_PRIVATE_KEY to .env"
            }
            
        input_mint = SOL_MINT if is_buy else token_mint
        output_mint = token_mint if is_buy else SOL_MINT
        amount_lamports = int(amount_sol * 1e9) if is_buy else int(amount_sol)
        
        async with httpx.AsyncClient() as http:
            # 1. Fetch Quote from Jupiter
            quote_params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_lamports),
                "slippageBps": str(slippage_bps)
            }
            
            try:
                logger.info(f"Fetching Jupiter Quote: {input_mint[:6]}... -> {output_mint[:6]}... ({amount_sol} SOL)")
                quote_res = await http.get(JUPITER_QUOTE_API, params=quote_params, timeout=10.0)
                
                if quote_res.status_code != 200:
                    err_msg = f"Jupiter Quote API failed (status {quote_res.status_code}): {quote_res.text}"
                    logger.error(err_msg)
                    return {"success": False, "error": err_msg}
                    
                quote_data = quote_res.json()
                
                # 2. Request Swap Transaction from Jupiter
                swap_payload = {
                    "quoteResponse": quote_data,
                    "userPublicKey": self.public_key_str,
                    "wrapAndUnwrapSol": True,
                    "dynamicComputeUnitLimit": True,
                    "prioritizationFeeLamports": "auto"
                }
                
                swap_res = await http.post(JUPITER_SWAP_API, json=swap_payload, timeout=15.0)
                if swap_res.status_code != 200:
                    err_msg = f"Jupiter Swap API failed (status {swap_res.status_code}): {swap_res.text}"
                    logger.error(err_msg)
                    return {"success": False, "error": err_msg}
                    
                swap_data = swap_res.json()
                swap_tx_b64 = swap_data.get("swapTransaction")
                
                if not swap_tx_b64:
                    return {"success": False, "error": "No swapTransaction returned by Jupiter API"}
                    
                # 3. Deserialize & Sign Versioned Transaction
                raw_tx_bytes = base58.b58decode(swap_tx_b64) if not swap_tx_b64.startswith("A") else httpx.codes
                # Standard base64 decoding for Jupiter transactions
                import base64
                raw_tx_bytes = base64.b64decode(swap_tx_b64)
                
                tx = VersionedTransaction.from_bytes(raw_tx_bytes)
                
                # Sign transaction with wallet keypair
                signature = self.keypair.sign_message(tx.message.to_bytes())
                signed_tx = VersionedTransaction.populate(tx.message, [signature])
                
                # 4. Broadcast to Solana RPC
                logger.info("Broadcasting signed transaction to Solana mainnet...")
                tx_res = await self.client.send_transaction(signed_tx)
                tx_hash = str(tx_res.value)
                
                logger.info(f"✅ Solana Swap Executed Successfully! Tx: https://solscan.io/tx/{tx_hash}")
                return {
                    "success": True,
                    "tx_hash": tx_hash,
                    "solscan_url": f"https://solscan.io/tx/{tx_hash}"
                }
                
            except Exception as e:
                logger.error(f"Error executing Solana swap: {e}")
                return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Quick Test
    async def test():
        trader = SolanaTrader()
        print("Solana Trader loaded. Connected:", trader.is_wallet_connected())
        
    import asyncio
    asyncio.run(test())
