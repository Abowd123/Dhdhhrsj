"""
خادم المحرر.

‼ **بلا مصادقة.** لا مستخدمين ولا مفاتيح ولا تحقّق من هوية. من يصل إلى
المنفذ يقرأ كل مشروع محمَّل في الذاكرة ويعدّله ويحفظه على القرص بأي
مسار. الافتراضي الربط على `127.0.0.1` فلا شيء خارج الجهاز يصل، وهذا كل
الحماية الموجودة.

`create_app(allow_public=True)` وحده يسمح بالربط على واجهة عامة، ويطبع
تحذيرًا. لا تفعل ذلك على شبكة لا تثق بكل من عليها: طبقة مصادقة قرار نشر
يُتّخذ قبل ذلك، لا عَلَم يُمرَّر بعده.

الحالة في الذاكرة، بسقف عدد وإخلاء بالأقدمية: كل جلسة تحمل مخططًا ورسمًا
وثلاثة تقارير، فقاموسٌ بلا حدّ يستهلك الذاكرة حتى يسقط الخادم.
"""
from __future__ import annotations
import os
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from planforge.assurance import assess
from planforge.codes.signing import SignatureBook
from planforge.edit.ops import parse_op
from planforge.edit.session import EditSession
from planforge.export.svg import storey_svg
from planforge.model.brief import Brief
from planforge.pipeline import closest, run as run_pipeline
from planforge.project import Project
from planforge.rules.core import ComplianceReport
from planforge.solver.config import SolverConfig
from planforge.units import area_m2

MAX_SESSIONS = 12
STATIC_DIR = Path(__file__).parent / "static"

WORKSPACE = Path(
    os.environ.get("PLANFORGE_WORKSPACE", "projects")
).resolve()


def _safe(raw: str) -> Path:
    """يمنع الخروج من مجلّد العمل بـ`..` أو بمسار مطلق."""
    path = (WORKSPACE / raw.lstrip("/")).resolve()
    if not path.is_relative_to(WORKSPACE):
        raise HTTPException(400, "المسار خارج مجلّد العمل")
    return path


@dataclass
class Slot:
    session: EditSession
    origin_layout: Any
    path: Path | None = None


class Store:
    """جلسات في الذاكرة بسقف عدد — الأقدم يُخلى عند الامتلاء."""

    def __init__(self, cap: int = MAX_SESSIONS) -> None:
        self._slots: OrderedDict[str, Slot] = OrderedDict()
        self._cap = cap

    def put(self, slot: Slot) -> str:
        sid = uuid.uuid4().hex[:12]
        self._slots[sid] = slot
        while len(self._slots) > self._cap:
            self._slots.popitem(last=False)
        return sid

    def get(self, sid: str) -> Slot:
        slot = self._slots.get(sid)
        if slot is None:
            raise HTTPException(
                404,
                "الجلسة غير موجودة أو أُخليت لضيق الذاكرة — "
                "أعد فتح المشروع",
            )
        self._slots.move_to_end(sid)
        return slot

    def drop(self, sid: str) -> bool:
        return self._slots.pop(sid, None) is not None

    def ids(self) -> list[str]:
        return list(self._slots)


def _report_json(rep: ComplianceReport) -> dict:
    return {
        "ok": rep.ok,
        "errors": [
            {
                "rule": v.rule_id, "message": v.message,
                "reference": v.reference, "storey": v.storey,
                "rooms": list(v.rooms),
                "actual": v.actual, "required": v.required,
            }
            for v in rep.errors
        ],
        "warnings": [
            {
                "rule": v.rule_id, "message": v.message,
                "storey": v.storey, "rooms": list(v.rooms),
            }
            for v in rep.warnings
        ],
        "counts": {
            "errors": len(rep.errors),
            "warnings": len(rep.warnings),
            "rules_run": len(set(rep.rules_run)),
        },
    }


