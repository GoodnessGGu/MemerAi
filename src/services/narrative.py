import re
import math
import logging
import sys
import os
from datetime import datetime, timedelta
import feedparser

# Ensure local Agent-Reach module can be imported
agent_reach_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Agent-Reach"))
if os.path.exists(agent_reach_dir) and agent_reach_dir not in sys.path:
    sys.path.insert(0, agent_reach_dir)

try:
    from agent_reach.channels.v2ex import V2EXChannel
    from agent_reach.channels.web import WebChannel
except Exception:
    V2EXChannel = None
    WebChannel = None

from src.services.db import KnowledgeDatabase

logger = logging.getLogger(__name__)

# Default stop words for simple tokenization/clustering
STOP_WORDS = {
    "the", "and", "a", "of", "to", "in", "is", "that", "it", "on", "for", "as", "with",
    "was", "for", "on", "are", "as", "with", "his", "they", "i", "at", "be", "this",
    "have", "from", "or", "one", "had", "by", "word", "but", "not", "what", "all",
    "were", "we", "when", "your", "can", "said", "there", "use", "an", "each", "which",
    "she", "do", "how", "their", "if", "will", "up", "other", "about", "out", "many",
    "then", "them", "these", "so", "some", "her", "would", "make", "like", "him", "into",
    "has", "look", "more", "write", "go", "see", "number", "no", "way", "could", "people",
    "my", "than", "first", "water", "been", "call", "who", "oil", "its", "now", "find",
    "crypto", "bitcoin", "ethereum", "btc", "eth", "solana", "sol", "token", "coin",
    "news", "market", "price", "trading", "network"
}

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]

