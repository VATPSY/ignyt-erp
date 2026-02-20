from datetime import date, datetime
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship


class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sku: str = Field(index=True, unique=True)
    name: str
    unit: str = "pcs"
    quantity: int = 0
    reorder_level: int = 0
    active: bool = True

    stock_ledger: List["StockLedger"] = Relationship(back_populates="item")


class StockLedger(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="item.id")
    qty: float
    txn_type: str  # IN / OUT / ADJUST
    ref_type: Optional[str] = None
    ref_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    item: Optional["Item"] = Relationship(back_populates="stock_ledger")


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

    sales_orders: List["SalesOrder"] = Relationship(back_populates="customer")


class Vendor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

    purchase_orders: List["PurchaseOrder"] = Relationship(back_populates="vendor")


class SalesOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    status: str = "DRAFT"
    order_date: date = Field(default_factory=date.today)
    total_amount: float = 0.0

    customer: Optional["Customer"] = Relationship(back_populates="sales_orders")
    lines: List["SalesOrderLine"] = Relationship(back_populates="sales_order")


class SalesOrderLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sales_order_id: int = Field(foreign_key="salesorder.id")
    item_id: int = Field(foreign_key="item.id")
    qty: float
    unit_price: float

    sales_order: Optional["SalesOrder"] = Relationship(back_populates="lines")
    item: Optional["Item"] = Relationship()


class PurchaseOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    vendor_id: Optional[int] = Field(default=None, foreign_key="vendor.id")
    status: str = "DRAFT"
    order_date: date = Field(default_factory=date.today)
    order_timestamp: Optional[datetime] = None
    customer_name: Optional[str] = None
    sales_person: Optional[str] = None
    total_amount: float = 0.0

    vendor: Optional["Vendor"] = Relationship(back_populates="purchase_orders")
    lines: List["PurchaseOrderLine"] = Relationship(back_populates="purchase_order")


class PurchaseOrderLine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    purchase_order_id: int = Field(foreign_key="purchaseorder.id")
    item_id: int = Field(foreign_key="item.id")
    qty: float
    unit_cost: float
    dispatched_qty: float = 0.0

    purchase_order: Optional["PurchaseOrder"] = Relationship(back_populates="lines")
    item: Optional["Item"] = Relationship()


class DispatchLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    purchase_order_id: int = Field(foreign_key="purchaseorder.id")
    sku: str
    item_name: str
    dispatch_qty: int
    rejected_qty: int
    passed_qty: int
    proof_public_id: Optional[str] = None
    proof_version: Optional[str] = None
    proof_format: Optional[str] = None
    qc_name: str
    qc_date: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="item.id")
    qty: float
    planned_qty: float = 0.0
    status: str = "PLANNED"
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    item: Optional["Item"] = Relationship()


class PackagingOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_order_id: int = Field(foreign_key="workorder.id")
    item_id: int = Field(foreign_key="item.id")
    qty_total: int
    qty_packed: int = 0
    status: str = "PLANNED"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class AssemblyOrder(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_order_id: int = Field(foreign_key="workorder.id")
    item_id: int = Field(foreign_key="item.id")
    qty_total: int
    qty_assembled: int = 0
    status: str = "PLANNED"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str
    permissions: str = ""  # comma-separated module keys


class UserAuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    actor: str
    action: str
    target_username: str
    permissions: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Invoice(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    sales_order_id: Optional[int] = Field(default=None, foreign_key="salesorder.id")
    invoice_date: date = Field(default_factory=date.today)
    total_amount: float = 0.0
    status: str = "UNPAID"
