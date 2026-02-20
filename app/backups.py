import json
import os
from datetime import datetime

from sqlmodel import Session, select

from app.s3_client import upload_raw
from app.models import (
    AssemblyOrder,
    DispatchLog,
    Item,
    PackagingOrder,
    PurchaseOrder,
    PurchaseOrderLine,
    WorkOrder,
)


def build_backup_payload(session: Session) -> dict:
    return {
        "generated_at": datetime.utcnow().isoformat(),
        "items": [item.model_dump() for item in session.exec(select(Item)).all()],
        "purchase_orders": [
            order.model_dump() for order in session.exec(select(PurchaseOrder)).all()
        ],
        "purchase_order_lines": [
            line.model_dump() for line in session.exec(select(PurchaseOrderLine)).all()
        ],
        "dispatch_logs": [
            log.model_dump() for log in session.exec(select(DispatchLog)).all()
        ],
        "work_orders": [order.model_dump() for order in session.exec(select(WorkOrder)).all()],
        "assembly_orders": [
            order.model_dump() for order in session.exec(select(AssemblyOrder)).all()
        ],
        "packaging_orders": [
            order.model_dump() for order in session.exec(select(PackagingOrder)).all()
        ],
    }


def run_backup(session: Session) -> dict:
    payload = build_backup_payload(session)
    folder = os.getenv("S3_BACKUP_FOLDER", "backups/db")
    filename = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    content = json.dumps(payload)
    key = upload_raw(content, folder=folder, filename=filename)
    return {
        "key": key,
        "created_at": datetime.utcnow().isoformat(),
    }
