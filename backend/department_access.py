"""Department membership helpers — reusable by department-scoped endpoints."""
from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Optional

import departments_catalog as dept_catalog

logger = logging.getLogger("helm")

UNASSIGNED_DEPARTMENT_LABEL = "Unassigned"

# Per-async-task memo for accessible_department_ids within one request.
_access_ids_cache: ContextVar[Optional[dict]] = ContextVar("helm_dept_access_ids", default=None)


def _access_cache() -> dict:
    cache = _access_ids_cache.get()
    if cache is None:
        cache = {}
        _access_ids_cache.set(cache)
    return cache


def clear_access_ids_cache() -> None:
    """Drop request memo (tests)."""
    _access_ids_cache.set({})


def is_workspace_ceo(principal: dict) -> bool:
    """Owner pack / role = company CEO for department admin actions."""
    return principal.get("pack") == "owner" or principal.get("role") == "owner"


def is_workspace_exec(principal: dict) -> bool:
    """Executive pack: reads every department, but lead-only actions still need a lead role."""
    return principal.get("pack") == "exec"


def can_read_all_departments(principal: dict) -> bool:
    """CEO and Executives see every enabled department without a membership row."""
    return is_workspace_ceo(principal) or is_workspace_exec(principal)


# Access packs that carry a role in one department type, without a membership row.
# The People / HR pack runs the HR department as its lead.
PACK_DEPARTMENT_ROLES: dict[str, dict[str, str]] = {
    "hr": {dept_catalog.TYPE_HR: "lead"},
}
_ROLE_RANK = {"member": 1, "lead": 2}

# The signed-in person for this request (set by get_principal). Pack-implied
# department roles are read from it, so checks cost no extra queries.
_current_principal: ContextVar[Optional[dict]] = ContextVar("helm_current_principal", default=None)


def set_current_principal(principal: Optional[dict]) -> None:
    _current_principal.set(principal)


def pack_department_role(pack: str | None, dept_type: str | None) -> Optional[str]:
    """Department role an access pack implies for a department type (or None)."""
    return (PACK_DEPARTMENT_ROLES.get(pack or "") or {}).get(dept_type or "")


def _implied_pack_for(user_id: str) -> Optional[str]:
    """Pack of the signed-in person when it carries a department role, else None."""
    principal = _current_principal.get()
    if not principal or principal.get("user_id") != user_id:
        return None
    pack = principal.get("pack")
    return pack if pack in PACK_DEPARTMENT_ROLES else None


async def _department_doc(db, department_id: str) -> Optional[dict]:
    # A department's workspace and type never change, so this memo is safe.
    cache = _access_cache()
    key = ("dept_doc", department_id)
    if key not in cache:
        cache[key] = await db.departments.find_one(
            {"department_id": department_id},
            {"_id": 0, "department_id": 1, "workspace_id": 1, "type": 1},
        )
    return cache[key]


def display_department_names(names: list[str] | None) -> str:
    """Human-readable department list for roster rows. Empty → Unassigned."""
    cleaned = [n.strip() for n in (names or []) if n and str(n).strip()]
    return ", ".join(cleaned) if cleaned else UNASSIGNED_DEPARTMENT_LABEL


def attach_real_departments(row: dict, names: list[str] | None) -> dict:
    """Overlay response fields from department_members (does not persist)."""
    cleaned = [n.strip() for n in (names or []) if n and str(n).strip()]
    row["departments"] = cleaned
    row["department"] = display_department_names(cleaned)
    return row


async def department_names_by_user_id(db, workspace_id: str) -> dict[str, list[str]]:
    """Map user_id → enabled department display names for a workspace."""
    enabled = await db.departments.find(
        {"workspace_id": workspace_id, "enabled": True},
        {"_id": 0, "department_id": 1, "name": 1, "type": 1},
    ).to_list(50)
    if not enabled:
        return {}
    id_to_name: dict[str, str] = {}
    for d in enabled:
        did = d.get("department_id")
        if not did:
            continue
        name = (d.get("name") or "").strip() or dept_catalog.default_name(d.get("type") or "")
        id_to_name[did] = name
    rows = await db.department_members.find(
        {"department_id": {"$in": list(id_to_name)}},
        {"_id": 0, "department_id": 1, "user_id": 1},
    ).to_list(2000)
    out: dict[str, list[str]] = {}
    for row in rows:
        uid = row.get("user_id")
        name = id_to_name.get(row.get("department_id"))
        if not uid or not name:
            continue
        bucket = out.setdefault(uid, [])
        if name not in bucket:
            bucket.append(name)
    for uid, names in out.items():
        out[uid] = sorted(names, key=str.lower)
    return out


