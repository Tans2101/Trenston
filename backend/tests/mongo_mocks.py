"""Mongo mock helpers for unit tests."""
from unittest.mock import MagicMock


def attach_users_in_find(users):
    """Route users.find($in) through users.find_one so batch lookups work on mocks."""
    def find(query, projection=None):
        raw = (query or {}).get("user_id")
        if isinstance(raw, dict) and "$in" in raw:
            ids = list(raw.get("$in") or [])
        elif raw:
            ids = [raw]
        else:
            ids = []
        cursor = MagicMock()

        async def to_list(_n=None):
            out = []
            for uid in ids:
                u = await users.find_one({"user_id": uid}, projection)
                if u:
                    doc = dict(u)
                    doc.setdefault("user_id", uid)
                    out.append(doc)
            return out

        cursor.to_list = to_list
        return cursor

    users.find = find
    return users


_MISSING = object()


def _field_matches(value, cond) -> bool:
    import re as _re

    if isinstance(cond, _re.Pattern):
        return isinstance(value, str) and bool(cond.search(value))
    if not isinstance(cond, dict) or not any(str(k).startswith("$") for k in cond):
        return value is not _MISSING and value == cond
    for op, arg in cond.items():
        if op == "$regex":
            flags = _re.IGNORECASE if "i" in (cond.get("$options") or "") else 0
            if not (isinstance(value, str) and _re.search(arg, value, flags)):
                return False
        elif op == "$options":
            continue
        elif op == "$exists":
            if (value is not _MISSING) != bool(arg):
                return False
        elif op == "$in":
            v = None if value is _MISSING else value
            if v not in arg:
                return False
        elif op == "$nin":
            v = None if value is _MISSING else value
            if v in arg:
                return False
        elif op == "$ne":
            if value is not _MISSING and value == arg:
                return False
        elif op == "$lt":
            if value is _MISSING or not value < arg:
                return False
        elif op == "$gte":
            if value is _MISSING or not value >= arg:
                return False
        elif op == "$not":
            if _field_matches(value, arg):
                return False
        else:
            raise NotImplementedError(op)
    return True


def match_filter(doc: dict, flt: dict) -> bool:
    """Tiny Mongo filter evaluator for unit tests (subset of operators)."""
    for key, cond in (flt or {}).items():
        if key == "$or":
            if not any(match_filter(doc, sub) for sub in cond):
                return False
        elif key == "$and":
            if not all(match_filter(doc, sub) for sub in cond):
                return False
        elif key == "$nor":
            if any(match_filter(doc, sub) for sub in cond):
                return False
        elif not _field_matches(doc.get(key, _MISSING), cond):
            return False
    return True


class FakeCollection:
    """In-memory async collection supporting the calls the unit tests exercise."""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, flt=None, projection=None):
        for d in self.docs:
            if match_filter(d, flt or {}):
                return dict(d)
        return None

    async def count_documents(self, flt=None, limit=0):
        n = sum(1 for d in self.docs if match_filter(d, flt or {}))
        return min(n, limit) if limit else n

    async def delete_many(self, flt):
        before = len(self.docs)
        self.docs = [d for d in self.docs if not match_filter(d, flt)]
        res = MagicMock()
        res.deleted_count = before - len(self.docs)
        return res

    async def delete_one(self, flt):
        for i, d in enumerate(self.docs):
            if match_filter(d, flt):
                del self.docs[i]
                break

    async def insert_many(self, docs):
        self.docs.extend(dict(d) for d in docs)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    def find(self, flt=None, projection=None):
        rows = [dict(d) for d in self.docs if match_filter(d, flt or {})]
        return _FakeCursor(rows)


class _FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        if isinstance(key, list):
            key, direction = key[0]
        self.rows.sort(key=lambda r: (r.get(key) is None, r.get(key)), reverse=direction == -1)
        return self

    def limit(self, n):
        if n:
            self.rows = self.rows[:n]
        return self

    async def to_list(self, n=None):
        return self.rows if n is None else self.rows[:n]
