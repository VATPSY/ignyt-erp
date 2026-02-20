from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select, delete

from app.db import get_session
from app.models import Item, StockLedger
from app.schemas import ItemCreate
from app.routers.auth import get_current_user, require_any_permission, require_permission

router = APIRouter(prefix="/api/items", tags=["inventory"])


@router.get("", response_model=List[Item])
def list_items(request: Request, session: Session = Depends(get_session)):
    require_any_permission(
        request,
        session,
        ["final_good_store", "purchase_order_generator", "orders", "production_manager"],
        "read",
    )
    return session.exec(select(Item)).all()


@router.post("", response_model=Item)
def create_item(payload: ItemCreate, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "final_good_store", "write")
    item = Item.model_validate(payload)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.get("/{item_id}", response_model=Item)
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.put("/{item_id}", response_model=Item)
def update_item(
    item_id: int, payload: ItemCreate, request: Request, session: Session = Depends(get_session)
):
    require_permission(request, session, "final_good_store", "write")
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.delete("/{item_id}")
def delete_item(item_id: int, request: Request, session: Session = Depends(get_session)):
    require_permission(request, session, "final_good_store", "write")
    item = session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    session.delete(item)
    session.commit()
    return {"ok": True}


@router.post("/clear")
def clear_inventory(request: Request, session: Session = Depends(get_session)):
    user = get_current_user(request, session)
    if not user or user.permissions != "*":
        raise HTTPException(status_code=403, detail="Admin only")
    session.exec(delete(StockLedger))
    session.exec(delete(Item))
    session.commit()
    return {"ok": True}
