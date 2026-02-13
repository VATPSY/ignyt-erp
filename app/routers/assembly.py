from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.models import AssemblyOrder, Item, PackagingOrder
from app.schemas import AssemblyOrderRead, AssemblyOrderUpdate
from app.routers.auth import require_permission

router = APIRouter(prefix="/api/assembly", tags=["assembly"])


@router.get("", response_model=List[AssemblyOrderRead])
def list_assembly(request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "assembly_line", "read")
    rows = session.exec(
        select(AssemblyOrder, Item)
        .where(AssemblyOrder.item_id == Item.id)
        .order_by(AssemblyOrder.id.desc())
    ).all()
    return [
        AssemblyOrderRead(
            id=assembly.id,
            sku=item.sku,
            item_name=item.name,
            qty_total=assembly.qty_total,
            qty_assembled=assembly.qty_assembled,
            status=assembly.status,
        )
        for assembly, item in rows
    ]


@router.put("/{assembly_id}", response_model=AssemblyOrderRead)
def update_assembly(
    assembly_id: int, payload: AssemblyOrderUpdate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "assembly_line", "write")
    assembly = session.get(AssemblyOrder, assembly_id)
    if not assembly:
        raise HTTPException(status_code=404, detail="Assembly order not found")

    if payload.status not in ["PLANNED", "IN_PROGRESS", "DONE"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    if payload.qty_assembled < 0 or payload.qty_assembled > assembly.qty_total:
        raise HTTPException(status_code=400, detail="Invalid assembled quantity")

    if payload.qty_assembled <= 0:
        raise HTTPException(status_code=400, detail="Assembled quantity must be greater than 0")

    if payload.status == "DONE" and payload.qty_assembled < assembly.qty_total:
        # Split into completed and remaining
        completed = AssemblyOrder(
            work_order_id=assembly.work_order_id,
            item_id=assembly.item_id,
            qty_total=payload.qty_assembled,
            qty_assembled=payload.qty_assembled,
            status="DONE",
        )
        remaining_qty = assembly.qty_total - payload.qty_assembled
        assembly.qty_total = remaining_qty
        assembly.qty_assembled = 0
        assembly.status = "PLANNED"
        session.add(completed)
        session.add(assembly)
        session.commit()
        session.refresh(completed)

        # Send completed qty to packaging
        session.add(
            PackagingOrder(
                work_order_id=completed.work_order_id,
                item_id=completed.item_id,
                qty_total=completed.qty_total,
                qty_packed=0,
                status="PLANNED",
            )
        )
        session.commit()

        item = session.get(Item, completed.item_id)
        return AssemblyOrderRead(
            id=completed.id,
            sku=item.sku if item else "",
            item_name=item.name if item else "",
            qty_total=completed.qty_total,
            qty_assembled=completed.qty_assembled,
            status=completed.status,
        )

    assembly.qty_assembled = payload.qty_assembled
    assembly.status = payload.status
    session.add(assembly)
    session.commit()
    session.refresh(assembly)

    if payload.status == "DONE" and payload.qty_assembled == assembly.qty_total:
        session.add(
            PackagingOrder(
                work_order_id=assembly.work_order_id,
                item_id=assembly.item_id,
                qty_total=assembly.qty_total,
                qty_packed=0,
                status="PLANNED",
            )
        )
        session.commit()

    item = session.get(Item, assembly.item_id)
    return AssemblyOrderRead(
        id=assembly.id,
        sku=item.sku if item else "",
        item_name=item.name if item else "",
        qty_total=assembly.qty_total,
        qty_assembled=assembly.qty_assembled,
        status=assembly.status,
    )
