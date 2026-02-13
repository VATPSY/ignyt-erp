from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import SalesOrder
from app.schemas import SalesOrderCreate

router = APIRouter(prefix="/api/sales-orders", tags=["sales"])


@router.get("", response_model=List[SalesOrder])
def list_sales_orders(session: Session = Depends(get_session)):
    return session.exec(select(SalesOrder)).all()


@router.post("", response_model=SalesOrder)
def create_sales_order(payload: SalesOrderCreate, session: Session = Depends(get_session)):
    order = SalesOrder.model_validate(payload)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.get("/{order_id}", response_model=SalesOrder)
def get_sales_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return order


@router.put("/{order_id}", response_model=SalesOrder)
def update_sales_order(order_id: int, payload: SalesOrderCreate, session: Session = Depends(get_session)):
    order = session.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    for key, value in payload.model_dump().items():
        setattr(order, key, value)
    session.add(order)
    session.commit()
    session.refresh(order)
    return order


@router.delete("/{order_id}")
def delete_sales_order(order_id: int, session: Session = Depends(get_session)):
    order = session.get(SalesOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    session.delete(order)
    session.commit()
    return {"ok": True}
