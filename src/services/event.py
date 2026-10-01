import logging
from datetime import datetime, timedelta
from src.services.db import KnowledgeDatabase

logger = logging.getLogger(__name__)

# Predefined event patterns mapping to categories and estimated durations
EVENT_METAS = {
    "BINANCE LISTING": {"category": "Binance/CZ Meta 💛", "impact": 9.5, "duration": 48},
    "COINBASE LISTING": {"category": "Binance/CZ Meta 💛", "impact": 9.0, "duration": 48},
    "ELON TWEET": {"category": "Elon Meta 🚀", "impact": 8.0, "duration": 24},
    "FED MEETING": {"category": "Generic", "impact": 7.0, "duration": 12},
    "ELECTION POLL": {"category": "PolitiFi Meta 🇺🇸", "impact": 8.5, "duration": 72},
    "WORLD CUP GOAL": {"category": "Sports Meta ⚽", "impact": 6.5, "duration": 24},
    "AI BREAKTHROUGH": {"category": "AI Meta 🧠", "impact": 7.5, "duration": 96}
}

class EventEngine:
    def __init__(self, db: KnowledgeDatabase = None):
        self.db = db or KnowledgeDatabase()

    def process_new_event(self, title: str, description: str) -> dict:
        """
        Detects, scores, and stores a new event.
        Matches event title against patterns to find the category and impact score.
        """
        title_upper = title.upper()
        category = "Generic"
        impact_score = 5.0
        duration = 24.0 # default 24 hours
        
        # Match event patterns
        for pattern, meta in EVENT_METAS.items():
            if pattern in title_upper:
                category = meta["category"]
                impact_score = meta["impact"]
                duration = meta["duration"]
                break
                
        # Save to database
        self.db.save_event(
            category=category,
            impact_score=impact_score,
            description=f"{title}: {description}",
            expected_duration=duration,
            affected_narratives=category
        )
        
        logger.info(f"Processed Event: '{title}' | Category: {category} | Impact: {impact_score}/10")
        
        return {
            "category": category,
            "impact_score": impact_score,
            "expected_duration_hours": duration
        }

    def get_active_event_impact(self, narrative_category: str) -> dict:
        """
        Checks database for any recent, unexpired events affecting the given narrative.
        Returns a dict: {has_active_event, max_impact_score, event_description}
        """
        recent_events = self.db.get_recent_events(limit=5)
        now = datetime.utcnow()
        
        max_impact = 0.0
        active_event = None
        
        for event in recent_events:
            event_time = datetime.fromisoformat(event["timestamp"])
            duration_delta = timedelta(hours=event["expected_duration"])
            
            # Check if event has not expired yet
            if now <= (event_time + duration_delta):
                affected = [x.strip() for x in event["affected_narratives"].split(",")]
                if narrative_category in affected or event["category"] == "Generic":
                    if event["impact_score"] > max_impact:
                        max_impact = event["impact_score"]
                        active_event = event
                        
        if active_event:
            return {
                "has_active_event": True,
                "impact_score": max_impact,
                "description": active_event["description"]
            }
            
        return {
            "has_active_event": False,
            "impact_score": 0.0,
            "description": ""
        }
