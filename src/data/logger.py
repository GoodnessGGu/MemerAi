import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DataLogger:
    def __init__(self, filepath="dataset.csv"):
        # Put the dataset at the root of the project or in a specific data dir
        self.filepath = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", filepath)
        self.headers = [
            "timestamp", "token_address", "pair_address", 
            "liquidity_bnb", "market_cap", "buy_sell_ratio", 
            "volume_growth", "tx_count_growth", "holder_count",
            "is_safe", "label_2x"
        ]
        self._ensure_file()

    def _ensure_file(self):
        directory = os.path.dirname(self.filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        if not os.path.exists(self.filepath):
            with open(self.filepath, mode='w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(self.headers)
            logger.info(f"Created new dataset file at {self.filepath}")

    def log_features(self, token_address: str, pair_address: str, features: list, is_safe: bool):
        """
        Appends a new feature vector to the CSV dataset.
        label_2x is left empty initially (can be updated by a separate labeler script later).
        """
        try:
            timestamp = datetime.utcnow().isoformat()
            # None or empty string for label_2x initially
            label_2x = "" 
            
            # features list shouldn't be empty, but standardizes it just in case
            safe_val = 1 if is_safe else 0
            row = [timestamp, token_address, pair_address] + features + [safe_val, label_2x]
            
            with open(self.filepath, mode='a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
            logger.info(f"Logged features for {token_address} safely.")
        except Exception as e:
            logger.error(f"Failed to log data for {token_address}: {e}")