async def department_ids_by_user_id(db, workspace_id: str) -> dict[str, list[str]]:
    """Map user_id → enabled department_ids for a workspace."""
    enabled = await db.departments.find(
        {"workspace_id": workspace_id, "enabled": True},
        {"_id": 0, "department_id": 1},
    ).to_list(50)
    enabled_ids = [d["department_id"] for d in enabled if d.get("department_id")]
    if not enabled_ids:
        return {}
    rows = await db.department_members.find(
        {"department_id": {"$in": enabled_ids}},
        {"_id": 0, "department_id": 1, "user_id": 1},
    ).to_list(2000)
    out: dict[str, list[str]] = {}
    for row in rows:
        uid = row.get("user_id")
        did = row.get("department_id")
        if not uid or not did:
            continue
        bucket = out.setdefault(uid, [])
        if did not in bucket:
            bucket.append(did)
    return out


async def list_enabled_departments(db, workspace_id: str) -> list[dict]:
    """Enabled department rows for access UI: id, type, name."""
    rows = await db.departments.find(
        {"workspace_id": workspace_id, "enabled": True},
        {"_id": 0, "department_id": 1, "type": 1, "name": 1},
    ).to_list(50)
    out = []
    for d in rows:
        did = d.get("department_id")
        if not did:
            continue
        dtype = d.get("type") or ""
        out.append({
            "department_id": did,
            "type": dtype,
            "name": (d.get("name") or "").strip() or dept_catalog.default_name(dtype),
        })
    out.sort(key=lambda x: (x.get("name") or "").lower())
    return out


async def get_department_membership(db, department_id: str, user_id: str) -> Optional[dict]:
    """The user's department role — a real membership row, raised by any pack-implied role."""
    row = await db.department_members.find_one(
        {"department_id": department_id, "user_id": user_id},
        {"_id": 0},
    )
    if row and row.get("role") == "lead":
        return row
    pack = _implied_pack_for(user_id)
    if not pack:
        return row
    dept = await _department_doc(db, department_id)
    if not dept or dept.get("workspace_id") != (_current_principal.get() or {}).get("workspace_id"):
        return row
    implied = pack_department_role(pack, dept.get("type"))
    if not implied or _ROLE_RANK.get(implied, 0) <= _ROLE_RANK.get((row or {}).get("role"), 0):
        return row
    return {
        **(row or {"department_id": department_id, "user_id": user_id}),
        "role": implied,
        "implied_by_pack": pack,
    }


async def is_department_member(db, user_id: str, department_id: str) -> bool:
    row = await get_department_membership(db, department_id, user_id)
    return bool(row)


async def is_department_lead(db, user_id: str, department_id: str) -> bool:
    row = await get_department_membership(db, department_id, user_id)
    return bool(row) and row.get("role") == "lead"


async def can_manage_department_members(db, principal: dict, department_id: str) -> bool:
    if is_workspace_ceo(principal):
        return True
    return await is_department_lead(db, principal["user_id"], department_id)


async def can_access_department(db, principal: dict, department: dict) -> bool:
    """CEO and Executives see every enabled department; others need a membership
    row or a pack that implies one (People / HR → HR)."""
    # Defense in depth: never grant access to a department from another workspace,
    # even if the caller already loaded the doc (CEO/exec/pack short-circuits used
    # to skip this and could IDOR across tenants if a foreign doc was passed).
    if department.get("workspace_id") != principal.get("workspace_id"):
        return False
    if can_read_all_departments(principal):
        return True
    if pack_department_role(principal.get("pack"), department.get("type")):
        return True
    return await is_department_member(db, principal["user_id"], department["department_id"])


async def accessible_department_ids(
    db, principal: dict, dept_type: str,
) -> Optional[list[str]]:
    """Department ids of ``dept_type`` the principal may read records from.

    Returns ``None`` for CEO and Executives (bypass — see all workspace records of that kind).
    Returns a list (possibly empty) for everyone else — empty means no access.
    """
    cache = _access_cache()
    cache_key = (principal.get("user_id"), principal.get("workspace_id"), dept_type)
    if cache_key in cache:
        return cache[cache_key]

    if can_read_all_departments(principal):
        cache[cache_key] = None
        return None
    rows = await db.departments.find(
        {
            "workspace_id": principal["workspace_id"],
            "type": dept_type,
            "enabled": True,
        },
        {"_id": 0, "department_id": 1},
    ).to_list(50)
    if not rows:
        cache[cache_key] = []
        return []
    if pack_department_role(principal.get("pack"), dept_type):
        result = [r["department_id"] for r in rows]
        cache[cache_key] = result
        return result
    my_rows = await db.department_members.find(
        {
            "user_id": principal["user_id"],
            "department_id": {"$in": [r["department_id"] for r in rows]},
        },
        {"_id": 0, "department_id": 1},
    ).to_list(50)
    result = [m["department_id"] for m in my_rows]
    cache[cache_key] = result
    return result


