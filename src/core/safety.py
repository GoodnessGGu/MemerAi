import logging
import httpx
from web3 import AsyncWeb3
from src.utils.web3_utils import get_async_w3
from src.config.settings import MAX_BUY_TAX, MAX_SELL_TAX, RPC_URL

logger = logging.getLogger(__name__)

# BSC Chain ID for GoPlus
CHAIN_ID = "56"
GOPLUS_URL = "https://api.gopluslabs.io/api/v1/token_security"

# Burn Addresses
BURN_ADDRESSES = [
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dEaD"
]

# Minimal ABI for LP Token supply/balance
LP_ABI = [
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
]

async def check_lp_lock(w3: AsyncWeb3, pair_address: str) -> dict:
    """Check if LP tokens are burnt or locked."""
    try:
        lp_contract = w3.eth.contract(address=w3.to_checksum_address(pair_address), abi=LP_ABI)
        total_supply = await lp_contract.functions.totalSupply().call()
        
        if total_supply == 0:
            return {"is_locked": False, "percent": 0.0}
            
        burnt_amount = 0
        for addr in BURN_ADDRESSES:
            try:
                balance = await lp_contract.functions.balanceOf(w3.to_checksum_address(addr)).call()
                burnt_amount += balance
            except Exception: continue
            
        percent_burnt = (burnt_amount / total_supply) * 100
        return {
            "is_locked": percent_burnt > 90, # Threshold 90%
            "percent": percent_burnt
        }
    except Exception as e:
        logger.error(f"Error checking LP lock: {e}")
        return {"is_locked": False, "percent": 0.0}

async def check_token_safety(token_address: str, pair_address: str = None) -> dict:
    """
    Query GoPlus API for token safety metrics and perform LP lock checks.
    """
    url = f"{GOPLUS_URL}/{CHAIN_ID}?contract_addresses={token_address}"
    
    result = {
        "is_safe": False,
        "risk_flags": []
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            
            if response.status_code != 200:
                result["risk_flags"].append("api_error")
                return result
                
            data = response.json()
            if data.get("code") != 1 or not data.get("result"):
                result["risk_flags"].append("no_data")
                return result
                
            token_info = data["result"].get(token_address.lower(), {})
            if not token_info:
                result["risk_flags"].append("not_found")
                return result
                
            # PERFORM HEURISTICS CHECKS
            
            # 1. Critical Risks
            if token_info.get("is_honeypot") == "1": result["risk_flags"].append("is_honeypot")
            if token_info.get("is_mintable") == "1": result["risk_flags"].append("is_mintable")
            if token_info.get("cannot_sell_all") == "1": result["risk_flags"].append("cannot_sell_all")
            if token_info.get("is_blacklisted") == "1": result["risk_flags"].append("has_blacklist")
                
            # 2. Trading Taxes
            try:
                buy_tax = float(token_info.get("buy_tax", "0") or "0") * 100
                sell_tax = float(token_info.get("sell_tax", "0") or "0") * 100
                if buy_tax > MAX_BUY_TAX: result["risk_flags"].append(f"high_buy_tax_{buy_tax}%")
                if sell_tax > MAX_SELL_TAX: result["risk_flags"].append(f"high_sell_tax_{sell_tax}%")
            except Exception: result["risk_flags"].append("tax_parse_err")

            # 3. Holder Concentration (Whale Detection)
            holders = token_info.get("holders", [])
            for h in holders[:3]: # Check top 3 holders
                h_addr = h.get("address", "").lower()
                h_pct = float(h.get("percent", "0")) * 100
                # Ignore burn addresses and the pair itself if known (often pair is top holder)
                if h_addr not in [addr.lower() for addr in BURN_ADDRESSES] and h_pct > 15:
                    # Note: We can't easily know the pair address here without more logic, 
                    # but usually, >15% on a non-burn address for a new token is a red flag.
                    result["risk_flags"].append(f"whale_holder_{h_pct:.1f}%")

            # 4. LP Lock Check (On-chain)
            if pair_address:
                w3 = get_async_w3(RPC_URL)
                lp_res = await check_lp_lock(w3, pair_address)
                if not lp_res["is_locked"]:
                    result["risk_flags"].append(f"lp_unlocked_{lp_res['percent']:.1f}%")
                
            # Determine overall safety
            if len(result["risk_flags"]) == 0:
                result["is_safe"] = True
                
            return result
            
    except Exception as e:
        logger.error(f"Error checking token safety: {e}")
        result["risk_flags"].append("exception")
        return result
            
    except httpx.RequestError as exc:
        logger.error(f"HTTP exception while requesting GoPlus: {exc}")
        result["risk_flags"].append("http_exception")
        return result
    except Exception as e:
        logger.error(f"Error checking token safety: {e}")
        result["risk_flags"].append("exception")
        return result
