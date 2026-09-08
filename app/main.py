import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .manager import Manager, OperationError
from .folders import browse_directories, StorageUnavailable
from .error_codes import error_code
from .settings import SettingsService, SettingsValidation
from .socks import check_proxy

STATIC = Path(__file__).parent / "static"
Mode = Literal["direct", "proxy"]


class Magnet(BaseModel):
    mode: Mode
    magnet: str = Field(min_length=10, max_length=32768)


class FolderUpdate(BaseModel):
    downloads: str = Field(min_length=1, max_length=4096)
    completed: str | None = Field(default=None, max_length=4096)


class SecurityMiddleware:
    """Add local API authentication and response headers without buffering SSE."""

    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope["method"]
        path = scope["path"]
        protected = method not in ("GET", "HEAD", "OPTIONS") or path.startswith(
            ("/api/storage", "/api/settings")
        )
        if protected:
            supplied = Headers(scope=scope).get("x-p2p-token", "")
            if not secrets.compare_digest(supplied, self.token):
                response = JSONResponse(
                    {
                        "detail": "Session expirée : rechargez la page.",
                        "code": "session_expired",
                    },
                    status_code=403,
                )
                await response(scope, receive, send)
                return

        async def secured_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self' http://127.0.0.1:* "
                    "http://[::1]:*; frame-ancestors 'none'; base-uri 'none'; "
                    "form-action 'self'"
                )
                if path.startswith("/api/"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, secured_send)


