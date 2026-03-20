from web3 import AsyncWeb3, AsyncHTTPProvider

def get_async_w3(rpc_url: str):
    """
    Returns an AsyncWeb3 instance initialized with the appropriate provider.
    """
    if rpc_url.startswith("ws"):
        from web3.providers import WebSocketProvider
        provider = WebSocketProvider(rpc_url)
    else:
        provider = AsyncHTTPProvider(rpc_url)
        
    return AsyncWeb3(provider)
