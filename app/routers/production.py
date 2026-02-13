from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import AssemblyOrder, Item, PackagingOrder, PurchaseOrder, PurchaseOrderLine, WorkOrder
from app.schemas import WorkOrderCreate, WorkOrderProduce, WorkOrderRead, WorkOrderUpdate
from app.routers.auth import require_permission

router = APIRouter(prefix="/api/work-orders", tags=["production"])


@router.get("", response_model=List[WorkOrderRead])
def list_work_orders(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "production_manager", "read")
    _recalc_production_requirements(session)

    rows = session.exec(
        select(WorkOrder, Item).where(WorkOrder.item_id == Item.id).order_by(WorkOrder.id.desc())
    ).all()
    return [
        WorkOrderRead(
            id=work_order.id,
            sku=item.sku,
            item_name=item.name,
            quantity=work_order.qty,
            status=work_order.status,
        )
        for work_order, item in rows
    ]


@router.post("", response_model=WorkOrderRead)
def create_work_order(payload: WorkOrderCreate, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "production_manager", "write")
    item = session.exec(select(Item).where(Item.sku == payload.sku)).first()
    if not item:
        raise HTTPException(status_code=404, detail="SKU not found")

    work_order = WorkOrder(item_id=item.id, qty=payload.quantity, status=payload.status)
    work_order.planned_qty = payload.quantity
    session.add(work_order)
    session.commit()
    session.refresh(work_order)
    return WorkOrderRead(
        id=work_order.id,
        sku=item.sku,
        item_name=item.name,
        quantity=work_order.qty,
        status=work_order.status,
    )


@router.put("/{work_order_id}", response_model=WorkOrderRead)
def update_work_order(
    work_order_id: int, payload: WorkOrderUpdate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "production_manager", "write")
    work_order = session.get(WorkOrder, work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    if payload.status not in ["PLANNED", "IN_PROGRESS", "DONE"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    if work_order.status != "DONE" and payload.status == "DONE":
        if work_order.qty > 0:
            session.add(
                AssemblyOrder(
                    work_order_id=work_order.id,
                    item_id=work_order.item_id,
                    qty_total=int(work_order.qty),
                    qty_assembled=0,
                    status="PLANNED",
                )
            )
            work_order.qty = 0
        work_order.completed_at = datetime.utcnow()
        session.add(
            PackagingOrder(
                work_order_id=work_order.id,
                item_id=work_order.item_id,
                qty_total=int(work_order.qty),
                qty_packed=0,
                status="PLANNED",
            )
        )

    work_order.status = payload.status
    session.add(work_order)
    session.commit()
    session.refresh(work_order)

    item = session.get(Item, work_order.item_id)
    return WorkOrderRead(
        id=work_order.id,
        sku=item.sku if item else "",
        item_name=item.name if item else "",
        quantity=work_order.qty,
        status=work_order.status,
    )


@router.post("/{work_order_id}/produce", response_model=WorkOrderRead)
def produce_work_order(
    work_order_id: int, payload: WorkOrderProduce, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "production_manager", "write")
    work_order = session.get(WorkOrder, work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")

    if payload.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be > 0")

    if payload.quantity > work_order.qty:
        raise HTTPException(status_code=400, detail="Quantity exceeds remaining plan")

    # Create assembly batch for produced quantity
    session.add(
        AssemblyOrder(
            work_order_id=work_order.id,
            item_id=work_order.item_id,
            qty_total=payload.quantity,
            qty_assembled=0,
            status="PLANNED",
        )
    )

    work_order.qty -= payload.quantity
    if work_order.qty == 0:
        work_order.status = "DONE"
        work_order.completed_at = datetime.utcnow()
    else:
        work_order.status = "IN_PROGRESS"

    session.add(work_order)
    session.commit()
    session.refresh(work_order)

    item = session.get(Item, work_order.item_id)
    return WorkOrderRead(
        id=work_order.id,
        sku=item.sku if item else "",
        item_name=item.name if item else "",
        quantity=work_order.qty,
        status=work_order.status,
    )


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


@router.delete("/{work_order_id}")
def delete_work_order(work_order_id: int, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "production_manager", "write")
    work_order = session.get(WorkOrder, work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    session.delete(work_order)
    session.commit()
    return {"ok": True}
