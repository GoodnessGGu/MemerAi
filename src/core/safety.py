import logging
import httpx
from web3 import AsyncWeb3
from src.utils.web3_utils import get_async_w3
import src.config.settings as settings
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

async def check_token_safety(token_address: str, pair_address: str = None, client: httpx.AsyncClient = None, w3: AsyncWeb3 = None) -> dict:
    """
    Query GoPlus API for token safety metrics and perform LP lock checks.
    """
    url = f"{GOPLUS_URL}/{CHAIN_ID}?contract_addresses={token_address}"
    
    result = {
        "is_safe": False,
        "risk_flags": [],
        "meta": "Generic"
    }
    
    try:
        # Use provided client or create temporary one (better to provide it)
        if client is None:
            async with httpx.AsyncClient() as temp_client:
                response = await temp_client.get(url, timeout=10.0)
        else:
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
            
        # NARRATIVE DETECTION
        name = token_info.get("token_name", "").upper()
        symbol = token_info.get("token_symbol", "").upper()
        if any(x in name or x in symbol for x in ["ELON", "MUSK", "MARS", "XAI"]): result["meta"] = "Elon Meta 🚀"
        elif any(x in name or x in symbol for x in ["GPT", "AI", "BOT", "NEURAL"]): result["meta"] = "AI Meta 🧠"
        elif any(x in name or x in symbol for x in ["DOGE", "SHIB", "PEPE", "FLOKI", "MOODENG", "PNUT", "CHILLGUY", "NEIRO"]): result["meta"] = "Meme Meta 🐸"
        elif any(x in name or x in symbol for x in ["MOON", "SAFE", "GALAXY"]): result["meta"] = "Space Meta 🌌"
        elif any(x in name or x in symbol for x in ["HALLOWEEN", "PUMPKIN", "SPOOKY", "GHOST", "WEEN", "HAUNT", "WITCH"]): result["meta"] = "Halloween Meta 🎃"
        elif any(x in name or x in symbol for x in ["CZ", "BINANCE", "BNB"]): result["meta"] = "Binance/CZ Meta 💛"
        elif any(x in name or x in symbol for x in ["TRUMP", "HARRIS", "BIDEN", "VOTE", "USA", "ELECTION"]): result["meta"] = "PolitiFi Meta 🇺🇸"
        elif any(x in name or x in symbol for x in ["HAALAND", "CR7", "MESSI", "FOOTBALL", "SOCCER"]): result["meta"] = "Sports Meta ⚽"

        # PERFORM HEURISTICS CHECKS
        fatal_risks = []
        warning_risks = []

        # 1. Fatal Risks (Immediate Rug/Scam)
        if token_info.get("is_honeypot") == "1": fatal_risks.append("is_honeypot")
        if token_info.get("cannot_sell_all") == "1": fatal_risks.append("cannot_sell_all")
        if token_info.get("is_blacklisted") == "1": fatal_risks.append("has_blacklist")
        
        # 2. Warning Risks (High Risk but tradable in simulation)
        if token_info.get("is_mintable") == "1": warning_risks.append("is_mintable")
        
        # 3. Trading Taxes
        try:
            buy_tax = float(token_info.get("buy_tax", "0") or "0") * 100
            sell_tax = float(token_info.get("sell_tax", "0") or "0") * 100
            if buy_tax > 50: fatal_risks.append(f"fatal_buy_tax_{buy_tax:.0f}%")
            elif buy_tax > MAX_BUY_TAX: warning_risks.append(f"high_buy_{buy_tax:.0f}%")
            
            if sell_tax > 50: fatal_risks.append(f"fatal_sell_tax_{sell_tax:.0f}%")
            elif sell_tax > MAX_SELL_TAX: warning_risks.append(f"high_sell_{sell_tax:.0f}%")
        except Exception: warning_risks.append("tax_err")

        # 4. Holder Concentration (Warning only)
        holders = token_info.get("holders", [])
        for h in holders[:3]:
            h_addr = h.get("address", "").lower()
            h_pct = float(h.get("percent", "0")) * 100
            if h_addr not in [addr.lower() for addr in BURN_ADDRESSES] and h_pct > 25:
                warning_risks.append(f"whale_{h_pct:.0f}%")

        # 5. LP Lock & Burn Check (GoPlus + On-chain)
        goplus_locked_pct = 0.0
        lp_holders = token_info.get("lp_holders", [])
        for h in lp_holders:
            try:
                is_locked = int(h.get("is_locked", 0))
                addr = h.get("address", "").lower()
                pct = float(h.get("percent", 0) or 0) * 100
                if is_locked == 1 or addr in [b.lower() for b in BURN_ADDRESSES]:
                    goplus_locked_pct += pct
            except Exception:
                continue

        onchain_lp_pct = 0.0
        if pair_address and w3:
            lp_res = await check_lp_lock(w3, pair_address)
            onchain_lp_pct = lp_res["percent"]
            
        effective_lp_lock_pct = max(goplus_locked_pct, onchain_lp_pct)
        result["lp_lock_percent"] = effective_lp_lock_pct

        min_lock_required = getattr(settings, "MIN_LP_LOCK_PERCENT", 80.0)
        require_lock = getattr(settings, "REQUIRE_LOCKED_LP", True)

        if require_lock and effective_lp_lock_pct < min_lock_required:
            fatal_risks.append(f"unlocked_lp_{effective_lp_lock_pct:.0f}%_min_{min_lock_required:.0f}%")
        elif effective_lp_lock_pct < 50:
            warning_risks.append(f"low_lp_lock_{effective_lp_lock_pct:.0f}%")

        # Overall result
        result["risk_flags"] = fatal_risks + warning_risks
        result["fatal_count"] = len(fatal_risks)
        result["warning_count"] = len(warning_risks)
        result["is_safe"] = len(fatal_risks) == 0

        return result

    except httpx.RequestError as exc:
        logger.error(f"HTTP exception while requesting GoPlus: {exc}")
        result["risk_flags"].append("http_exception")
        return result
    except Exception as e:
        logger.error(f"Error checking token safety: {e}")
        result["risk_flags"].append("exception")
        return result
