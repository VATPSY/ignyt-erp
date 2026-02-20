from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, delete

from app.db import get_session
from app.models import AssemblyOrder, DispatchLog, PackagingOrder, PurchaseOrder, PurchaseOrderLine, StockLedger, WorkOrder
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _ensure_admin(request: Request, session: Session) -> None:
    user = get_current_user(request, session)
    if not user or user.permissions != "*":
        raise HTTPException(status_code=403, detail="Admin only")


@router.post("/clear")
def clear_data(scope: str, request: Request, session: Session = Depends(get_session)):
    _ensure_admin(request, session)

    if scope == "orders":
        session.exec(delete(DispatchLog))
        session.exec(delete(PurchaseOrderLine))
        session.exec(delete(PurchaseOrder))
        session.exec(delete(StockLedger).where(StockLedger.ref_type == "PURCHASE_ORDER"))
    elif scope == "production":
        session.exec(delete(WorkOrder))
    elif scope == "assembly":
        session.exec(delete(AssemblyOrder))
    elif scope == "packaging":
        session.exec(delete(PackagingOrder))
    else:
        raise HTTPException(status_code=400, detail="Invalid scope")

    session.commit()
    return {"ok": True}
