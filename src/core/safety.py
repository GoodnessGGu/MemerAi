import httpx
import logging
from src.config.settings import MAX_BUY_TAX, MAX_SELL_TAX

logger = logging.getLogger(__name__)

# BSC Chain ID for GoPlus
CHAIN_ID = "56"
GOPLUS_URL = "https://api.gopluslabs.io/api/v1/token_security"

async def check_token_safety(token_address: str) -> dict:
    """
    Query GoPlus API for token safety metrics on BSC.
    Returns a dictionary with safety status and any detected risk flags.
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
                logger.error(f"GoPlus API error: {response.status_code}")
                result["risk_flags"].append("api_error")
                return result
                
            data = response.json()
            if data.get("code") != 1 or not data.get("result"):
                logger.warning(f"No GoPlus data for {token_address}")
                # Sometimes brand new tokens aren't indexed yet, we flag as no_data
                result["risk_flags"].append("no_data")
                return result
                
            token_info = data["result"].get(token_address.lower(), {})
            if not token_info:
                result["risk_flags"].append("not_found")
                return result
                
            # Perform Heuristics Checks
            
            # 1. Is Honeypot?
            if token_info.get("is_honeypot") == "1":
                result["risk_flags"].append("is_honeypot")
                
            # 2. Mintable?
            if token_info.get("is_mintable") == "1":
                result["risk_flags"].append("is_mintable")
                
            # 3. Can Sell All?
            if token_info.get("cannot_sell_all") == "1":
                result["risk_flags"].append("cannot_sell_all")
                
            # 4. Blacklist Function?
            if token_info.get("is_blacklisted") == "1":
                result["risk_flags"].append("has_blacklist")
                
            # 5. Trading Taxes
            # Convert string representations like "0.05" (which might imply 5%) correctly
            # GoPlus returns exact fractions: "0.05" == 5%
            try:
                buy_tax = float(token_info.get("buy_tax", "1.0") or "1.0")
                sell_tax = float(token_info.get("sell_tax", "1.0") or "1.0")
                
                # Check absolute maximum allowed taxes (e.g. 15%)
                if buy_tax * 100 > MAX_BUY_TAX:
                    result["risk_flags"].append(f"high_buy_tax_{buy_tax*100}%")
                if sell_tax * 100 > MAX_SELL_TAX:
                    result["risk_flags"].append(f"high_sell_tax_{sell_tax*100}%")
            except ValueError:
                result["risk_flags"].append("parse_tax_error")

            # 6. Proxy Contract Risk
            if token_info.get("is_proxy") == "1":
                result["risk_flags"].append("is_proxy_contract")
                
            # Determine overall safety
            if len(result["risk_flags"]) == 0:
                result["is_safe"] = True
                
            return result
            
    except httpx.RequestError as exc:
        logger.error(f"HTTP exception while requesting GoPlus: {exc}")
        result["risk_flags"].append("http_exception")
        return result
    except Exception as e:
        logger.error(f"Error checking token safety: {e}")
        result["risk_flags"].append("exception")
        return result
