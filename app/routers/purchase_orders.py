from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import (
    AssemblyOrder,
    DispatchLog,
    Item,
    PackagingOrder,
    PurchaseOrder,
    PurchaseOrderLine,
    StockLedger,
    WorkOrder,
)
from app.schemas import (
    DispatchLogRead,
    DispatchQcPayload,
    PurchaseOrderCreate,
    PurchaseOrderHistoryRead,
    PurchaseOrderLineRead,
    PurchaseOrderWithLinesCreate,
)
from app.routers.auth import require_permission

router = APIRouter(prefix="/api/purchase-orders", tags=["purchasing"])


@router.get("", response_model=List[PurchaseOrder])
def list_purchase_orders(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "orders", "read")
    return session.exec(select(PurchaseOrder)).all()


@router.get("/with-lines", response_model=List[PurchaseOrderHistoryRead])
def list_purchase_orders_with_lines(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "orders", "read")
    orders = session.exec(select(PurchaseOrder).order_by(PurchaseOrder.id.desc())).all()
    if not orders:
        return []

    order_ids = [order.id for order in orders]
    lines = session.exec(
        select(PurchaseOrderLine, Item)
        .where(PurchaseOrderLine.purchase_order_id.in_(order_ids))
        .where(PurchaseOrderLine.item_id == Item.id)
    ).all()

    lines_by_order: dict[int, list[PurchaseOrderLineRead]] = {}
    for line, item in lines:
        lines_by_order.setdefault(line.purchase_order_id, []).append(
            PurchaseOrderLineRead(
                sku=item.sku,
                item_name=item.name,
                quantity=int(line.qty),
                dispatched_qty=int(line.dispatched_qty),
                remaining_qty=int(line.qty - line.dispatched_qty),
            )
        )

    history = []
    for order in orders:
        history.append(
            PurchaseOrderHistoryRead(
                id=order.id,
                customer_name=order.customer_name,
                sales_person=order.sales_person,
                order_timestamp=order.order_timestamp,
                status=order.status,
                lines=lines_by_order.get(order.id, []),
            )
        )
    return history


@router.post("", response_model=PurchaseOrder)
def create_purchase_order(
    payload: PurchaseOrderCreate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "purchase_order_generator", "write")
    order = PurchaseOrder.model_validate(payload)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.post("/with-lines", response_model=PurchaseOrder)
def create_purchase_order_with_lines(
    payload: PurchaseOrderWithLinesCreate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "purchase_order_generator", "write")
    if not payload.lines:
        raise HTTPException(status_code=400, detail="At least one line item is required")

    sku_list = [line.sku for line in payload.lines]
    items = session.exec(select(Item).where(Item.sku.in_(sku_list))).all()
    items_by_sku = {item.sku: item for item in items}

    missing = [sku for sku in sku_list if sku not in items_by_sku]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing SKUs: {', '.join(missing)}")

    shortages = []
    for line in payload.lines:
        item = items_by_sku[line.sku]
        if line.quantity <= 0:
            shortages.append(f"{line.sku} qty must be > 0")
        elif item.quantity < line.quantity:
            shortages.append(f"{line.sku} available {item.quantity}, requested {line.quantity}")

    # Orders stay pending until manually approved and dispatched.
    has_shortage = bool(shortages)
    order = PurchaseOrder(
        status="PENDING_DISPATCH",
        order_date=payload.order_timestamp.date(),
        order_timestamp=payload.order_timestamp,
        customer_name=payload.customer_name,
        sales_person=payload.sales_person,
        total_amount=0.0,
    )
    session.add(order)
    session.commit()
    session.refresh(order)

    for line in payload.lines:
        item = items_by_sku[line.sku]
        shortage_qty = max(0, line.quantity - item.quantity)

        session.add(
            PurchaseOrderLine(
                purchase_order_id=order.id,
                item_id=item.id,
                qty=line.quantity,
                unit_cost=0.0,
                dispatched_qty=0.0,
            )
        )

        if has_shortage:
            # If the order is pending, do not deduct any inventory yet.
            continue

        # Do not fulfill immediately; manual approval handles dispatch.
        continue

    session.commit()
    session.refresh(order)
    _recalc_production_requirements(session)
    return order


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
            session.add(planned)
        elif not in_progress:
            session.add(WorkOrder(item_id=item.id, qty=needed, status="PLANNED"))

    session.commit()