def _state_json(slot: Slot, book: SignatureBook) -> dict:
    s = slot.session
    st = s.state
    unfurnishable = frozenset(st.fixtures.unfurnishable)
    assurance = assess(st.reports, book=book)
    return {
        "ok": st.ok,
        "rank": st.rank,
        "features": st.features.__dict__,
        "reports": {
            "layout": _report_json(st.layout_report),
            "drawing": _report_json(st.drawing_report),
            "fixtures": _report_json(st.fixture_report),
        },
        "assurance": {
            "stamp": assurance.stamp(),
            "summary_ar": assurance.summary_ar(),
            "delivery_ready": assurance.delivery_ready,
            "unsigned": len(assurance.unsigned),
        },
        "history": {
            "depth": s.depth,
            "can_undo": s.can_undo,
            "can_redo": s.can_redo,
        },
        "storeys": [
            {
                "index": sd.index,
                "gia_m2": round(area_m2(sd.gia_mm2), 2),
                "svg": storey_svg(sd, unfurnishable=unfurnishable),
                "rooms": [
                    {
                        "id": r.id, "type": str(r.type),
                        "area_m2": round(area_m2(r.area), 2),
                        "w": r.w, "h": r.h,
                        "furnishable": r.id not in unfurnishable,
                    }
                    for r in sd.rooms
                ],
                "lines": [
                    {
                        "id": ln.id, "axis": str(ln.axis),
                        "coord": ln.coord, "movable": ln.movable,
                        "rooms": sorted(ln.rooms),
                    }
                    for ln in s.topo[sd.index].movable_lines()
                ],
                "openings": [
                    {
                        "id": o.id, "kind": str(o.kind),
                        "width": o.clear_width_mm,
                        "rooms": list(o.rooms()),
                    }
                    for o in sd.openings
                ],
            }
            for sd in sorted(s.state.drawing.storeys, key=lambda d: d.index)
        ],
    }


