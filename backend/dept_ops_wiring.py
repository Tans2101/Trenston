"""Register Sales order-book, Maintenance ops, and Procurement spend routes.

Called from server.py after helpers/deps exist. Keeps the large additive surface
out of the already-huge server module body.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import department_access as dept_access
import department_migrate as dept_migrate
import departments_catalog as dept_catalog
import decision_engine
import maintenance_ops as maint_ops
import procurement_spend as proc_spend
import sales_order_book as sales_ob
import money_fmt
import tz_utils

logger = logging.getLogger("helm.dept_ops")


# ----- Request bodies (module-level so FastAPI binds them as JSON bodies) -----
class OrderBookCreate(BaseModel):
    buyer_name: str
    country: str
    product: str
    price: float
    quantity: float
    status: str = "expected"
    expected_close_month: str = ""
    source_deal_id: Optional[str] = None
    notes: str = ""


class OrderBookPatch(BaseModel):
    buyer_name: Optional[str] = None
    country: Optional[str] = None
    product: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    status: Optional[str] = None
    expected_close_month: Optional[str] = None
    source_deal_id: Optional[str] = None
    notes: Optional[str] = None


class SalesTargetPut(BaseModel):
    month: str
    target: float


class SpareInput(BaseModel):
    part_name: str
    equipment_name: str = ""
    equipment_names: list[str] = Field(default_factory=list)
    quantity_on_hand: float = 0
    minimum_threshold: float = 0
    unit: str = "pcs"


class SparePatch(BaseModel):
    part_name: Optional[str] = None
    equipment_name: Optional[str] = None
    equipment_names: Optional[list[str]] = None
    quantity_on_hand: Optional[float] = None
    minimum_threshold: Optional[float] = None
    unit: Optional[str] = None


class ScheduleInput(BaseModel):
    equipment_name: str
    task: str
    frequency_days: int
    last_done_at: Optional[str] = None


class SchedulePatch(BaseModel):
    equipment_name: Optional[str] = None
    task: Optional[str] = None
    frequency_days: Optional[int] = None
    last_done_at: Optional[str] = None
    mark_done: Optional[bool] = None


class ContractInput(BaseModel):
    equipment_name: str
    vendor_name: str
    coverage_start: str
    coverage_end: str
    renewal_date: str = ""
    cost: Optional[float] = None
    scope_notes: str = ""


class ContractPatch(BaseModel):
    equipment_name: Optional[str] = None
    vendor_name: Optional[str] = None
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    renewal_date: Optional[str] = None
    cost: Optional[float] = None
    scope_notes: Optional[str] = None


class MaintSettingsPut(BaseModel):
    monthly_budget: Optional[float] = None
    clear_budget: bool = False


class MaintCostCreate(BaseModel):
    amount: float
    description: str = ""
    month: str = ""
    category: str = "general"


class ProcSettingsPut(BaseModel):
    monthly_budget: Optional[float] = None
    clear_budget: bool = False


def register(api_router, *, db, get_principal, invalidate_workspace_list_cache, invalidate_departments_cache):
    """Attach all new department-ops endpoints onto api_router.

    `db` is resolved at request time via server.db when available so TestClient
    patches of server.db (same pattern as procurement routes) take effect.
    """

    class _LiveDb:
        def __getattr__(self, name):
            try:
                import server as _server
                return getattr(_server.db, name)
            except Exception:
                return getattr(db, name)

    db = _LiveDb()

    # ----- Sales department gate (mirrors procurement) -----
    async def _ws_today(principal: dict):
        """Workspace-local calendar day (overdue flags, current month)."""
        ws = await db.workspaces.find_one(
            {"workspace_id": principal["workspace_id"]}, {"_id": 0, "timezone": 1},
        )
        return tz_utils.workspace_today(ws)

    async def _currency_fields(principal: dict) -> dict:
        ws = await db.workspaces.find_one(
            {"workspace_id": principal["workspace_id"]}, {"_id": 0, "financial_settings.currency": 1},
        ) or {}
        code = money_fmt.normalize_currency((ws.get("financial_settings") or {}).get("currency"))
        return {"currency": code, "currency_symbol": money_fmt.currency_symbol(code)}

    async def _sales_department(principal: dict) -> dict:
        doc = await dept_migrate.get_enabled_department(
            db, principal["workspace_id"], dept_catalog.TYPE_SALES,
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Sales department is not enabled")
        if not await dept_access.can_access_department(db, principal, doc):
            raise HTTPException(status_code=403, detail="You do not have access to Sales")
        return doc

    def _can_lead_sales(principal: dict, membership: dict | None) -> bool:
        if dept_access.is_workspace_ceo(principal):
            return True
        return bool(membership) and membership.get("role") == "lead"

    # ===================== Sales order book =====================
    def _strip_entry(row: dict) -> dict:
        return {k: v for k, v in row.items() if k != "_id"}

    @api_router.get("/sales/order-book")
    async def list_sales_order_book(
        principal=Depends(get_principal),
        status: Optional[str] = Query(None),
        country: Optional[str] = Query(None),
        month_from: Optional[str] = Query(None),
        month_to: Optional[str] = Query(None),
    ):
        dept = await _sales_department(principal)
        filt: dict = {"department_id": dept["department_id"]}
        if status is not None:
            st = status.strip().lower()
            if st not in sales_ob.ORDER_BOOK_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status filter")
            filt["status"] = st
        if country is not None and country.strip():
            filt["country"] = {"$regex": f"^{re.escape(country.strip())}$", "$options": "i"}
        rows = await db.sales_order_book.find(filt, {"_id": 0}).sort("updated_at", -1).to_list(5000)
        mf = sales_ob.normalize_month(month_from)
        mt = sales_ob.normalize_month(month_to)
        if mf or mt:
            filtered = []
            for r in rows:
                am = sales_ob.attribute_month(r) or ""
                if mf and am < mf:
                    continue
                if mt and am > mt:
                    continue
                filtered.append(r)
            rows = filtered
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        is_lead = _can_lead_sales(principal, membership)
        summary = sales_ob.order_book_summary(rows)
        month = sales_ob.current_month(await _ws_today(principal))
        target_row = await db.sales_targets.find_one(
            {"workspace_id": principal["workspace_id"], "month": month},
            {"_id": 0},
        )
        # Settled: actual = confirmed order-book only. Deals/stages are never consulted.
        confirmed_actual = summary["confirmed_this_month"]
        target_vs = sales_ob.target_vs_actual(target_row=target_row, confirmed_actual=confirmed_actual)
        return {
            "department_id": dept["department_id"],
            "entries": rows,
            "statuses": sorted(sales_ob.ORDER_BOOK_STATUSES),
            "summary": summary,
            "target_vs_actual": target_vs,
            "is_ceo": dept_access.is_workspace_ceo(principal),
            "is_lead": is_lead,
            "my_user_id": principal["user_id"],
            **(await _currency_fields(principal)),
        }

    @api_router.get("/sales/order-book/summary")
    async def sales_order_book_summary(principal=Depends(get_principal)):
        data = await list_sales_order_book(
            principal=principal,
            status=None,
            country=None,
            month_from=None,
            month_to=None,
        )
        return {
            "summary": data["summary"],
            "target_vs_actual": data["target_vs_actual"],
        }

    @api_router.post("/sales/order-book")
    async def create_sales_order_book(payload: OrderBookCreate, principal=Depends(get_principal)):
        dept = await _sales_department(principal)
        buyer = (payload.buyer_name or "").strip()
        country = (payload.country or "").strip()
        product = (payload.product or "").strip()
        if not buyer:
            raise HTTPException(status_code=400, detail="buyer_name is required")
        if not country:
            raise HTTPException(status_code=400, detail="country is required")
        if not product:
            raise HTTPException(status_code=400, detail="product is required")
        try:
            price = float(payload.price)
            qty = float(payload.quantity)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="price and quantity must be numbers")
        if price < 0:
            raise HTTPException(status_code=400, detail="price cannot be negative")
        if qty <= 0:
            raise HTTPException(status_code=400, detail="quantity must be positive")
        status = (payload.status or "expected").strip().lower()
        if status not in sales_ob.ORDER_BOOK_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid status")
        em = sales_ob.normalize_month(payload.expected_close_month) or ""
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": f"sob_{uuid.uuid4().hex[:10]}",
            "workspace_id": principal["workspace_id"],
            "department_id": dept["department_id"],
            "created_by_user_id": principal["user_id"],
            "buyer_name": buyer[:200],
            "country": country[:100],
            "product": product[:200],
            "price": round(price, 4),
            "quantity": round(qty, 4),
            "total_value": sales_ob.compute_total(price, qty),
            "status": status,
            "expected_close_month": em,
            "source_deal_id": (payload.source_deal_id or "").strip() or None,
            "notes": (payload.notes or "").strip()[:2000],
            "created_at": now,
            "updated_at": now,
        }
        await db.sales_order_book.insert_one(dict(entry))
        invalidate_workspace_list_cache(principal["workspace_id"], "sales_order_book")
        return {"ok": True, "entry": _strip_entry(entry)}

    @api_router.patch("/sales/order-book/{entry_id}")
    async def patch_sales_order_book(
        entry_id: str, payload: OrderBookPatch, principal=Depends(get_principal),
    ):
        dept = await _sales_department(principal)
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        is_lead = _can_lead_sales(principal, membership)
        entry = await db.sales_order_book.find_one(
            {"id": entry_id, "department_id": dept["department_id"]}, {"_id": 0},
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Order book entry not found")
        is_owner = entry.get("created_by_user_id") == principal["user_id"]
        if not (is_lead or is_owner):
            raise HTTPException(status_code=403, detail="You can only edit your own order book entries")
        upd: dict = {}
        if payload.buyer_name is not None:
            v = payload.buyer_name.strip()
            if not v:
                raise HTTPException(status_code=400, detail="buyer_name is required")
            upd["buyer_name"] = v[:200]
        if payload.country is not None:
            v = payload.country.strip()
            if not v:
                raise HTTPException(status_code=400, detail="country is required")
            upd["country"] = v[:100]
        if payload.product is not None:
            v = payload.product.strip()
            if not v:
                raise HTTPException(status_code=400, detail="product is required")
            upd["product"] = v[:200]
        price = entry.get("price")
        qty = entry.get("quantity")
        if payload.price is not None:
            try:
                price = float(payload.price)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="price must be a number")
            if price < 0:
                raise HTTPException(status_code=400, detail="price cannot be negative")
            upd["price"] = round(price, 4)
        if payload.quantity is not None:
            try:
                qty = float(payload.quantity)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="quantity must be a number")
            if qty <= 0:
                raise HTTPException(status_code=400, detail="quantity must be positive")
            upd["quantity"] = round(qty, 4)
        if payload.price is not None or payload.quantity is not None:
            upd["total_value"] = sales_ob.compute_total(price, qty)
        if payload.status is not None:
            st = payload.status.strip().lower()
            if st not in sales_ob.ORDER_BOOK_STATUSES:
                raise HTTPException(status_code=400, detail="Invalid status")
            upd["status"] = st
        if payload.expected_close_month is not None:
            upd["expected_close_month"] = sales_ob.normalize_month(payload.expected_close_month) or ""
        if payload.source_deal_id is not None:
            upd["source_deal_id"] = (payload.source_deal_id or "").strip() or None
        if payload.notes is not None:
            upd["notes"] = payload.notes.strip()[:2000]
        if not upd:
            return {"ok": True, "entry": entry}
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.sales_order_book.update_one(
            {"id": entry_id, "department_id": dept["department_id"]}, {"$set": upd},
        )
        invalidate_workspace_list_cache(principal["workspace_id"], "sales_order_book")
        return {"ok": True, "entry": {**entry, **upd}}

    @api_router.delete("/sales/order-book/{entry_id}")
    async def delete_sales_order_book(entry_id: str, principal=Depends(get_principal)):
        dept = await _sales_department(principal)
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        is_lead = _can_lead_sales(principal, membership)
        entry = await db.sales_order_book.find_one(
            {"id": entry_id, "department_id": dept["department_id"]}, {"_id": 0},
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Order book entry not found")
        is_owner = entry.get("created_by_user_id") == principal["user_id"]
        if not (is_lead or is_owner):
            raise HTTPException(status_code=403, detail="You can only delete your own order book entries")
        await db.sales_order_book.delete_one({"id": entry_id, "department_id": dept["department_id"]})
        invalidate_workspace_list_cache(principal["workspace_id"], "sales_order_book")
        return {"ok": True}

    @api_router.get("/sales/targets")
    async def list_sales_targets(principal=Depends(get_principal)):
        await _sales_department(principal)
        rows = await db.sales_targets.find(
            {"workspace_id": principal["workspace_id"]}, {"_id": 0},
        ).sort("month", -1).to_list(36)
        month = sales_ob.current_month(await _ws_today(principal))
        current = next((r for r in rows if r.get("month") == month), None)
        return {"targets": rows, "current_month": month, "current": current}

    @api_router.put("/sales/targets")
    async def put_sales_target(payload: SalesTargetPut, principal=Depends(get_principal)):
        dept = await _sales_department(principal)
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        if not _can_lead_sales(principal, membership):
            raise HTTPException(status_code=403, detail="Only a Sales lead or CEO can set targets")
        month = sales_ob.normalize_month(payload.month)
        if not month:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        try:
            target = float(payload.target)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="target must be a number")
        if target < 0:
            raise HTTPException(status_code=400, detail="target cannot be negative")
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "workspace_id": principal["workspace_id"],
            "month": month,
            "target": round(target, 2),
            "updated_at": now,
            "updated_by": principal["user_id"],
        }
        existing = await db.sales_targets.find_one(
            {"workspace_id": principal["workspace_id"], "month": month}, {"_id": 0, "id": 1},
        )
        if existing:
            await db.sales_targets.update_one(
                {"workspace_id": principal["workspace_id"], "month": month},
                {"$set": doc},
            )
            doc["id"] = existing.get("id")
        else:
            doc["id"] = f"st_{uuid.uuid4().hex[:10]}"
            doc["created_at"] = now
            await db.sales_targets.insert_one(dict(doc))
        invalidate_workspace_list_cache(principal["workspace_id"], "sales_order_book")
        return {"ok": True, "target": {k: v for k, v in doc.items() if k != "_id"}}

    # ===================== Maintenance spares / schedules / contracts / costs =====================
    async def _maint_dept(principal: dict) -> dict:
        doc = await db.departments.find_one(
            {
                "workspace_id": principal["workspace_id"],
                "type": dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
                "enabled": True,
            },
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Engineering & Maintenance department is not enabled")
        if not await dept_access.can_access_department(db, principal, doc):
            raise HTTPException(status_code=403, detail="You do not have access to Engineering & Maintenance")
        return doc

    def _can_lead_maint(principal: dict, membership: dict | None) -> bool:
        if dept_access.is_workspace_ceo(principal):
            return True
        return bool(membership) and membership.get("role") == "lead"

    async def _require_maint_lead(principal: dict, dept: dict):
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        if not _can_lead_maint(principal, membership):
            raise HTTPException(status_code=403, detail="Only a lead or CEO can manage this")
        return membership

    def _equipment_names_from_payload(payload) -> list[str]:
        names = []
        if getattr(payload, "equipment_names", None):
            names.extend([str(n).strip() for n in payload.equipment_names if str(n).strip()])
        single = (getattr(payload, "equipment_name", None) or "").strip()
        if single and single not in names:
            names.append(single)
        return names

    @api_router.get("/maintenance/spares")
    async def list_maintenance_spares(principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        rows = await db.maintenance_spares.find(
            {"department_id": dept["department_id"]}, {"_id": 0},
        ).sort("part_name", 1).to_list(2000)
        items = [maint_ops.enrich_spare(r) for r in rows]
        below = [s for s in items if s["is_below_threshold"]]
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        return {
            "spares": items,
            "below_threshold": below,
            "below_threshold_count": len(below),
            "is_lead": _can_lead_maint(principal, membership),
            "is_ceo": dept_access.is_workspace_ceo(principal),
        }

    @api_router.post("/maintenance/spares")
    async def create_maintenance_spare(payload: SpareInput, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        name = (payload.part_name or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="part_name is required")
        now = datetime.now(timezone.utc).isoformat()
        eq_names = _equipment_names_from_payload(payload)
        doc = {
            "id": f"msp_{uuid.uuid4().hex[:10]}",
            "department_id": dept["department_id"],
            "workspace_id": principal["workspace_id"],
            "part_name": name[:200],
            "equipment_name": eq_names[0] if eq_names else "",
            "equipment_names": eq_names,
            "quantity_on_hand": float(payload.quantity_on_hand or 0),
            "minimum_threshold": float(payload.minimum_threshold or 0),
            "unit": (payload.unit or "pcs").strip()[:32] or "pcs",
            "created_at": now,
            "updated_at": now,
        }
        if doc["quantity_on_hand"] < 0 or doc["minimum_threshold"] < 0:
            raise HTTPException(status_code=400, detail="quantities cannot be negative")
        await db.maintenance_spares.insert_one(dict(doc))
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "spare": maint_ops.enrich_spare(doc)}

    @api_router.patch("/maintenance/spares/{spare_id}")
    async def patch_maintenance_spare(
        spare_id: str, payload: SparePatch, principal=Depends(get_principal),
    ):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        row = await db.maintenance_spares.find_one(
            {"id": spare_id, "department_id": dept["department_id"]}, {"_id": 0},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Spare not found")
        upd: dict = {}
        if payload.part_name is not None:
            v = payload.part_name.strip()
            if not v:
                raise HTTPException(status_code=400, detail="part_name is required")
            upd["part_name"] = v[:200]
        if payload.equipment_names is not None or payload.equipment_name is not None:
            names = _equipment_names_from_payload(payload)
            upd["equipment_names"] = names
            upd["equipment_name"] = names[0] if names else ""
        if payload.quantity_on_hand is not None:
            q = float(payload.quantity_on_hand)
            if q < 0:
                raise HTTPException(status_code=400, detail="quantity_on_hand cannot be negative")
            upd["quantity_on_hand"] = q
        if payload.minimum_threshold is not None:
            m = float(payload.minimum_threshold)
            if m < 0:
                raise HTTPException(status_code=400, detail="minimum_threshold cannot be negative")
            upd["minimum_threshold"] = m
        if payload.unit is not None:
            upd["unit"] = (payload.unit or "pcs").strip()[:32] or "pcs"
        if not upd:
            return {"ok": True, "spare": maint_ops.enrich_spare(row)}
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.maintenance_spares.update_one(
            {"id": spare_id, "department_id": dept["department_id"]}, {"$set": upd},
        )
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "spare": maint_ops.enrich_spare({**row, **upd})}

    @api_router.delete("/maintenance/spares/{spare_id}")
    async def delete_maintenance_spare(spare_id: str, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        result = await db.maintenance_spares.delete_one(
            {"id": spare_id, "department_id": dept["department_id"]},
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Spare not found")
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True}

    @api_router.get("/maintenance/schedules")
    async def list_maintenance_schedules(principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        rows = await db.maintenance_schedules.find(
            {"department_id": dept["department_id"]}, {"_id": 0},
        ).sort("equipment_name", 1).to_list(2000)
        today = await _ws_today(principal)
        items = [maint_ops.enrich_schedule(r, today=today) for r in rows]
        overdue = [s for s in items if s["is_overdue"]]
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        return {
            "schedules": items,
            "overdue": overdue,
            "overdue_count": len(overdue),
            "is_lead": _can_lead_maint(principal, membership),
            "is_ceo": dept_access.is_workspace_ceo(principal),
        }

    @api_router.post("/maintenance/schedules")
    async def create_maintenance_schedule(payload: ScheduleInput, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        eq = (payload.equipment_name or "").strip()
        task = (payload.task or "").strip()
        if not eq or not task:
            raise HTTPException(status_code=400, detail="equipment_name and task are required")
        try:
            freq = int(payload.frequency_days)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="frequency_days must be an integer")
        if freq <= 0:
            raise HTTPException(status_code=400, detail="frequency_days must be positive")
        now = datetime.now(timezone.utc).isoformat()
        last = (payload.last_done_at or "").strip() or None
        doc = {
            "id": f"msch_{uuid.uuid4().hex[:10]}",
            "department_id": dept["department_id"],
            "workspace_id": principal["workspace_id"],
            "equipment_name": eq[:200],
            "task": task[:200],
            "frequency_days": freq,
            "last_done_at": last,
            "created_at": now,
            "updated_at": now,
        }
        await db.maintenance_schedules.insert_one(dict(doc))
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "schedule": maint_ops.enrich_schedule(doc, today=await _ws_today(principal))}

    @api_router.patch("/maintenance/schedules/{schedule_id}")
    async def patch_maintenance_schedule(
        schedule_id: str, payload: SchedulePatch, principal=Depends(get_principal),
    ):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        row = await db.maintenance_schedules.find_one(
            {"id": schedule_id, "department_id": dept["department_id"]}, {"_id": 0},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")
        upd: dict = {}
        if payload.equipment_name is not None:
            v = payload.equipment_name.strip()
            if not v:
                raise HTTPException(status_code=400, detail="equipment_name is required")
            upd["equipment_name"] = v[:200]
        if payload.task is not None:
            v = payload.task.strip()
            if not v:
                raise HTTPException(status_code=400, detail="task is required")
            upd["task"] = v[:200]
        if payload.frequency_days is not None:
            freq = int(payload.frequency_days)
            if freq <= 0:
                raise HTTPException(status_code=400, detail="frequency_days must be positive")
            upd["frequency_days"] = freq
        if payload.mark_done:
            upd["last_done_at"] = datetime.now(timezone.utc).isoformat()
        elif payload.last_done_at is not None:
            upd["last_done_at"] = (payload.last_done_at or "").strip() or None
        if not upd:
            return {"ok": True, "schedule": maint_ops.enrich_schedule(row, today=await _ws_today(principal))}
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.maintenance_schedules.update_one(
            {"id": schedule_id, "department_id": dept["department_id"]}, {"$set": upd},
        )
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "schedule": maint_ops.enrich_schedule({**row, **upd}, today=await _ws_today(principal))}

    @api_router.delete("/maintenance/schedules/{schedule_id}")
    async def delete_maintenance_schedule(schedule_id: str, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        result = await db.maintenance_schedules.delete_one(
            {"id": schedule_id, "department_id": dept["department_id"]},
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Schedule not found")
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True}

    @api_router.get("/maintenance/contracts")
    async def list_maintenance_contracts(principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        rows = await db.maintenance_contracts.find(
            {"department_id": dept["department_id"]}, {"_id": 0},
        ).sort("coverage_end", 1).to_list(2000)
        today = await _ws_today(principal)
        items = [maint_ops.enrich_contract(r, today=today) for r in rows]
        needing = [c for c in items if c["expired"] or c["renewal_due_soon"]]
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        return {
            "contracts": items,
            "needing_renewal": needing,
            "needing_renewal_count": len(needing),
            "is_lead": _can_lead_maint(principal, membership),
            "is_ceo": dept_access.is_workspace_ceo(principal),
        }

    def _norm_ymd(raw: str, field: str) -> str:
        s = (raw or "").strip()
        if not s:
            raise HTTPException(status_code=400, detail=f"{field} is required (YYYY-MM-DD)")
        try:
            if "T" in s:
                s = s.split("T", 1)[0]
            datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD")
        return s[:10]

    @api_router.post("/maintenance/contracts")
    async def create_maintenance_contract(payload: ContractInput, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        eq = (payload.equipment_name or "").strip()
        vendor = (payload.vendor_name or "").strip()
        if not eq or not vendor:
            raise HTTPException(status_code=400, detail="equipment_name and vendor_name are required")
        start = _norm_ymd(payload.coverage_start, "coverage_start")
        end = _norm_ymd(payload.coverage_end, "coverage_end")
        renewal = (payload.renewal_date or "").strip()
        renewal = _norm_ymd(renewal, "renewal_date") if renewal else end
        cost = None
        if payload.cost is not None:
            cost = float(payload.cost)
            if cost < 0:
                raise HTTPException(status_code=400, detail="cost cannot be negative")
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": f"mct_{uuid.uuid4().hex[:10]}",
            "department_id": dept["department_id"],
            "workspace_id": principal["workspace_id"],
            "equipment_name": eq[:200],
            "vendor_name": vendor[:200],
            "coverage_start": start,
            "coverage_end": end,
            "renewal_date": renewal,
            "cost": cost,
            "scope_notes": (payload.scope_notes or "").strip()[:2000],
            "created_at": now,
            "updated_at": now,
        }
        await db.maintenance_contracts.insert_one(dict(doc))
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "contract": maint_ops.enrich_contract(doc, today=await _ws_today(principal))}

    @api_router.patch("/maintenance/contracts/{contract_id}")
    async def patch_maintenance_contract(
        contract_id: str, payload: ContractPatch, principal=Depends(get_principal),
    ):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        row = await db.maintenance_contracts.find_one(
            {"id": contract_id, "department_id": dept["department_id"]}, {"_id": 0},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Contract not found")
        upd: dict = {}
        if payload.equipment_name is not None:
            v = payload.equipment_name.strip()
            if not v:
                raise HTTPException(status_code=400, detail="equipment_name is required")
            upd["equipment_name"] = v[:200]
        if payload.vendor_name is not None:
            v = payload.vendor_name.strip()
            if not v:
                raise HTTPException(status_code=400, detail="vendor_name is required")
            upd["vendor_name"] = v[:200]
        if payload.coverage_start is not None:
            upd["coverage_start"] = _norm_ymd(payload.coverage_start, "coverage_start")
        if payload.coverage_end is not None:
            upd["coverage_end"] = _norm_ymd(payload.coverage_end, "coverage_end")
        if payload.renewal_date is not None:
            r = (payload.renewal_date or "").strip()
            upd["renewal_date"] = _norm_ymd(r, "renewal_date") if r else upd.get("coverage_end") or row.get("coverage_end")
        if payload.cost is not None:
            c = float(payload.cost)
            if c < 0:
                raise HTTPException(status_code=400, detail="cost cannot be negative")
            upd["cost"] = c
        if payload.scope_notes is not None:
            upd["scope_notes"] = payload.scope_notes.strip()[:2000]
        if not upd:
            return {"ok": True, "contract": maint_ops.enrich_contract(row, today=await _ws_today(principal))}
        upd["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.maintenance_contracts.update_one(
            {"id": contract_id, "department_id": dept["department_id"]}, {"$set": upd},
        )
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "contract": maint_ops.enrich_contract({**row, **upd}, today=await _ws_today(principal))}

    @api_router.delete("/maintenance/contracts/{contract_id}")
    async def delete_maintenance_contract(contract_id: str, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        result = await db.maintenance_contracts.delete_one(
            {"id": contract_id, "department_id": dept["department_id"]},
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Contract not found")
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True}

    async def _maint_overhead(dept: dict, workspace_id: str) -> dict:
        month_start, month_end = decision_engine.month_period_bounds()
        tickets = await db.maintenance_tickets.find(
            {
                "department_id": dept["department_id"],
                "status": "resolved",
                "$or": [
                    {"resolved_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}},
                    {
                        "resolved_at": {"$exists": False},
                        "updated_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()},
                    },
                ],
            },
            {"_id": 0, "cost": 1, "resolved_at": 1, "updated_at": 1},
        ).to_list(5000)
        ticket_costs = []
        for t in tickets:
            if t.get("cost") is None:
                continue
            try:
                ticket_costs.append(float(t["cost"]))
            except (TypeError, ValueError):
                pass
        ledger = await db.maintenance_costs.find(
            {
                "department_id": dept["department_id"],
                "month": month_start.strftime("%Y-%m"),
            },
            {"_id": 0, "amount": 1},
        ).to_list(2000)
        ledger_costs = []
        for row in ledger:
            try:
                ledger_costs.append(float(row.get("amount") or 0))
            except (TypeError, ValueError):
                pass
        budget = dept.get("monthly_budget")
        budget_entered = bool(dept.get("monthly_budget_entered"))
        rollup = maint_ops.overhead_rollup(
            ticket_costs=ticket_costs,
            ledger_costs=ledger_costs,
            budget=budget,
            budget_entered=budget_entered,
        )
        rollup["period"] = month_start.strftime("%Y-%m")
        rollup["period_label"] = month_start.strftime("%B %Y")
        return rollup

    @api_router.get("/maintenance/settings")
    async def get_maintenance_settings(principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        overhead = await _maint_overhead(dept, principal["workspace_id"])
        return {
            "monthly_budget": dept.get("monthly_budget"),
            "monthly_budget_entered": bool(dept.get("monthly_budget_entered")),
            "overhead": overhead,
            "can_manage": _can_lead_maint(principal, membership),
        }

    @api_router.put("/maintenance/settings")
    async def put_maintenance_settings(payload: MaintSettingsPut, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        upd: dict = {}
        if payload.clear_budget:
            upd["monthly_budget"] = None
            upd["monthly_budget_entered"] = False
        elif payload.monthly_budget is not None:
            b = float(payload.monthly_budget)
            if b < 0:
                raise HTTPException(status_code=400, detail="monthly_budget cannot be negative")
            upd["monthly_budget"] = round(b, 2)
            upd["monthly_budget_entered"] = True
        if not upd:
            raise HTTPException(status_code=400, detail="No changes provided")
        await db.departments.update_one({"department_id": dept["department_id"]}, {"$set": upd})
        invalidate_departments_cache(principal["workspace_id"])
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, **upd}

    @api_router.get("/maintenance/costs")
    async def list_maintenance_costs(principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        month = decision_engine.month_period_bounds()[0].strftime("%Y-%m")
        rows = await db.maintenance_costs.find(
            {"department_id": dept["department_id"], "month": month},
            {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        overhead = await _maint_overhead(dept, principal["workspace_id"])
        return {"costs": rows, "overhead": overhead, "month": month, **(await _currency_fields(principal))}

    @api_router.post("/maintenance/costs")
    async def create_maintenance_cost(payload: MaintCostCreate, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        try:
            amount = float(payload.amount)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="amount must be a number")
        if amount < 0:
            raise HTTPException(status_code=400, detail="amount cannot be negative")
        month = sales_ob.normalize_month(payload.month) or sales_ob.current_month(await _ws_today(principal))
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": f"mcost_{uuid.uuid4().hex[:10]}",
            "department_id": dept["department_id"],
            "workspace_id": principal["workspace_id"],
            "amount": round(amount, 2),
            "description": (payload.description or "").strip()[:500],
            "category": (payload.category or "general").strip()[:64],
            "month": month,
            "created_by": principal["user_id"],
            "created_at": now,
        }
        await db.maintenance_costs.insert_one(dict(doc))
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True, "cost": {k: v for k, v in doc.items() if k != "_id"}}

    @api_router.delete("/maintenance/costs/{cost_id}")
    async def delete_maintenance_cost(cost_id: str, principal=Depends(get_principal)):
        dept = await _maint_dept(principal)
        await _require_maint_lead(principal, dept)
        result = await db.maintenance_costs.delete_one(
            {"id": cost_id, "department_id": dept["department_id"]},
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Cost entry not found")
        invalidate_workspace_list_cache(principal["workspace_id"], "maintenance")
        return {"ok": True}

    # ===================== Procurement spend / budget =====================
    async def _proc_dept(principal: dict) -> dict:
        doc = await db.departments.find_one(
            {
                "workspace_id": principal["workspace_id"],
                "type": dept_catalog.TYPE_PROCUREMENT,
                "enabled": True,
            },
            {"_id": 0},
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Procurement department is not enabled")
        if not await dept_access.can_access_department(db, principal, doc):
            raise HTTPException(status_code=403, detail="You do not have access to Procurement")
        return doc

    def _can_lead_proc(principal: dict, membership: dict | None) -> bool:
        if dept_access.is_workspace_ceo(principal):
            return True
        return bool(membership) and membership.get("role") == "lead"

    @api_router.get("/procurement/spend")
    async def get_procurement_spend(principal=Depends(get_principal)):
        dept = await _proc_dept(principal)
        month_start, month_end = decision_engine.month_period_bounds()
        rows = await db.procurement_requests.find(
            {"department_id": dept["department_id"]},
            {"_id": 0, "item": 1, "vendor_name": 1, "cost": 1, "created_at": 1, "updated_at": 1},
        ).to_list(5000)
        rollup = proc_spend.spend_rollup(
            rows,
            period_start=month_start,
            period_end=month_end,
            budget=dept.get("monthly_budget"),
            budget_entered=bool(dept.get("monthly_budget_entered")),
        )
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        return {
            "spend": rollup,
            "can_manage_budget": _can_lead_proc(principal, membership),
            "monthly_budget": dept.get("monthly_budget"),
            "monthly_budget_entered": bool(dept.get("monthly_budget_entered")),
        }

    @api_router.get("/procurement/settings")
    async def get_procurement_settings(principal=Depends(get_principal)):
        return await get_procurement_spend(principal=principal)

    @api_router.put("/procurement/settings")
    async def put_procurement_settings(payload: ProcSettingsPut, principal=Depends(get_principal)):
        dept = await _proc_dept(principal)
        membership = await dept_access.get_department_membership(
            db, dept["department_id"], principal["user_id"],
        )
        if not _can_lead_proc(principal, membership):
            raise HTTPException(status_code=403, detail="Only a Procurement lead or CEO can set budget")
        upd: dict = {}
        if payload.clear_budget:
            upd["monthly_budget"] = None
            upd["monthly_budget_entered"] = False
        elif payload.monthly_budget is not None:
            b = float(payload.monthly_budget)
            if b < 0:
                raise HTTPException(status_code=400, detail="monthly_budget cannot be negative")
            upd["monthly_budget"] = round(b, 2)
            upd["monthly_budget_entered"] = True
        if not upd:
            raise HTTPException(status_code=400, detail="No changes provided")
        await db.departments.update_one({"department_id": dept["department_id"]}, {"$set": upd})
        invalidate_departments_cache(principal["workspace_id"])
        invalidate_workspace_list_cache(principal["workspace_id"], "procurement")
        return {"ok": True, **upd}

    logger.info("dept_ops routes registered")