@router.get("/{order_id}", response_model=PurchaseOrder)
def get_purchase_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return order


@router.put("/{order_id}", response_model=PurchaseOrder)
def update_purchase_order(
    order_id: int, payload: PurchaseOrderCreate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "orders", "write")
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    for key, value in payload.model_dump().items():
        setattr(order, key, value)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.delete("/{order_id}")
def delete_purchase_order(order_id: int, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "orders", "write")
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    session.delete(order)
    session.commit()
    return {"ok": True}


@router.post("/{order_id}/approve-dispatch", response_model=PurchaseOrder)
def approve_and_dispatch(
    order_id: int, payload: DispatchQcPayload, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "orders", "write")
    order = session.get(PurchaseOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    lines = session.exec(
        select(PurchaseOrderLine, Item)
        .where(PurchaseOrderLine.purchase_order_id == order.id)
        .where(PurchaseOrderLine.item_id == Item.id)
    ).all()
    if not lines:
        raise HTTPException(status_code=400, detail="No order lines found")

    qc_by_sku = {entry.sku: entry for entry in payload.lines}
    for line, item in lines:
        qc = qc_by_sku.get(item.sku)
        if not qc:
            raise HTTPException(status_code=400, detail=f"Missing QC for {item.sku}")
        if qc.dispatch_qty <= 0:
            raise HTTPException(status_code=400, detail=f"Dispatch qty must be > 0 for {item.sku}")
        remaining = int(line.qty - line.dispatched_qty)
        if qc.dispatch_qty > remaining:
            raise HTTPException(status_code=400, detail=f"Dispatch qty exceeds remaining for {item.sku}")
        if qc.passed + qc.rejected != qc.dispatch_qty:
            raise HTTPException(status_code=400, detail=f"Passed + Rejected must equal dispatch qty for {item.sku}")
        required = qc.passed + qc.rejected + (qc.replacement_qty if qc.replaced else 0)
        if required < 0 or qc.passed < 0 or qc.rejected < 0:
            raise HTTPException(status_code=400, detail="Invalid QC quantities")
        if item.quantity < required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for {item.sku}: available {item.quantity}, needed {required}",
            )

    for line, item in lines:
        qc = qc_by_sku[item.sku]
        required = qc.passed + qc.rejected + (qc.replacement_qty if qc.replaced else 0)
        item.quantity -= int(required)
        session.add(item)
        line.dispatched_qty += qc.dispatch_qty
        session.add(line)
        session.add(
            DispatchLog(
                purchase_order_id=order.id,
                sku=item.sku,
                item_name=item.name,
                dispatch_qty=qc.dispatch_qty,
                rejected_qty=qc.rejected,
                passed_qty=qc.passed,
                proof_public_id=payload.proof_public_id,
                proof_version=payload.proof_version,
                proof_format=payload.proof_format,
                qc_name=payload.qc_name,
                qc_date=payload.qc_date,
            )
        )
        session.add(
            StockLedger(
                item_id=item.id,
                qty=required,
                txn_type="OUT",
                ref_type="PURCHASE_ORDER",
                ref_id=order.id,
            )
        )

    if all(int(line.qty - line.dispatched_qty) <= 0 for line, _ in lines):
        order.status = "CONFIRMED"
    else:
        order.status = "PENDING_DISPATCH"
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.get("/{order_id}/dispatch-logs", response_model=List[DispatchLogRead])
def list_dispatch_logs(order_id: int, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "orders", "read")
    logs = session.exec(
        select(DispatchLog).where(DispatchLog.purchase_order_id == order_id)
    ).all()
    return [
        DispatchLogRead(
            id=log.id,
            purchase_order_id=log.purchase_order_id,
            sku=log.sku,
            item_name=log.item_name,
            dispatch_qty=log.dispatch_qty,
            rejected_qty=log.rejected_qty,
            passed_qty=log.passed_qty,
            proof_public_id=log.proof_public_id,
            proof_version=log.proof_version,
            proof_format=log.proof_format,
            qc_name=log.qc_name,
            qc_date=log.qc_date,
            created_at=log.created_at,
        )
        for log in logs
    ]
