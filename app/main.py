import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlmodel import Session

from app.db import init_db, engine
from app.routers import (
    admin,
    assembly,
    backups,
    customers,
    inventory,
    media,
    packaging,
    production,
    purchase_orders,
    reports,
    sales_orders,
    vendors,
)
from app.routers.auth import router as auth_router, get_current_user, ensure_admin_seed

app = FastAPI(title="MSME Manufacturer ERP")

app.mount("/static", StaticFiles(directory="app/static"), name="static")

templates = Jinja2Templates(directory="app/templates")

_scheduler = None


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    enable_backup = os.getenv("ENABLE_DAILY_BACKUP", "false").lower() == "true"
    if enable_backup:
        from apscheduler.schedulers.background import BackgroundScheduler

        def _run_backup_job():
            from app.backups import run_backup

            with Session(engine) as session:
                run_backup(session)

        global _scheduler
        if _scheduler is None:
            _scheduler = BackgroundScheduler(daemon=True)
            _scheduler.add_job(_run_backup_job, "interval", days=1)
            _scheduler.start()


@app.get("/")
def root(request: Request):
    with Session(engine) as session:
        ensure_admin_seed(session)
        user = get_current_user(request, session)
        if not user:
            return RedirectResponse(url="/login")
        permissions = [] if not user.permissions else user.permissions.split(",")
        if user.permissions == "*":
            permissions = ["*"]
        return templates.TemplateResponse(
            "dashboard.html",
            {"request": request, "user": user, "permissions": permissions},
        )


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    public_prefixes = ("/static", "/login", "/docs", "/openapi", "/redoc")
    if request.url.path.startswith(public_prefixes):
        return await call_next(request)
    with Session(engine) as session:
        user = get_current_user(request, session)
        if not user:
            return RedirectResponse(url="/login")
        if user.permissions != "*":
            permissions = [] if not user.permissions else user.permissions.split(",")
            path_map = {
                "/final-good-store": "final_good_store",
                "/raw-material-store": "raw_material_store",
                "/purchase-department": "purchase_department",
                "/purchase-order-generator": "purchase_order_generator",
                "/orders": "orders",
                "/production-manager": "production_manager",
                "/assembly-line": "assembly_line",
                "/packaging": "packaging",
                "/boms": "boms",
                "/quality-checks": "quality_checks",
                "/production-reports": "production_reports",
                "/profile-settings": "profile_settings",
            }
            key = path_map.get(request.url.path)
            if key:
                has_access = any(p.startswith(f"{key}:") for p in permissions)
                if not has_access:
                    return RedirectResponse(url="/")
    return await call_next(request)


@app.get("/final-good-store")
def final_good_store(request: Request):
    return templates.TemplateResponse("final_good_store.html", {"request": request})


@app.get("/raw-material-store")
def raw_material_store(request: Request):
    return templates.TemplateResponse("raw_material_store.html", {"request": request})


@app.get("/purchase-department")
def purchase_department(request: Request):
    return templates.TemplateResponse("purchase_department.html", {"request": request})


@app.get("/boms")
def boms(request: Request):
    return templates.TemplateResponse("boms.html", {"request": request})


@app.get("/quality-checks")
def quality_checks(request: Request):
    return templates.TemplateResponse("quality_checks.html", {"request": request})


@app.get("/profile-settings")
def profile_settings(request: Request):
    return templates.TemplateResponse("profile_settings.html", {"request": request})


@app.get("/purchase-order-generator")
def purchase_order_generator(request: Request):
    return templates.TemplateResponse("purchase_order_generator.html", {"request": request})


@app.get("/orders")
def orders(request: Request):
    return templates.TemplateResponse("orders.html", {"request": request})


@app.get("/production-reports")
def production_reports(request: Request):
    return templates.TemplateResponse("production_reports.html", {"request": request})


@app.get("/production-manager")
def production_manager(request: Request):
    return templates.TemplateResponse("production_manager.html", {"request": request})


@app.get("/assembly-line")
def assembly_line(request: Request):
    return templates.TemplateResponse("assembly_line.html", {"request": request})


@app.get("/packaging")
def packaging_page(request: Request):
    return templates.TemplateResponse("packaging.html", {"request": request})


app.include_router(inventory.router)
app.include_router(assembly.router)
app.include_router(packaging.router)
app.include_router(production.router)
app.include_router(customers.router)
app.include_router(vendors.router)
app.include_router(sales_orders.router)
app.include_router(purchase_orders.router)
app.include_router(reports.router)
app.include_router(media.router)
app.include_router(backups.router)
app.include_router(admin.router)
app.include_router(auth_router)