def create_app(
    *,
    signatures: Path | None = None,
    allow_public: bool = False,
    skip_fixtures: bool = False,
) -> FastAPI:
    app = FastAPI(title="PlanForge", version="0.7.0")
    store = Store()
    book = SignatureBook.load(signatures) if signatures else SignatureBook()
    app.state.allow_public = allow_public

    if allow_public:
        from planforge.server.auth import require_token, token
        if not token():
            raise SystemExit(
                "الربط على واجهة عامة يقتضي ضبط PLANFORGE_TOKEN. "
                "ولّد رمزًا: python -c \"import secrets;"
                "print(secrets.token_urlsafe(32))\""
            )
        app.router.dependencies.append(Depends(require_token))

    if STATIC_DIR.exists():
        app.mount(
            "/static", StaticFiles(directory=STATIC_DIR), name="static"
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = STATIC_DIR / "index.html"
        if not page.exists():
            return "<h1>PlanForge</h1><p>واجهة المحرر غير مثبَّتة.</p>"
        return page.read_text(encoding="utf-8")

    @app.get("/api/health")
    def health() -> dict:
        return {
            "ok": True,
            "sessions": len(store.ids()),
            "authenticated": False,
            "note": "الخادم بلا مصادقة — للاستخدام المحلي فقط",
        }

    # ─────────── توليد وفتح ───────────

    @app.post("/api/generate")
    def generate(payload: dict = Body(...)) -> JSONResponse:
        try:
            brief = Brief.model_validate(payload.get("brief", {}))
        except Exception as exc:
            raise HTTPException(422, f"متطلب غير صالح: {exc}") from exc
        cfg = SolverConfig(
            seed=brief.seed,
            n_alternatives=int(payload.get("alternatives", 3)),
            time_limit_s=float(payload.get("time_limit_s", 45.0)),
            workers=2,
        )
        best, feas, attempted = run_pipeline(
            brief, cfg, skip_fixtures=skip_fixtures
        )
        if best is None:
            best = closest(attempted)
        if best is None:
            return JSONResponse(
                {
                    "ok": False,
                    "feasibility": _report_json(feas),
                    "message": (
                        "لم يُنتج المُحلّل أي بديل — شغّل التشخيص لمعرفة "
                        "القيد المُلزِم"
                    ),
                },
                status_code=200,
            )
        sid = store.put(Slot(
            session=EditSession(
                brief, best.layout, skip_fixtures=skip_fixtures
            ),
            origin_layout=best.layout,
        ))
        return JSONResponse({
            "ok": True,
            "session": sid,
            "rounds": best.rounds,
            "shrink_ratio": best.shrink_ratio,
            "shrink_notes": best.shrink_notes,
            "alternatives_tried": len(attempted),
            "feasibility": _report_json(feas),
            "state": _state_json(store.get(sid), book),
        })

    @app.post("/api/open")
    def open_project(payload: dict = Body(...)) -> dict:
        raw = payload.get("path")
        if not raw:
            raise HTTPException(422, "المسار مطلوب")
        path = _safe(raw)
        if not path.exists():
            raise HTTPException(404, f"لا يوجد ملف: {path}")
        proj = Project.load(path)
        session = proj.open_session(skip_fixtures=skip_fixtures)
        sid = store.put(Slot(
            session=session, origin_layout=proj.layout, path=path
        ))
        return {
            "ok": True, "session": sid,
            "state": _state_json(store.get(sid), book),
        }

    @app.get("/api/session/{sid}")
    def state(sid: str) -> dict:
        return _state_json(store.get(sid), book)

    @app.delete("/api/session/{sid}")
    def close(sid: str) -> dict:
        return {"ok": store.drop(sid)}

    # ─────────── تعديل ───────────

    @app.post("/api/session/{sid}/op")
    def apply_op(sid: str, payload: dict = Body(...)) -> dict:
        slot = store.get(sid)
        try:
            op = parse_op(payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        res = slot.session.apply(op)
        return {
            "ok": res.ok,
            "message": res.message,
            "moved_lines": res.moved_lines,
            "introduced": [
                {
                    "rule": v.rule_id, "message": v.message,
                    "rooms": list(v.rooms), "storey": v.storey,
                }
                for v in res.introduced
            ],
            "state": _state_json(slot, book) if res.ok else None,
        }

    @app.post("/api/session/{sid}/undo")
    def undo(sid: str) -> dict:
        slot = store.get(sid)
        res = slot.session.undo()
        return {
            "ok": res.ok, "message": res.message,
            "state": _state_json(slot, book) if res.ok else None,
        }

    @app.post("/api/session/{sid}/redo")
    def redo(sid: str) -> dict:
        slot = store.get(sid)
        res = slot.session.redo()
        return {
            "ok": res.ok, "message": res.message,
            "state": _state_json(slot, book) if res.ok else None,
        }

    # ─────────── حفظ ───────────

    @app.post("/api/session/{sid}/save")
    def save(sid: str, payload: dict = Body(default={})) -> dict:
        """
        `keep_history=True` (الافتراضي) يحفظ المخطط الأصلي مع السجل، فيبقى
        الملف قابلًا لإعادة الإنتاج بـ`replay`. و`False` يحفظ الحالة
        الراهنة نقطةَ بدايةٍ جديدة ويُسقط السجل.
        """
        slot = store.get(sid)
        target = payload.get("path") or (
            str(slot.path) if slot.path else None
        )
        if not target:
            raise HTTPException(422, "المسار مطلوب لأول حفظ")
        keep = bool(payload.get("keep_history", True))
        proj = (
            Project.from_session(
                slot.session, origin=slot.origin_layout
            )
            if keep else Project.snapshot(slot.session)
        )
        written = proj.save(_safe(target))
        slot.path = written
        return {
            "ok": True, "path": str(written),
            "history_kept": keep, "operations": len(proj.history),
        }

    return app


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    signatures: Path | None = None,
    allow_public: bool = False,
    skip_fixtures: bool = False,
) -> None:
    """
    يرفض الربط على واجهة عامة بلا إقرار صريح.

    الرفض لا التحذير: عَلَمٌ يُطبَع في سجلّ لا يقرؤه أحد ليس حماية.
    """
    import uvicorn

    public = host not in ("127.0.0.1", "localhost", "::1")
    if public and not allow_public:
        raise SystemExit(
            f"الربط على {host} يفتح الخادم على الشبكة، والخادم بلا "
            f"مصادقة: أي جهاز يصل إلى المنفذ {port} يقرأ مشاريعك "
            f"ويعدّلها ويكتب على قرصك.\n"
            f"إن كنت تفهم ذلك وتقصده، أضِف --allow-public. "
            f"وإلا استخدم 127.0.0.1."
        )
    if public:
        print(
            f"⚠  الخادم مفتوح على {host}:{port} بلا مصادقة — "
            f"تأكّد أن الشبكة موثوقة."
        )
    port = int(os.environ.get("PORT", port))
    app = create_app(
        signatures=signatures, allow_public=allow_public,
        skip_fixtures=skip_fixtures,
    )
    uvicorn.run(app, host=host, port=port, log_level="info")
