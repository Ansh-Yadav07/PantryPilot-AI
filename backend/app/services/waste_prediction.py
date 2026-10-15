from datetime import datetime
from typing import Optional


class WastePredictionService:
    """Rule-based waste risk from days until expiry.

    This is a deterministic heuristic, not a trained model; the probabilities
    are fixed bands, and the API labels results as rule-based.
    """

    @staticmethod
    def predict_waste_risk(item_name: str, expiry_date: datetime, quantity: float,
                           now: Optional[datetime] = None) -> dict:
        today = (now or datetime.utcnow()).date()
        days_to_expiry = (expiry_date.date() - today).days

        if days_to_expiry < 0:
            return {"wasteProbability": 1.0, "riskLevel": "CRITICAL", "reason": f"{item_name} has expired."}
        if days_to_expiry <= 3:
            return {"wasteProbability": 0.85, "riskLevel": "HIGH",
                    "reason": f"{item_name} expires within {days_to_expiry} day(s)."}
        if days_to_expiry <= 7:
            return {"wasteProbability": 0.5, "riskLevel": "MEDIUM", "reason": f"{item_name} expires within a week."}
        return {"wasteProbability": 0.1, "riskLevel": "LOW", "reason": f"{item_name} has plenty of shelf life left."}
