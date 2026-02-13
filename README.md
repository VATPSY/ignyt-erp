# MSME Manufacturer ERP (Scaffold)

A simple, extensible ERP scaffold for small manufacturers. Includes pages, database schema, and REST APIs.

## Modules
- Dashboard
- Inventory (items, stock)
- Production (work orders)
- Sales (orders, customers)
- Purchasing (vendors, purchase orders)
- Finance (invoices)

## Quick start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open: http://127.0.0.1:8000

## API docs
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Notes
- Default DB is SQLite at `erp.db`
- Update `DATABASE_URL` in `.env` as needed
