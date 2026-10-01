import asyncio
from asyncio import subprocess
import json
import logging
import os
import shutil

logger = logging.getLogger(__name__)

class GMGNClient:
    """Wrapper around the GMGN OpenAPI CLI to fetch token data."""
    def __init__(self):
        # We use the local patched skills directory
        self.skills_path = os.path.join(os.getcwd(), "temp_gmgn_skills")
        self.index_ts = os.path.join(self.skills_path, "src", "index.ts")
            
    async def _run_command(self, *args) -> dict:
        """Runs a gmgn-cli command with --raw and parses JSON output."""
        try:
            # Detected OS to use correct npx command
            npx_cmd = "npx.cmd" if os.name == "nt" else "npx"
            if not shutil.which(npx_cmd):
                logger.debug(f"GMGN CLI disabled: '{npx_cmd}' not found in system PATH.")
                return {}
            full_args = [npx_cmd, "tsx", self.index_ts] + list(args) + ["--raw"]
            
            # Subprocess
            process = await asyncio.create_subprocess_exec(
                *full_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.skills_path
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"GMGN CLI Error: {stderr.decode().strip() or stdout.decode().strip()}")
                return {}
                
            try:
                # The output should be a single JSON string if --raw is used
                return json.loads(stdout.decode().strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse GMGN JSON output: {e}. Output was: {stdout.decode()[:200]}")
                return {}
                
        except Exception as e:
            logger.error(f"Error running GMGN command '{' '.join(args)}': {e}")
            return {}

    async def get_trending_tokens(self, chain: str = "bsc", interval: str = "1h", limit: int = 50, orderby: str = "swaps", direction: str = "desc") -> list:
        """Get trending tokens (sniper feed). Returns a list of dicts."""
        logger.debug(f"Fetching GMGN trending tokens on {chain} (interval: {interval}, orderby: {orderby})")
        # Example API: gmgn-cli market trending --chain bsc --interval 5m --limit 50
        data = await self._run_command(
            "market", "trending", 
            "--chain", chain, 
            "--interval", interval, 
            "--limit", str(limit),
            "--order-by", orderby,
            "--direction", direction
        )
        # Data is a dict where the trending array is usually under a specific key, 
        # or it might directly be an array depending on the API schema.
        # Actually gmgm-skills usually outputs the Array directly if parsing raw response.data
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            inner_data = data.get("data")
            # If the envelope contains {"data": {"rank": [...]}}
            if isinstance(inner_data, dict) and "rank" in inner_data:
                return inner_data["rank"]
            # If the envelope contains {"data": [...]} 
            if isinstance(inner_data, list):
                return inner_data
            # If wrapped directly like {"rank": [...]}
            if "rank" in data and isinstance(data["rank"], list):
                return data["rank"]
        return []

    async def get_token_info(self, chain: str, address: str) -> dict:
        """Fetch smart money, price, and token info."""
        data = await self._run_command("token", "info", "--chain", chain, "--address", address)
        return data if isinstance(data, dict) else {}

    async def get_token_security(self, chain: str, address: str) -> dict:
        """Fetch security/rug pull metrics."""
        data = await self._run_command("token", "security", "--chain", chain, "--address", address)
        return data if isinstance(data, dict) else {}

if __name__ == "__main__":
    # Test execution
    async def test():
        logging.basicConfig(level=logging.DEBUG)
        client = GMGNClient()
        tokens = await client.get_trending_tokens(chain="bsc", interval="1h", limit=3)
        print("Trending Tokens:", json.dumps(tokens, indent=2))
    
    asyncio.run(test())
