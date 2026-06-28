import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("monitoring.alertmanager")

# --- Pydantic Models for Alertmanager Webhook Payload ---
# Structuring the rigorous exact schema exported by Prometheus Alertmanager

class AlertLabels(BaseModel):
    severity: str = "unknown"
    service: Optional[str] = "unknown-service"
    instance: Optional[str] = "unknown-instance"
    alertname: str = "UnknownAlert"

class AlertAnnotations(BaseModel):
    summary: Optional[str] = "No summary provided."
    description: Optional[str] = "No description provided."

class AlertItem(BaseModel):
    status: str
    labels: AlertLabels
    annotations: AlertAnnotations
    startsAt: str
    endsAt: str
    generatorURL: Optional[str] = None
    fingerprint: str

class AlertmanagerPayload(BaseModel):
    version: str
    groupKey: str
    truncatedAlerts: int = 0
    status: str
    receiver: str
    groupLabels: Dict[str, str]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]
    externalURL: str
    alerts: List[AlertItem]


# --- In-Memory State & Notification Mock Engine ---

class NotificationRouter:
    """
    Handles logical extraction of Alertmanager events and coordinates 
    dynamic dispatch mechanisms to external sinks based on priority boundaries.
    """
    
    def __init__(self):
        # Logical state map storing deduplicated histories via prometheus fingerprint IDs
        self.alert_history: Dict[str, Dict[str, Any]] = {}

    async def _send_pagerduty(self, alert: AlertItem):
        """
        Mocks invoking the PagerDuty Events API v2.
        Required exclusively for CRITICAL severity events mapping to physical paging logic.
        """
        logger.error(f"[PagerDuty Triggered] 🔥 INCIDENT: {alert.labels.alertname} - {alert.annotations.summary}")
        logger.error(f"Event dispatched to PagerDuty sink for physical service mapping: {alert.labels.service}")

    async def _send_slack(self, alert: AlertItem):
        """
        Mocks invoking a standard Slack Incoming Webhook pipeline.
        Utilized primarily for WARNING severity constraints without waking engineers.
        """
        logger.warning(f"[Slack Notification] ⚠️ {alert.labels.alertname}: {alert.annotations.summary}")
        logger.warning(f"Message payload broadcasted to Slack channel #monitoring (Instance: {alert.labels.instance})")

    async def route_alert(self, alert: AlertItem):
        """
        Core boundary router. Evaluates strict severity labels and determines 
        notification propagation logic while safely tracking lifecycle states.
        """
        # 1. Update the local deduplicated historical tracking map using the unique hash fingerprint
        self.alert_history[alert.fingerprint] = {
            "status": alert.status,
            "severity": alert.labels.severity,
            "alertname": alert.labels.alertname,
            "service": alert.labels.service,
            "received_at": datetime.utcnow().isoformat(),
            "raw": alert.model_dump()
        }
        
        # 2. Escalate cleanly on resolutions (Don't trigger PagerDuty for a resolved alert)
        if alert.status.lower() == "resolved":
            logger.info(f"Alert {alert.fingerprint} natively resolved by system constraints. Clearing active escalations.")
            return

        # 3. Handle severity escalations explicitly
        severity = alert.labels.severity.lower()
        
        if severity == "critical":
            await self._send_pagerduty(alert)
        elif severity == "warning":
            await self._send_slack(alert)
        else:
            # Safely capture Info/Unknown/Debug traces internally without API noise
            logger.info(f"[Platform Event] {alert.labels.alertname} mapped and logged securely.")

    def get_history(self) -> List[Dict[str, Any]]:
        """Returns chronological snapshots of system anomaly states."""
        events = list(self.alert_history.values())
        return sorted(events, key=lambda x: x["received_at"], reverse=True)


# --- REST Controllers Integration ---

router = APIRouter(prefix="/webhooks/alertmanager", tags=["monitoring", "webhooks"])
notification_router = NotificationRouter()

@router.post("")
async def receive_prometheus_alerts(payload: AlertmanagerPayload):
    """
    POST /webhooks/alertmanager
    Ingestion endpoint natively consuming standard Prometheus Webhook structural formatting.
    Unpacks nested payloads scaling dynamically across massive logical lists.
    """
    logger.info(f"Alertmanager push received. Processing group key [{payload.groupKey}] carrying {len(payload.alerts)} alarms.")
    
    # Process dynamically routed chunks
    for alert in payload.alerts:
        try:
            await notification_router.route_alert(alert)
        except Exception as e:
            logger.error(f"Routing logic execution failure for alert fingerprint {alert.fingerprint}: {e}")
            
    return {"status": "accepted", "processed_alarms": len(payload.alerts)}


@router.get("/history")
async def fetch_alert_history():
    """
    GET /webhooks/alertmanager/history
    Diagnostic retrieval endpoint fetching active historical states tracked by fingerprints.
    """
    return {
        "total_events_tracked": len(notification_router.alert_history), 
        "events": notification_router.get_history()
    }
