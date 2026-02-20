from datetime import datetime, date, time, timedelta
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import DispatchLog, Item, PackagingOrder, WorkOrder
from app.routers.auth import require_permission
from app.schemas import ProductionReportResponse, ProductionReportRow

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _period_from_range(range_key: str) -> tuple[datetime, datetime]:
    today = date.today()
    if range_key == "daily":
        start = datetime.combine(today, time.min)
    elif range_key == "weekly":
        start = datetime.combine(today - timedelta(days=6), time.min)
    elif range_key == "monthly":
        start = datetime.combine(today - timedelta(days=29), time.min)
    else:
        raise HTTPException(status_code=400, detail="Invalid range")
    end = datetime.now()
    return start, end


@router.get("/production", response_model=ProductionReportResponse)
def production_report(
    request: Request,
    range: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    session: Session = Depends(get_session),
):
    require_permission(request, session, "production_reports", "read")
    start, end = _period_from_range(range)

    items = session.exec(select(Item)).all()
    item_by_id = {item.id: item for item in items}
    item_by_sku = {item.sku: item for item in items}

    planned_map: Dict[str, int] = {}
    planned_rows = session.exec(
        select(WorkOrder).where(
            WorkOrder.created_at >= start,
            WorkOrder.created_at <= end,
        )
    ).all()
    for order in planned_rows:
        item = item_by_id.get(order.item_id)
        if not item:
            continue
        planned_qty = int(order.planned_qty or order.qty or 0)
        if planned_qty <= 0:
            continue
        planned_map[item.sku] = planned_map.get(item.sku, 0) + planned_qty

    produced_map: Dict[str, int] = {}
    produced_rows = session.exec(
        select(PackagingOrder).where(
            PackagingOrder.status == "DONE",
            PackagingOrder.completed_at.is_not(None),
            PackagingOrder.completed_at >= start,
            PackagingOrder.completed_at <= end,
        )
    ).all()
    for pack in produced_rows:
        item = item_by_id.get(pack.item_id)
        if not item:
            continue
        produced_map[item.sku] = produced_map.get(item.sku, 0) + int(pack.qty_packed)

    rejected_map: Dict[str, int] = {}
    rejected_rows = session.exec(
        select(DispatchLog).where(
            DispatchLog.created_at >= start,
            DispatchLog.created_at <= end,
        )
    ).all()
    for log in rejected_rows:
        if not log.sku:
            continue
        rejected_map[log.sku] = rejected_map.get(log.sku, 0) + int(log.rejected_qty)

    sku_set = set(planned_map) | set(produced_map) | set(rejected_map)
    rows: List[ProductionReportRow] = []
    totals = {"planned": 0, "produced": 0, "rejected": 0}

    for sku in sorted(sku_set):
        item = item_by_sku.get(sku)
        row = ProductionReportRow(
            sku=sku,
            item_name=item.name if item else "",
            planned=planned_map.get(sku, 0),
            produced=produced_map.get(sku, 0),
            rejected=rejected_map.get(sku, 0),
        )
        totals["planned"] += row.planned
        totals["produced"] += row.produced
        totals["rejected"] += row.rejected
        rows.append(row)

    return ProductionReportResponse(
        start=start,
        end=end,
        rows=rows,
        totals=ProductionReportRow(
            sku="TOTAL",
            item_name="",
            planned=totals["planned"],
            produced=totals["produced"],
            rejected=totals["rejected"],
        ),
    )


@router.get("/summary")
def production_summary(
    request: Request,
    range: str = Query("weekly", regex="^(weekly|monthly)$"),
    session: Session = Depends(get_session),
):
    require_permission(request, session, "production_reports", "read")
    start, end = _period_from_range(range)

    produced_rows = session.exec(
        select(PackagingOrder).where(
            PackagingOrder.status == "DONE",
            PackagingOrder.completed_at.is_not(None),
            PackagingOrder.completed_at >= start,
            PackagingOrder.completed_at <= end,
        )
    ).all()
    produced = sum(int(pack.qty_packed) for pack in produced_rows)

    dispatch_rows = session.exec(
        select(DispatchLog).where(DispatchLog.created_at >= start, DispatchLog.created_at <= end)
    ).all()
    dispatched = sum(int(log.dispatch_qty) for log in dispatch_rows)
    rejected = sum(int(log.rejected_qty) for log in dispatch_rows)
    rejection_rate = (rejected / dispatched * 100) if dispatched > 0 else 0.0

    return {
        "start": start,
        "end": end,
        "produced": produced,
        "dispatched": dispatched,
        "rejected": rejected,
        "rejection_rate": round(rejection_rate, 2),
    }
