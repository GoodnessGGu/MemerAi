import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def check_balance():
    wallet_address = os.getenv("WALLET_ADDRESS", "0x533c8307c6e20c66d8Ab8A7BA2AdCFFA76E9821a")
    
    # Try several reliable RPCs
    rpcs = [
        "https://binance.llamarpc.com",
        "https://1rpc.io/bnb",
        "https://bsc-dataseed.binance.org/",
        "https://bsc.publicnode.com",
        "https://rpc.ankr.com/bsc"
    ]
    
    headers = {'Content-Type': 'application/json'}
    
    for rpc_url in rpcs:
        print(f"Connecting to {rpc_url}...")
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [wallet_address, "latest"],
            "id": 1
        }
        try:
            response = requests.post(rpc_url, headers=headers, data=json.dumps(payload), timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if "result" in data:
                balance_hex = data["result"]
                balance_wei = int(balance_hex, 16)
                balance_bnb = balance_wei / 10**18
                
                print("\n" + "="*40)
                print(f"Node:    {rpc_url}")
                print(f"Wallet:  {wallet_address}")
                print(f"Balance: {balance_bnb:.6f} BNB")
                print("="*40 + "\n")
                return
            else:
                print(f"Error in RPC response from {rpc_url}: {data}")
        except Exception as e:
            print(f"Failed to get balance from {rpc_url}: {e}")
            
    print("All providers failed.")

if __name__ == "__main__":
    check_balance()
