import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from fastapi import APIRouter

logger = logging.getLogger("alertmanager_webhook")
logger.setLevel(logging.INFO)

router = APIRouter(tags=["alertmanager"])

# --- Models ---
class Alert(BaseModel):
    """
    Represents an individual alert triggered in Prometheus/Alertmanager.
    """
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str] = Field(default_factory=dict)
    startsAt: str
    endsAt: str
    generatorURL: str
    fingerprint: str

class AlertPayload(BaseModel):
    """
    Matches the standard webhook JSON payload structure sent by Prometheus Alertmanager.
    """
    version: str
    groupKey: str
    status: str
    receiver: str
    groupLabels: Dict[str, str] = Field(default_factory=dict)
    commonLabels: Dict[str, str] = Field(default_factory=dict)
    commonAnnotations: Dict[str, str] = Field(default_factory=dict)
    externalURL: str
    alerts: List[Alert]

# --- Storage & Deduplication ---
class AlertStore:
    """
    In-memory storage for deduplication and alert history tracking.
    """
    def __init__(self):
        # Maps fingerprint -> the latest Alert state received
        self.active_alerts: Dict[str, Alert] = {}
        # Stores a history of processed alert events
        self.alert_history: List[Dict[str, Any]] = []

    def is_duplicate(self, alert: Alert) -> bool:
        """
        Checks if the alert is a duplicate by comparing its fingerprint and status
        against the active active_alerts map.
        """
        if alert.fingerprint in self.active_alerts:
            existing = self.active_alerts[alert.fingerprint]
            # If we already have the alert in the exact same state, consider it a duplicate
            if existing.status == alert.status:
                return True
        return False

    def store_alert(self, alert: Alert):
        """
        Saves the alert to the active state and appends to history.
        """
        self.active_alerts[alert.fingerprint] = alert
        
        self.alert_history.append({
            "fingerprint": alert.fingerprint,
            "status": alert.status,
            "labels": alert.labels,
            "recorded_at": datetime.utcnow().isoformat()
        })
        
        # Keep history bounded in-memory
        if len(self.alert_history) > 1000:
            self.alert_history.pop(0)

# Global in-memory store
alert_store = AlertStore()

# --- Mock Integrations & Routing ---
async def mock_pagerduty_notify(alert: Alert):
    logger.info(f"[PAGERDUTY MOCK] Triggering high-priority incident for fingerprint {alert.fingerprint} | Labels: {alert.labels}")

async def mock_slack_notify(alert: Alert):
    logger.info(f"[SLACK MOCK] Sending warning notification to #alerts channel for fingerprint {alert.fingerprint} | Labels: {alert.labels}")

async def route_alert(alert: Alert):
    """
    Routes the alert to the appropriate channel based on its severity label.
    """
    severity = alert.labels.get("severity", "info").lower()
    
    if severity == "critical":
        await mock_pagerduty_notify(alert)
    elif severity == "warning":
        await mock_slack_notify(alert)
    else:
        # Defaults to info/log for anything else
        logger.info(f"[LOG ONLY] Received info-level alert {alert.fingerprint} | Labels: {alert.labels}")

# --- Endpoints ---
@router.post("/webhooks/alertmanager")
async def receive_alertmanager_webhook(payload: AlertPayload):
    """
    Receives alerts from Prometheus Alertmanager, deduplicates by fingerprint, 
    stores them in history, and routes them to destinations (PagerDuty/Slack/Log).
    """
    processed_count = 0
    duplicates_count = 0
    
    for alert in payload.alerts:
        if alert_store.is_duplicate(alert):
            duplicates_count += 1
            continue
            
        alert_store.store_alert(alert)
        await route_alert(alert)
        processed_count += 1
        
    return {
        "status": "success",
        "processed": processed_count,
        "duplicates_skipped": duplicates_count
    }

@router.get("/webhooks/alertmanager/history")
async def get_alert_history():
    """
    Retrieve the bounded recent history of processed alerts.
    """
    return {"history": alert_store.alert_history}