async def accessible_department_ids_by_type(
    db, principal: dict, dept_types: list[str] | tuple[str, ...],
) -> dict[str, Optional[list[str]]]:
    """Batched membership lookup for many department types in one request.

    Same semantics as calling :func:`accessible_department_ids` per type:
    ``None`` = CEO bypass, ``[]`` = no access, non-empty list = allowed ids.
    Uses two Mongo queries total (enabled departments + memberships) instead of
    two per type. Populates the per-request memo so later single-type calls hit cache.
    """
    types = [t for t in dept_types if t]
    out: dict[str, Optional[list[str]]] = {t: [] for t in types}
    if not types:
        return out

    cache = _access_cache()
    uid = principal.get("user_id")
    ws_id = principal.get("workspace_id")

    if can_read_all_departments(principal):
        for t in types:
            out[t] = None
            cache[(uid, ws_id, t)] = None
        return out

    # Fill from memo when every type is already cached.
    if all((uid, ws_id, t) in cache for t in types):
        return {t: cache[(uid, ws_id, t)] for t in types}

    enabled = await db.departments.find(
        {
            "workspace_id": ws_id,
            "type": {"$in": list(types)},
            "enabled": True,
        },
        {"_id": 0, "department_id": 1, "type": 1},
    ).to_list(200)

    ids_by_type: dict[str, list[str]] = {t: [] for t in types}
    all_ids: list[str] = []
    for row in enabled:
        did = row.get("department_id")
        dtype = row.get("type")
        if not did or dtype not in ids_by_type:
            continue
        ids_by_type[dtype].append(did)
        all_ids.append(did)

    member_ids: set[str] = set()
    if all_ids:
        my_rows = await db.department_members.find(
            {
                "user_id": uid,
                "department_id": {"$in": all_ids},
            },
            {"_id": 0, "department_id": 1},
        ).to_list(200)
        member_ids = {m["department_id"] for m in my_rows if m.get("department_id")}

    for t in types:
        if pack_department_role(principal.get("pack"), t):
            allowed = list(ids_by_type[t])
        else:
            allowed = [did for did in ids_by_type[t] if did in member_ids]
        out[t] = allowed
        cache[(uid, ws_id, t)] = allowed
    return out


def apply_department_filter(base_filter: dict, department_ids: Optional[list[str]]) -> dict:
    """Attach department_id constraint. ``None`` = CEO bypass (unchanged filter)."""
    if department_ids is None:
        return base_filter
    out = dict(base_filter)
    out["department_id"] = {"$in": list(department_ids)}
    return out


# Feature collections owned by a department — cleared when the department is disabled.
# Do NOT include deals / financial_entries: those are core workspace data that keep
# their department_id but must not permanently block disable.
DEPARTMENT_FEATURE_COLLECTIONS = (
    "production_work_orders",
    "procurement_requests",
    "legal_matters",
    "maintenance_tickets",
    "hr_onboarding_instances",
    "hr_onboarding_template",
    "hr_employees",
    "hr_offboarding_instances",
    "hr_offboarding_template",
    "hr_leave_requests",
)

async def clear_department_feature_data(db, department_id: str) -> dict[str, int]:
    """Delete all feature rows for a department. Returns {collection: deleted_count}."""
    cleared: dict[str, int] = {}
    # Best-effort cleanup of legal matter files in R2 before wiping rows.
    legal = getattr(db, "legal_matters", None)
    if legal is not None:
        try:
            rows = await legal.find(
                {"department_id": department_id},
                {"_id": 0, "document_ref": 1},
            ).to_list(5000)
        except Exception:
            rows = []
        if rows:
            try:
                import storage as doc_storage
                if doc_storage.r2_configured():
                    import asyncio
                    for row in rows:
                        ref = row.get("document_ref") or {}
                        key = ref.get("storage_key") if isinstance(ref, dict) else None
                        if key:
                            try:
                                await asyncio.to_thread(doc_storage.delete_document, key)
                            except Exception:
                                logger.exception("failed to delete legal doc %s on dept clear", key)
            except Exception:
                logger.exception("legal matter R2 cleanup skipped")

    for name in DEPARTMENT_FEATURE_COLLECTIONS:
        coll = getattr(db, name, None)
        if coll is None:
            continue
        try:
            res = await coll.delete_many({"department_id": department_id})
            cleared[name] = int(getattr(res, "deleted_count", 0) or 0)
        except Exception:
            logger.exception("failed clearing %s for department %s", name, department_id)
            cleared[name] = 0
    return cleared
