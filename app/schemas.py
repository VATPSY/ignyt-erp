from datetime import date, datetime
from typing import Optional, List

from sqlmodel import SQLModel


class ItemCreate(SQLModel):
    sku: str
    name: str
    unit: str = "pcs"
    quantity: int = 0
    reorder_level: int = 0
    active: bool = True


class CustomerCreate(SQLModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class VendorCreate(SQLModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class SalesOrderCreate(SQLModel):
    customer_id: Optional[int] = None
    status: str = "DRAFT"
    order_date: date = date.today()
    total_amount: float = 0.0


class PurchaseOrderCreate(SQLModel):
    vendor_id: Optional[int] = None
    status: str = "DRAFT"
    order_date: date = date.today()
    order_timestamp: Optional[datetime] = None
    customer_name: Optional[str] = None
    sales_person: Optional[str] = None
    total_amount: float = 0.0


class WorkOrderCreate(SQLModel):
    sku: str
    quantity: int
    status: str = "PLANNED"
    due_date: Optional[date] = None


class WorkOrderRead(SQLModel):
    id: int
    sku: str
    item_name: str
    quantity: float
    status: str


class WorkOrderUpdate(SQLModel):
    status: str


class WorkOrderProduce(SQLModel):
    quantity: int


class PackagingOrderRead(SQLModel):
    id: int
    sku: str
    item_name: str
    qty_total: int
    qty_packed: int
    status: str


class PackagingOrderUpdate(SQLModel):
    qty_packed: int
    status: str


class AssemblyOrderRead(SQLModel):
    id: int
    sku: str
    item_name: str
    qty_total: int
    qty_assembled: int
    status: str


class AssemblyOrderUpdate(SQLModel):
    qty_assembled: int
    status: str


class UserCreate(SQLModel):
    username: str
    password: str
    permissions: List[str] = []


class UserUpdate(SQLModel):
    password: Optional[str] = None
    permissions: Optional[List[str]] = None


class UserRead(SQLModel):
    id: int
    username: str
    permissions: List[str] = []


class UserAuditRead(SQLModel):
    id: int
    actor: str
    action: str
    target_username: str
    permissions: List[str] = []
    created_at: datetime


class DispatchLogRead(SQLModel):
    id: int
    purchase_order_id: int
    sku: str
    item_name: str
    dispatch_qty: int
    rejected_qty: int
    passed_qty: int
    qc_name: str
    qc_date: str
    created_at: datetime


class PurchaseOrderLineCreate(SQLModel):
    sku: str
    quantity: int


class PurchaseOrderWithLinesCreate(SQLModel):
    customer_name: str
    sales_person: str
    order_timestamp: datetime
    lines: List[PurchaseOrderLineCreate]


class PurchaseOrderLineRead(SQLModel):
    sku: str
    item_name: str
    quantity: int
    dispatched_qty: int = 0
    remaining_qty: int = 0


class PurchaseOrderHistoryRead(SQLModel):
    id: int
    customer_name: Optional[str] = None
    sales_person: Optional[str] = None
    order_timestamp: Optional[datetime] = None
    status: str
    lines: List[PurchaseOrderLineRead] = []


class DispatchQcLine(SQLModel):
    sku: str
    dispatch_qty: int
    passed: int
    rejected: int
    replaced: bool = False
    replacement_qty: int = 0


class DispatchQcPayload(SQLModel):
    qc_name: str
    qc_date: str
    lines: List[DispatchQcLine]


class ProductionReportRow(SQLModel):
    sku: str
    item_name: str
    planned: int
    produced: int
    rejected: int


class ProductionReportResponse(SQLModel):
    start: datetime
    end: datetime
    rows: List[ProductionReportRow]
    totals: ProductionReportRow
