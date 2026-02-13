from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    AssemblyOrder,
    Item,
    PackagingOrder,
    PurchaseOrder,
    PurchaseOrderLine,
    StockLedger,
    WorkOrder,
)
from app.schemas import PackagingOrderRead, PackagingOrderUpdate
from app.routers.auth import require_permission

router = APIRouter(prefix="/api/packaging", tags=["packaging"])


@router.get("", response_model=List[PackagingOrderRead])
def list_packaging(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "packaging", "read")
    rows = session.exec(
        select(PackagingOrder, Item)
        .where(PackagingOrder.item_id == Item.id)
        .order_by(PackagingOrder.id.desc())
    ).all()
    return [
        PackagingOrderRead(
            id=packaging.id,
            sku=item.sku,
            item_name=item.name,
            qty_total=packaging.qty_total,
            qty_packed=packaging.qty_packed,
            status=packaging.status,
        )
        for packaging, item in rows
    ]


@router.put("/{packaging_id}", response_model=PackagingOrderRead)
def update_packaging(
    packaging_id: int, payload: PackagingOrderUpdate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "packaging", "write")
    packaging = session.get(PackagingOrder, packaging_id)
    if not packaging:
        raise HTTPException(status_code=404, detail="Packaging order not found")

    if payload.status not in ["PLANNED", "IN_PROGRESS", "DONE"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    if payload.qty_packed < 0 or payload.qty_packed > packaging.qty_total:
        raise HTTPException(status_code=400, detail="Invalid packed quantity")

    if payload.qty_packed <= 0:
        raise HTTPException(status_code=400, detail="Packed quantity must be greater than 0")

    # Update inventory by delta packed
    delta = payload.qty_packed - packaging.qty_packed
    if delta:
        item = session.get(Item, packaging.item_id)
        if item:
            item.quantity += delta
            session.add(item)

    if payload.status == "DONE" and payload.qty_packed < packaging.qty_total:
        # Split into completed record and remaining record
        completed = PackagingOrder(
            work_order_id=packaging.work_order_id,
            item_id=packaging.item_id,
            qty_total=payload.qty_packed,
            qty_packed=payload.qty_packed,
            status="DONE",
            completed_at=datetime.utcnow(),
        )
        remaining_qty = packaging.qty_total - payload.qty_packed
        packaging.qty_total = remaining_qty
        packaging.qty_packed = 0
        packaging.status = "PLANNED"
        session.add(completed)
        session.add(packaging)
        session.commit()
        session.refresh(completed)

        item = session.get(Item, packaging.item_id)
        _fulfill_pending_orders(session)
        return PackagingOrderRead(
            id=completed.id,
            sku=item.sku if item else "",
            item_name=item.name if item else "",
            qty_total=completed.qty_total,
            qty_packed=completed.qty_packed,
            status=completed.status,
        )

    packaging.qty_packed = payload.qty_packed
    packaging.status = payload.status
    if payload.status == "DONE":
        packaging.completed_at = datetime.utcnow()
    session.add(packaging)
    session.commit()
    session.refresh(packaging)

    item = session.get(Item, packaging.item_id)
    _fulfill_pending_orders(session)
    return PackagingOrderRead(
        id=packaging.id,
        sku=item.sku if item else "",
        item_name=item.name if item else "",
        qty_total=packaging.qty_total,
        qty_packed=packaging.qty_packed,
        status=packaging.status,
    )


def _fulfill_pending_orders(session: Session) -> None:
    pending_orders = session.exec(
        select(PurchaseOrder)
        .where(PurchaseOrder.status == "PENDING_DISPATCH")
        .order_by(PurchaseOrder.order_timestamp.asc(), PurchaseOrder.id.asc())
    ).all()
    if not pending_orders:
        return
    # Do not auto-approve pending orders. Approval is manual in Orders page.
    _recalc_production_requirements(session)


def _recalc_production_requirements(session: Session) -> None:
    pending_orders = session.exec(
        select(PurchaseOrder).where(PurchaseOrder.status == "PENDING_DISPATCH")
    ).all()
    order_ids = [order.id for order in pending_orders]

    pending_lines = []
    if order_ids:
        pending_lines = session.exec(
            select(PurchaseOrderLine, Item)
            .where(PurchaseOrderLine.purchase_order_id.in_(order_ids))
            .where(PurchaseOrderLine.item_id == Item.id)
        ).all()

    pending_demand: dict[int, int] = {}
    for line, item in pending_lines:
        pending_demand[item.id] = pending_demand.get(item.id, 0) + int(line.qty)

    items = session.exec(select(Item)).all()
    for item in items:
        open_work_orders = session.exec(
            select(WorkOrder).where(
                WorkOrder.item_id == item.id,
                WorkOrder.status.in_(["PLANNED", "IN_PROGRESS"]),
            )
        ).all()
        in_production = sum(int(order.qty) for order in open_work_orders)

        open_assembly = session.exec(
            select(AssemblyOrder).where(
                AssemblyOrder.item_id == item.id,
                AssemblyOrder.status != "DONE",
            )
        ).all()
        in_assembly = sum(
            max(0, int(order.qty_total) - int(order.qty_assembled)) for order in open_assembly
        )

        open_packaging = session.exec(
            select(PackagingOrder).where(
                PackagingOrder.item_id == item.id,
                PackagingOrder.status != "DONE",
            )
        ).all()
        in_packaging = sum(
            max(0, int(pack.qty_total) - int(pack.qty_packed)) for pack in open_packaging
        )

        target = item.reorder_level + pending_demand.get(item.id, 0)
        effective_available = item.quantity + in_production + in_assembly + in_packaging
        needed = max(0, target - effective_available)

        planned = next(
            (order for order in open_work_orders if order.status == "PLANNED"), None
        )
        in_progress = any(order.status == "IN_PROGRESS" for order in open_work_orders)

        if needed <= 0:
            if planned:
                session.delete(planned)
            continue

        if planned:
            planned.qty = needed
            planned.planned_qty = needed
            session.add(planned)
        elif not in_progress:
            session.add(
                WorkOrder(item_id=item.id, qty=needed, planned_qty=needed, status="PLANNED")
            )

    session.commit()
