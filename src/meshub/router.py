"""데이터 허브 화면 · API — `/hub` 저장 현황 · `/hub/structured` 정형 · `/hub/files` 비정형 · `/hub/realtime` 실시간 (D-53).

코어 업무 테이블에는 쓰지 않는다. 쓰는 곳은 `hub` 스키마(파일 목록 · 시간 집계)와 파일 폴더뿐이고, 쓰기는 접근 로그(change)에 남긴다.
요청 `Accept` 에 text/html 이 없으면 JSON 을 준다(코어 D-18 과 같음).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from mescore.app import rbac, templating
from mescore.app.util import audit

from . import access, catalog, files, realtime, store

router = APIRouter()
MENU = {"code": "hub", "name": "데이터 허브", "icon": "DH",
        "items": [("/hub", "저장 현황"), ("/hub/structured", "정형 데이터"), ("/hub/files", "비정형 데이터"), ("/hub/realtime", "실시간 데이터")]}
HUB_JS = Path(__file__).parent / "static" / "hub.js"
TEMPLATES = Path(__file__).parent / "templates"
if str(TEMPLATES) not in templating.env.loader.searchpath:            # 선택 모듈 템플릿 — 코어 · 팩 템플릿 뒤에서 찾는다
    templating.env.loader.searchpath.append(str(TEMPLATES))


def _html(request: Request) -> bool:
    return "text/html" in (request.headers.get("accept") or "")


def _page(request: Request, tpl: str, ctx: dict, title: str, status: int = 200):
    ctx = {**ctx, "screen_name": title, "menu_name": "데이터 허브", "hub_tabs": MENU["items"]}
    if not _html(request):
        return JSONResponse(templating.jsonable({k: v for k, v in ctx.items() if k != "hub_tabs"}), status_code=status)
    return templating.render(request, tpl, ctx, status_code=status)


def _log_change(request: Request, user: rbac.User, what: str, target: str, detail: dict | None = None) -> None:
    audit.write_log(kind=audit.CHANGE, login_id=user.login_id, user_id=user.id, screen_id="HUB", fn_id=what, target=target,
                    detail=detail or {}, ip=audit.client_ip(request), device=audit.device_of(request))


def _can_rt(user: rbac.User) -> bool:
    return rbac.can_read_menu(user.role_code, "eqp")


# ── 저장 현황 ─────────────────────────────────────────────
@router.get("/hub", include_in_schema=False)
def hub_overview(request: Request, user: rbac.User = Depends(rbac.require_login)):
    store.ensure()
    tables = catalog.catalog(user)
    rt = realtime.status() if _can_rt(user) else None
    return _page(request, "hub/overview.html", {
        "s": catalog.summary(tables), "f": files.stats(), "rt": rt,
        "daily_s": catalog.daily(user), "daily_f": files.daily(), "daily_r": realtime.daily() if rt else [],
    }, "저장 현황")


# ── 정형 데이터 ───────────────────────────────────────────
@router.get("/hub/structured", include_in_schema=False)
def hub_structured(request: Request, q: str = "", m: str = "", user: rbac.User = Depends(rbac.require_login)):
    tables = catalog.catalog(user)
    s = catalog.summary(tables)
    shown = [t for t in tables if (not m or t.module == m) and (not q or q.lower() in (t.name + t.description).lower())]
    return _page(request, "hub/structured.html", {"tables": shown, "s": s, "q": q, "m": m}, "정형 데이터")


@router.get("/hub/structured/{name}.csv", include_in_schema=False)
def hub_structured_csv(request: Request, name: str, days: int = 0, user: rbac.User = Depends(rbac.require_login)):
    try:
        info = catalog.check_name(user, name)
    except KeyError:
        return JSONResponse({"code": "not_found", "message": f"없는 테이블: {name}"}, status_code=404)
    except PermissionError:
        return JSONResponse({"code": "forbidden", "message": "지금 역할로 내보낼 수 없는 테이블입니다"}, status_code=403)
    body, n, truncated = catalog.export_csv(name, info["cols"], days or None)
    audit.write_log(kind=audit.VIEW, login_id=user.login_id, user_id=user.id, screen_id="HUB", target=name,
                    detail={"path": request.url.path, "export": "csv", "rows": n, "days": days or None, "truncated": truncated},
                    ip=audit.client_ip(request), device=audit.device_of(request))
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}.csv", "X-Rows": str(n),
                             "X-Truncated": "1" if truncated else "0"})


@router.get("/hub/structured/{name}", include_in_schema=False)
def hub_structured_table(request: Request, name: str, user: rbac.User = Depends(rbac.require_login)):
    try:
        info = catalog.check_name(user, name)
    except KeyError:
        return _page(request, "hub/structured.html", {"tables": [], "s": catalog.summary([]), "q": name, "m": "", "error": f"없는 테이블: {name}"},
                     "정형 데이터", 404)
    except PermissionError:
        return _page(request, "hub/structured.html", {"tables": [], "s": catalog.summary([]), "q": name, "m": "",
                                                      "error": "지금 역할로 볼 수 없는 테이블입니다"}, "정형 데이터", 403)
    t = catalog._stats(name, info)
    return _page(request, "hub/table.html", {"tb": t, "cols": info["cols"], "preview": catalog.preview(name, info["cols"]),
                                             "export_max": catalog.EXPORT_MAX}, "정형 데이터")


# ── 비정형 데이터 ─────────────────────────────────────────
@router.get("/hub/files", include_in_schema=False)
def hub_files(request: Request, q: str = "", category: str = "", link_kind: str = "", user: rbac.User = Depends(rbac.require_login)):
    return _page(request, "hub/files.html", {
        "rows": files.search(q, category, link_kind), "f": files.stats(), "q": q, "category": category, "link_kind": link_kind,
        "categories": files.CATEGORIES, "links": {k: v[0] for k, v in files.LINKS.items()}, "allowed": sorted(files.ALLOWED),
        "max_mb": files.max_bytes() // (1024 * 1024), "is_admin": access.is_admin(user), "me": user.login_id, "form": {}, "errors": {},
    }, "비정형 데이터")


@router.post("/hub/files", include_in_schema=False)
async def hub_files_upload(request: Request, file: UploadFile = File(None), title: str = Form(""), category: str = Form(""),
                           link_kind: str = Form(""), link_ref: str = Form(""), tags: str = Form(""), note: str = Form(""),
                           user: rbac.User = Depends(rbac.require_login)):
    data = await file.read(files.max_bytes() + 1) if file is not None else b""
    try:
        out = files.save(user_login=user.login_id, filename=file.filename if file is not None else "", data=data, title=title,
                         category=category, link_kind=link_kind, link_ref=link_ref, tags=tags, note=note)
    except files.FileRejected as exc:
        if not _html(request):
            return JSONResponse({"code": "validation_error", "message": str(exc), "errors": {exc.field: str(exc)}}, status_code=422)
        return _page(request, "hub/files.html", {
            "rows": files.search(), "f": files.stats(), "q": "", "category": "", "link_kind": "", "categories": files.CATEGORIES,
            "links": {k: v[0] for k, v in files.LINKS.items()}, "allowed": sorted(files.ALLOWED), "max_mb": files.max_bytes() // (1024 * 1024),
            "is_admin": access.is_admin(user), "me": user.login_id, "errors": {exc.field: str(exc)},
            "form": {"title": title, "category": category, "link_kind": link_kind, "link_ref": link_ref, "tags": tags, "note": note},
        }, "비정형 데이터", 422)
    _log_change(request, user, "HUB-FILE-ADD", out["file_no"], {"title": out["title"], "bytes": len(data), "text_chars": out["text_chars"]})
    if not _html(request):
        return JSONResponse({"ok": True, **out})
    return _page(request, "hub/files.html", {
        "rows": files.search(), "f": files.stats(), "q": "", "category": "", "link_kind": "", "categories": files.CATEGORIES,
        "links": {k: v[0] for k, v in files.LINKS.items()}, "allowed": sorted(files.ALLOWED), "max_mb": files.max_bytes() // (1024 * 1024),
        "is_admin": access.is_admin(user), "me": user.login_id, "form": {}, "errors": {},
        "saved": f"{out['file_no']} 저장 — 추출 텍스트 {out['text_chars']:,}자",
    }, "비정형 데이터")


@router.get("/hub/files/{fid}/download", include_in_schema=False)
def hub_files_download(request: Request, fid: int, inline: int = 0, user: rbac.User = Depends(rbac.require_login)):
    row = files.get(fid)
    if not row or not files.path_of(row).exists():
        return JSONResponse({"code": "not_found", "message": "없는 파일입니다"}, status_code=404)
    show_inline = bool(inline) and (row["ext"] in files.IMAGE_EXT or row["ext"] == "pdf")       # 스크립트를 품을 수 있는 형식은 내려받기만
    audit.write_log(kind=audit.VIEW, login_id=user.login_id, user_id=user.id, screen_id="HUB", target=row["file_no"],
                    detail={"path": request.url.path, "download": True}, ip=audit.client_ip(request), device=audit.device_of(request))
    disp = "inline" if show_inline else "attachment"
    return FileResponse(files.path_of(row), media_type=row["mime"], headers={
        "Content-Disposition": f"{disp}; filename*=UTF-8''{quote(row['original_name'])}", "X-Content-Type-Options": "nosniff"})


@router.post("/hub/files/{fid}/delete", include_in_schema=False)
def hub_files_delete(request: Request, fid: int, user: rbac.User = Depends(rbac.require_login)):
    row = files.get(fid)
    if not row:
        return JSONResponse({"code": "not_found", "message": "없는 파일입니다"}, status_code=404)
    if not (access.is_admin(user) or row["created_by"] == user.login_id):
        return JSONResponse({"code": "forbidden", "message": "올린 사람이나 관리자만 지울 수 있습니다"}, status_code=403)
    files.delete(fid, user.login_id)
    _log_change(request, user, "HUB-FILE-DEL", row["file_no"], {"title": row["title"]})
    if not _html(request):
        return JSONResponse({"ok": True})
    return hub_files(request, user=user)


# ── 실시간 데이터 ─────────────────────────────────────────
def _rt_forbidden(request: Request):
    msg = "실시간 데이터는 설비 메뉴를 볼 수 있는 역할만 봅니다"
    if not _html(request):
        return JSONResponse({"code": "forbidden", "message": msg}, status_code=403)
    return _page(request, "hub/realtime.html", {"st": None, "series": [], "error": msg, "is_admin": False}, "실시간 데이터", 403)


@router.get("/hub/realtime", include_in_schema=False)
def hub_realtime(request: Request, equipment_id: int = 0, tag: str = "", hours: int = 24, user: rbac.User = Depends(rbac.require_login)):
    if not _can_rt(user):
        return _rt_forbidden(request)
    series = realtime.series()
    sel = next((s for s in series if s["equipment_id"] == equipment_id and s["tag"] == tag), series[0] if series else None)
    tr = realtime.trend(sel["equipment_id"], sel["tag"], hours) if sel else None
    vals = [float(p["value_num"]) for p in tr["points"]] if tr else []
    return _page(request, "hub/realtime.html", {
        "st": realtime.status(), "series": series, "sel": sel, "trend": tr, "hours": hours,
        "spark": realtime.sparkline(vals), "spark_min": min(vals) if vals else None, "spark_max": max(vals) if vals else None,
        "is_admin": access.is_admin(user),
    }, "실시간 데이터")


@router.get("/hub/realtime/live", include_in_schema=False)
def hub_realtime_live(request: Request, user: rbac.User = Depends(rbac.require_login)):
    if not _can_rt(user):
        return JSONResponse({"code": "forbidden", "message": "권한 없음"}, status_code=403)
    st = realtime.status()
    return JSONResponse(templating.jsonable({"values": st["values"], "raw": st["raw"], "series": realtime.series()}))


@router.post("/hub/realtime/rollup", include_in_schema=False)
def hub_realtime_rollup(request: Request, hours: int = Form(72), user: rbac.User = Depends(rbac.require_login)):
    if not access.is_admin(user):
        return JSONResponse({"code": "forbidden", "message": "관리자만 집계를 돌립니다"}, status_code=403)
    n = realtime.rollup(user.login_id, hours)
    _log_change(request, user, "HUB-RT-ROLLUP", f"{hours}h", {"rows": n})
    if not _html(request):
        return JSONResponse({"ok": True, "rows": n})
    return hub_realtime(request, user=user)


@router.get("/hub/realtime.csv", include_in_schema=False)
def hub_realtime_csv(request: Request, hours: int = 24, equipment_id: int = 0, tag: str = "", user: rbac.User = Depends(rbac.require_login)):
    if not _can_rt(user):
        return JSONResponse({"code": "forbidden", "message": "권한 없음"}, status_code=403)
    body, n = realtime.export_csv(hours, equipment_id or None, tag)
    audit.write_log(kind=audit.VIEW, login_id=user.login_id, user_id=user.id, screen_id="HUB", target="eqp_collect",
                    detail={"path": request.url.path, "export": "csv", "rows": n, "hours": hours}, ip=audit.client_ip(request),
                    device=audit.device_of(request))
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''realtime.csv", "X-Rows": str(n)})


@router.get("/hub/hub.js", include_in_schema=False)
def hub_js(user: rbac.User = Depends(rbac.require_login)) -> FileResponse:
    return FileResponse(HUB_JS, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