def create_app(
    config,
    manager_factory=Manager,
    *,
    settings_service=None,
    setup_only=False,
    restart_callback=None,
    active_endpoint=None,
):
    token = secrets.token_urlsafe(32)
    instance_id = secrets.token_urlsafe(16)
    settings_service = settings_service or SettingsService(
        config, config._path or Path("config.yaml")
    )
    active_endpoint = active_endpoint or (config.server.host, config.server.port)

    @asynccontextmanager
    async def lifespan(app):
        app.state.manager = None if setup_only else manager_factory(config)
        try:
            if app.state.manager:
                await app.state.manager.start()
                await asyncio.to_thread(settings_service.finalize_migration)
            yield
        finally:
            if app.state.manager:
                await app.state.manager.close()

    app = FastAPI(
        title="LID — Linux ISO Downloader",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", "[::1]", "::1", "testserver"],
    )
    app.add_middleware(SecurityMiddleware, token=token)

    @app.exception_handler(OperationError)
    async def operation_error(request, exc):
        return JSONResponse(
            {"detail": str(exc), "code": error_code(str(exc))}, status_code=409
        )

    @app.exception_handler(StorageUnavailable)
    async def storage_error(request, exc):
        return JSONResponse(
            {"detail": str(exc), "code": error_code(str(exc))}, status_code=409
        )

    @app.exception_handler(SettingsValidation)
    async def settings_error(request, exc):
        return JSONResponse(
            {
                "detail": str(exc),
                "code": "invalid_settings",
                "fields": exc.fields,
                "warnings": exc.warnings,
            },
            status_code=409,
        )

    @app.get("/api/settings")
    async def settings(request: Request):
        return settings_service.public()

    @app.post("/api/settings/validate")
    async def validate_settings(body: dict):
        candidate = settings_service.candidate(body)
        result = await asyncio.to_thread(
            settings_service.validate,
            candidate,
            setup_endpoint=active_endpoint,
        )
        result["restart_required"] = settings_service.needs_restart(candidate)
        return result

    @app.post("/api/settings/proxy-check")
    async def settings_proxy_check(body: dict):
        candidate = settings_service.candidate(body)
        if not candidate.proxy.configured:
            return {
                "configured": False,
                "tcp": False,
                "udp": False,
                "message": "Aucun proxy configuré.",
            }
        return await asyncio.to_thread(check_proxy, candidate.proxy)

    @app.put("/api/settings")
    async def update_settings(body: dict, request: Request):
        candidate = settings_service.candidate(body)
        await asyncio.to_thread(
            settings_service.validate,
            candidate,
            setup_endpoint=active_endpoint,
        )
        manager = request.app.state.manager
        restart = settings_service.needs_restart(candidate)
        if restart:
            if manager and any(
                row.get("move_state") in ("moving", "verifying")
                for row in manager.state()["torrents"]
            ):
                raise OperationError(
                    "Un déplacement est en cours. Attendez sa fin avant de redémarrer."
                )
            url = await asyncio.to_thread(settings_service.stage_restart, candidate)
            if not restart_callback:
                raise OperationError("Le redémarrage supervisé est indisponible.")
            asyncio.get_running_loop().call_later(0.75, restart_callback)
            return {
                "applied": False,
                "restart": True,
                "url": url,
                "instance_id": instance_id,
            }
        return await manager.runtime_settings(candidate, settings_service)

    @app.get("/api/storage")
    async def storage(request: Request):
        manager = request.app.state.manager
        if not manager:
            return {
                "downloads": str(config.storage.downloads),
                "completed": str(config.storage.completed)
                if config.storage.completed
                else None,
                "revision": 0,
                "pending": False,
            }
        return {**manager.folders.payload(), "pending": manager.storage_pending}

    @app.put("/api/storage")
    async def update_storage(body: FolderUpdate, request: Request):
        manager = request.app.state.manager
        if not manager:
            raise OperationError("Terminez la configuration initiale avant ce réglage.")
        values = config.model_dump(mode="json")
        values["storage"]["downloads"] = body.downloads
        values["storage"]["completed"] = body.completed
        candidate = settings_service.candidate(values)
        await asyncio.to_thread(
            settings_service.validate,
            candidate,
            setup_endpoint=active_endpoint,
        )
        return await manager.runtime_settings(candidate, settings_service)

    @app.get("/api/storage/directories")
    async def directories(
        path: str | None = Query(None, max_length=4096), offset: int = Query(0, ge=0)
    ):
        return await asyncio.to_thread(browse_directories, path, offset)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/ready")
    async def ready(request: Request):
        response = JSONResponse({"ready": True, "instance_id": instance_id})
        origin = request.headers.get("origin", "")
        if origin.startswith("http://127.0.0.1:") or origin.startswith(
            "http://[::1]:"
        ):
            response.headers["Access-Control-Allow-Origin"] = origin
        return response

    @app.get("/api/bootstrap")
    async def bootstrap():
        return {
            "token": token,
            "proxy_address": f"{config.proxy.host}:{config.proxy.port}"
            if config.proxy.configured
            else None,
            "download_directory": str(config.storage.downloads),
            "setup_required": setup_only,
            "load_error": settings_service.load_error,
        }

    @app.get("/api/torrents")
    async def torrents(request: Request):
        if not request.app.state.manager:
            return {
                "torrents": [],
                "proxy": {
                    "configured": config.proxy.configured,
                    "tcp": False,
                    "udp": False,
                    "checked_at": None,
                    "message": "Configuration initiale",
                    "message_code": "proxy_checking",
                },
                "errors": [],
                "download_rate": 0,
                "upload_rate": 0,
                "total_downloaded": 0,
                "total_uploaded": 0,
                "global_ratio": 0,
                "seeding": 0,
            }
        return request.app.state.manager.state()

    @app.get("/api/proxy")
    async def proxy(request: Request):
        if not request.app.state.manager:
            return (await torrents(request))["proxy"]
        return request.app.state.manager.state()["proxy"]

    @app.post("/api/proxy/check")
    async def recheck(request: Request):
        if not request.app.state.manager:
            raise OperationError("Terminez la configuration initiale avant ce test.")
        return await request.app.state.manager.rpc("proxy", "check_proxy")

    @app.post("/api/torrents/files", status_code=201)
    async def add_files(
        request: Request, mode: Mode = Form(...), files: list[UploadFile] = File(...)
    ):
        if not request.app.state.manager:
            raise OperationError("Terminez la configuration initiale avant d'ajouter un torrent.")
        if len(files) > 20:
            return JSONResponse(
                {"detail": "Maximum 20 fichiers par dépôt.", "code": "too_many_files"},
                status_code=400,
            )
        results = []
        for file in files:
            try:
                if not (file.filename or "").lower().endswith(".torrent"):
                    raise ValueError("Seuls les fichiers .torrent sont acceptés.")
                source = await file.read(10 * 1024 * 1024 + 1)
                if len(source) > 10 * 1024 * 1024:
                    raise ValueError("Fichier trop volumineux (maximum 10 Mio).")
                record = await request.app.state.manager.add(mode, source)
                results.append({"name": file.filename, "ok": True, "id": record["id"]})
            except (ValueError, OperationError) as exc:
                results.append(
                    {
                        "name": file.filename,
                        "ok": False,
                        "error": str(exc),
                        "error_code": error_code(str(exc)),
                    }
                )
            finally:
                await file.close()
        return JSONResponse(
            {"results": results},
            status_code=201 if any(r["ok"] for r in results) else 409,
        )

    @app.post("/api/torrents/magnet", status_code=201)
    async def add_magnet(body: Magnet, request: Request):
        if not request.app.state.manager:
            raise OperationError("Terminez la configuration initiale avant d'ajouter un torrent.")
        record = await request.app.state.manager.add(body.mode, body.magnet.strip())
        return {"id": record["id"], "mode": record["mode"]}

    @app.post("/api/torrents/{key}/{action}")
    async def action(
        key: str, action: Literal["pause", "resume", "retry-move"], request: Request
    ):
        if not request.app.state.manager:
            raise OperationError("Terminez la configuration initiale.")
        try:
            return await request.app.state.manager.action(key, action)
        except KeyError:
            return JSONResponse(
                {"detail": "Torrent introuvable.", "code": "torrent_not_found"},
                status_code=404,
            )

    @app.delete("/api/torrents/{key}")
    async def remove(key: str, request: Request):
        if not request.app.state.manager:
            raise OperationError("Terminez la configuration initiale.")
        try:
            return await request.app.state.manager.action(key, "remove")
        except KeyError:
            return JSONResponse(
                {"detail": "Torrent introuvable.", "code": "torrent_not_found"},
                status_code=404,
            )

    @app.get("/api/events")
    async def events(request: Request):
        async def stream():
            while not await request.is_disconnected():
                manager = request.app.state.manager
                state = (
                    manager.state()
                    if manager
                    else {
                        "torrents": [],
                        "proxy": {"tcp": False, "udp": False},
                        "download_rate": 0,
                        "upload_rate": 0,
                        "total_downloaded": 0,
                        "total_uploaded": 0,
                        "global_ratio": 0,
                        "seeding": 0,
                    }
                )
                yield (
                    "data: "
                    + json.dumps(state, ensure_ascii=False)
                    + "\n\n"
                )
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
