import os
import pandas as pd
import numpy as np
import logging
from src.ml.model import MomentumModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrainScript")

DATASET_PATH = "data/dataset.csv"

def train():
    """Load dataset, clean, and train the model."""
    if not os.path.exists(DATASET_PATH):
        logger.error(f"Dataset not found at {DATASET_PATH}")
        return

    try:
        # 1. Load Data
        df = pd.read_csv(DATASET_PATH)
        logger.info(f"Loaded {len(df)} rows from dataset.")
        
        if len(df) < 5:
            logger.warning("Dataset too small for meaningful training.")
            return

        # 2. Define Features (X)
        # Drop metadata columns and the safety/label columns
        feature_cols = [
            "liquidity_bnb", "market_cap", "buy_sell_ratio", 
            "volume_growth", "tx_count_growth", "holder_count"
        ]
        X = df[feature_cols].apply(pd.to_numeric, errors='coerce').fillna(0).values
        
        # 3. Define Labels (y)
        # We look for 'label_2x'. If all empty, we use 'is_safe' as a proxy for the demo 
        # or mock labels if needed.
        y = df["label_2x"].apply(pd.to_numeric, errors='coerce').fillna(0).values
        
        # If no real outcomes yet, use a simple heuristic: 
        # If liq > 5 and is_safe == 1, target = 1
        if (y == 0).all():
            logger.info("No outcomes detected. Using heuristic for pipeline demonstration.")
            y = ((df["liquidity_bnb"] > 5) & (df["is_safe"] == 1)).astype(int).values

        # 4. Train
        model = MomentumModel()
        model.train_model(X, y)
        
        logger.info("✅ Training complete! Model updated in data/model.json")
        
    except Exception as e:
        logger.error(f"Training failed: {e}")

if __name__ == "__main__":
    train()
