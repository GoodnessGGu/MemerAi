import asyncio
import logging
import sys
from web3 import AsyncWeb3
import src.config.settings as settings

from src.core.listener import BlockchainListener
from src.core.safety import check_token_safety
from src.core.features import FeatureExtractor
from src.core.decision import DecisionEngine
from src.ml.model import MomentumModel
from src.data.logger import DataLogger
from src.utils.web3_utils import get_async_w3

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("MainOrchestrator")

async def main():
    logger.info("Initializing Memer AI Core MVP...")
    
    # Initialize components
    w3 = get_async_w3(settings.RPC_URL)
    feature_extractor = FeatureExtractor(w3)
    decision_engine = DecisionEngine()
    model = MomentumModel()
    data_logger = DataLogger("dataset.csv")

    async def process_new_pair(pair_data: dict):
        token_address = pair_data.get("token_address")
        pair_address = pair_data.get("pair_address")
        
        try:
            # 1. Safety Check
            safety_result = await check_token_safety(token_address)
            is_safe = safety_result.get("is_safe", False)
            
            # 2. Extract Features
            features = await feature_extractor.extract_features(token_address, pair_address)
            
            # 3. Predict Probability
            ml_probability = model.predict(features)
            
            # 4. Log Data
            data_logger.log_features(token_address, pair_address, features, is_safe)
            
            # 5. Make Decision
            decision = decision_engine.make_decision(safety_result, features, ml_probability)
            
            if decision:
                logger.info(f"🚀 Execution triggered for token {token_address} (Phase 2 placeholder)")
                # Phase 2: await trader.execute_trade(...)
                
        except Exception as e:
            logger.error(f"Error processing pair {pair_address}: {e}")

    # Start Blockchain Listener
    listener = BlockchainListener(w3=w3, callback=process_new_pair)
    
    try:
        await listener.start()
    except KeyboardInterrupt:
        logger.info("Gracefully shutting down.")
        listener.stop()

if __name__ == "__main__":
    asyncio.run(main())