class NarrativeEngine:
    def __init__(self, db: KnowledgeDatabase = None):
        self.db = db or KnowledgeDatabase()
        self.v2ex = V2EXChannel() if V2EXChannel else None
        self.web = WebChannel() if WebChannel else None

    async def discover_narratives(self):
        """Scrape RSS and V2EX to extract emerging keywords and update narratives database."""
        logger.info("Starting dynamic narrative discovery...")
        word_counts = {}
        
        # 1. Fetch RSS feeds
        for feed_url in RSS_FEEDS:
            try:
                # running in executor or directly (asyncio friendly via wrapper is better, but this is simple block)
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:15]:
                    text = f"{entry.title} {getattr(entry, 'description', '')}"
                    self._extract_words(text, word_counts)
            except Exception as e:
                logger.warning(f"Failed to fetch RSS feed {feed_url}: {e}")

        # 2. Fetch V2EX hot topics
        if self.v2ex:
            try:
                hot_topics = self.v2ex.get_hot_topics(limit=20)
                for topic in hot_topics:
                    text = f"{topic['title']} {topic.get('content', '')}"
                    self._extract_words(text, word_counts)
            except Exception as e:
                logger.warning(f"Failed to fetch V2EX hot topics: {e}")

        # Normalize and filter words by frequency
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        discovered_meta = []
        
        for word, count in sorted_words:
            if count >= 3: # Must appear at least 3 times
                category = word.upper()
                
                # Check current database status
                existing = self.db.get_narrative(category)
                if existing:
                    # Update popularity and calculate growth
                    old_popularity = existing["popularity"]
                    growth = (count - old_popularity) / old_popularity if old_popularity > 0 else 1.0
                    status = "growth" if growth > 0.05 else "peak"
                    
                    # Store updated narrative
                    self.db.save_narrative(
                        category=category,
                        description=f"Trending keyword discovered from web: {category}",
                        status=status,
                        popularity=float(count),
                        growth_rate=float(growth),
                        decay_factor=0.01
                    )
                else:
                    # New narrative
                    self.db.save_narrative(
                        category=category,
                        description=f"New trending keyword: {category}",
                        status="birth",
                        popularity=float(count),
                        growth_rate=1.0,
                        decay_factor=0.01
                    )
                discovered_meta.append(category)

        logger.info(f"Narrative discovery complete. Top keywords: {discovered_meta[:10]}")

    def _extract_words(self, text: str, word_counts: dict):
        # Clean text, find English words and Chinese terms (simple regex)
        words = re.findall(r'[a-zA-Z]{3,}', text.lower())
        for w in words:
            if w not in STOP_WORDS:
                word_counts[w] = word_counts.get(w, 0) + 1

    def decay_narratives(self):
        """Simulate natural popularity decay over time."""
        narratives = self.db.get_all_narratives()
        for n in narratives:
            # Popularity decays by 5% per cycle unless updated
            decayed_pop = n["popularity"] * (1 - n["decay_factor"])
            status = n["status"]
            if decayed_pop < 1.0:
                status = "dead"
            elif decayed_pop < n["popularity"] * 0.7:
                status = "decline"
                
            self.db.save_narrative(
                category=n["category"],
                description=n["description"],
                status=status,
                popularity=decayed_pop,
                growth_rate=-0.05,
                decay_factor=n["decay_factor"]
            )

    def evaluate_token_narrative(self, name: str, symbol: str) -> dict:
        """
        Match a token's name and symbol to dynamic database narratives and calculate a Narrative Score.
        Returns a dict: {category, score, status, growth_rate, expected_lifespan_hours}
        """
        name_upper = name.upper()
        symbol_upper = symbol.upper()
        
        # 1. High-priority Seasonal & Signature metas first
        halloween_kw = ["HALLOWEEN", "PUMPKIN", "SPOOKY", "GHOST", "WEEN", "HAUNT", "WITCH", "SKELETON", "VAMPIRE", "ZOMBIE"]
        if any(x in name_upper or x in symbol_upper for x in halloween_kw):
            return {
                "category": "Halloween Meta 🎃",
                "score": 85.0,
                "status": "growth",
                "growth_rate": 0.25,
                "expected_lifespan_hours": 48.0
            }

        all_narratives = self.db.get_all_narratives()
        matched = None
        highest_pop = 0.0
        
        # Check database match with word boundary safety for short words
        combined_text = f"{name_upper} {symbol_upper}"
        for n in all_narratives:
            cat = n["category"].upper()
            is_match = False
            if len(cat) <= 4:
                is_match = bool(re.search(rf"\b{re.escape(cat)}\b", combined_text))
            else:
                is_match = cat in name_upper or cat in symbol_upper
                
            if is_match and n["popularity"] > highest_pop:
                highest_pop = n["popularity"]
                matched = n

        # Fallback default hardcoded rules if database is empty or not matched
        if not matched:
            fallback_category = "Generic"
            score = 10.0
            status = "birth"
            growth = 0.0
            lifespan = 24.0
            
            # Map fallback rules
            if any(x in name_upper or x in symbol_upper for x in ["ELON", "MUSK", "MARS", "XAI"]):
                fallback_category = "Elon Meta 🚀"
                score = 65.0
                status = "growth"
                lifespan = 48.0
            elif any(x in name_upper or x in symbol_upper for x in ["GPT", "AI", "BOT", "NEURAL"]):
                fallback_category = "AI Meta 🧠"
                score = 55.0
                status = "growth"
                lifespan = 72.0
            elif any(x in name_upper or x in symbol_upper for x in ["DOGE", "SHIB", "PEPE", "FLOKI", "MOODENG", "PNUT", "CHILLGUY", "NEIRO"]):
                fallback_category = "Meme Meta 🐸"
                score = 75.0
                status = "peak"
                lifespan = 96.0
            elif any(x in name_upper or x in symbol_upper for x in ["CZ", "BINANCE", "BNB"]):
                fallback_category = "Binance/CZ Meta 💛"
                score = 50.0
                status = "growth"
                lifespan = 36.0
            elif any(x in name_upper or x in symbol_upper for x in ["HALLOWEEN", "PUMPKIN", "SPOOKY", "GHOST", "WEEN", "HAUNT", "WITCH", "SKELETON", "VAMPIRE", "ZOMBIE"]):
                fallback_category = "Halloween Meta 🎃"
                score = 85.0
                status = "growth"
                lifespan = 48.0
            elif any(x in name_upper or x in symbol_upper for x in ["TRUMP", "HARRIS", "BIDEN", "VOTE", "USA", "ELECTION"]):
                fallback_category = "PolitiFi Meta 🇺🇸"
                score = 80.0
                status = "peak"
                lifespan = 120.0
            elif any(x in name_upper or x in symbol_upper for x in ["HAALAND", "CR7", "MESSI", "FOOTBALL", "SOCCER"]):
                fallback_category = "Sports Meta ⚽"
                score = 45.0
                status = "growth"
                lifespan = 48.0
            elif any(x in name_upper or x in symbol_upper for x in ["SEC", "SP500", "FED", "WALLSTREET", "STONK", "BANK"]):
                fallback_category = "Financial Satire 🏛️"
                score = 70.0
                status = "growth"
                lifespan = 48.0
            elif any(x in name_upper or x in symbol_upper for x in ["2.0", "3.0", "V2", "INU", "BABY"]):
                fallback_category = "Derivative 2.0 🔄"
                score = 60.0
                status = "growth"
                lifespan = 24.0
                
            return {
                "category": fallback_category,
                "score": score,
                "status": status,
                "growth_rate": growth,
                "expected_lifespan_hours": lifespan
            }

        # Calculate a Narrative Score (0-100) based on popularity and growth
        base_score = min(30.0 + (matched["popularity"] * 10.0), 90.0)
        if matched["growth_rate"] > 0:
            base_score = min(100.0, base_score + (matched["growth_rate"] * 10.0))
            
        # Expected Lifespan estimation based on status
        lifespan_map = {
            "birth": 24.0,
            "growth": 72.0,
            "peak": 48.0,
            "decline": 12.0,
            "dead": 2.0
        }
        
        return {
            "category": matched["category"],
            "score": base_score,
            "status": matched["status"],
            "growth_rate": matched["growth_rate"],
            "expected_lifespan_hours": lifespan_map.get(matched["status"], 24.0)
        }
