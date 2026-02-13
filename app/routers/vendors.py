from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models import Vendor
from app.schemas import VendorCreate

router = APIRouter(prefix="/api/vendors", tags=["purchasing"])


@router.get("", response_model=List[Vendor])
def list_vendors(session: Session = Depends(get_session)):
    return session.exec(select(Vendor)).all()


@router.post("", response_model=Vendor)
def create_vendor(payload: VendorCreate, session: Session = Depends(get_session)):
    vendor = Vendor.model_validate(payload)
    session.add(vendor)
    session.commit()
    session.refresh(vendor)
    return vendor


@router.get("/{vendor_id}", response_model=Vendor)
def get_vendor(vendor_id: int, session: Session = Depends(get_session)):
    vendor = session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    return vendor


@router.put("/{vendor_id}", response_model=Vendor)
def update_vendor(vendor_id: int, payload: VendorCreate, session: Session = Depends(get_session)):
    vendor = session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    for key, value in payload.model_dump().items():
        setattr(vendor, key, value)
    session.add(vendor)
    session.commit()
    session.refresh(vendor)
    return vendor


@router.delete("/{vendor_id}")
def delete_vendor(vendor_id: int, session: Session = Depends(get_session)):
    vendor = session.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")
    session.delete(vendor)
    session.commit()
    return {"ok": True}
