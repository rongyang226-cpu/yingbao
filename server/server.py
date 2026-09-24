from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Cookie, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.live2d.state import build_live2d_state
from app.live2d.weather import search_city, current_weather
from app.live2d.mobile_chat import mobile_chat
from app.live2d.interaction import ambient_bubble, poke_reaction
from app.live2d.mobile_auth import bind_device, authenticate_device
from app.live2d.appearance import get_appearance, set_appearance
from app.activity.diary import read_today_daily_diary, DIARY_PATH

ROOT = Path("/opt/ying")
WEB_DIR = ROOT / "live2d" / "web"
MODEL_DIR = ROOT / "live2d" / "model"

app = FastAPI(title="Yingbao Bridge", version="0.2.0")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/model", StaticFiles(directory=str(MODEL_DIR)), name="model")
app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")


class BindRequest(BaseModel):
    device_id: str
    access_key: str


class ChatRequest(BaseModel):
    text: str


class PokeRequest(BaseModel):
    area: str = "body"
    streak: int = 1

class AppearanceRequest(BaseModel):
    pose: str | None = None
    outfit: str | None = None
    scale: int | None = None
async def _auth(device: str | None, session: str | None) -> dict:
    person = await authenticate_device(device or "", session or "")
    if not person:
        raise HTTPException(status_code=401, detail="unauthorized")
    return person


@app.get("/health")
async def health():
    return {"ok": True, "service": "yingbao"}


@app.post("/api/mobile/bind")
async def mobile_bind(req: BindRequest):
    result = await bind_device(req.device_id, req.access_key)
    if not result.get("ok"):
        code = result.get("error")
        status = 409 if code in {"device_already_bound", "key_already_bound"} else 401
        return JSONResponse(result, status_code=status)

    response = JSONResponse({
        "ok": True,
        "slot": result["slot"],
        "access_role": result["access_role"],
    })
    response.set_cookie(
        "ying_device", req.device_id,
        max_age=60 * 60 * 24 * 180,
        httponly=True, secure=True, samesite="strict", path="/",
    )
    response.set_cookie(
        "ying_session", result["session_secret"],
        max_age=60 * 60 * 24 * 180,
        httponly=True, secure=True, samesite="strict", path="/",
    )
    return response
@app.get("/api/mobile/whoami")
async def whoami(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    return {
        "ok": True,
        "slot": person["slot"],
        "access_role": person["access_role"],
        "display_name": person.get("display_name"),
    }


@app.get("/api/state")
async def state(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    return JSONResponse(await build_live2d_state())

@app.get("/api/mobile/weather/search")
async def weather_search(
    q: str,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    try:
        return JSONResponse(await search_city(q))
    except Exception:
        raise HTTPException(status_code=503, detail="weather_service_unavailable")

@app.get("/api/mobile/weather")
async def weather_current(
    lat: float, lon: float, tz: str,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    try:
        return JSONResponse(await current_weather(lat, lon, tz))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_location")
    except Exception:
        raise HTTPException(status_code=503, detail="weather_service_unavailable")


@app.get("/api/mobile/appearance")
async def mobile_appearance_get(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    return JSONResponse(await get_appearance(person["person_id"]))

@app.post("/api/mobile/appearance")
async def mobile_appearance_set(
    req: AppearanceRequest,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    try:
        result = await set_appearance(
            person["person_id"], pose=req.pose, outfit=req.outfit, scale=req.scale
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result)


@app.get("/api/interaction/bubble")
async def bubble(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    return {"ok": True, "text": await ambient_bubble()}


@app.post("/api/interaction/poke")
async def poke(
    req: PokeRequest,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    return {"ok": True, "text": await poke_reaction(req.area, req.streak)}
@app.get("/api/mobile/diary")
async def mobile_diary_api(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    role = str(person.get("person_role") or person.get("role") or "USER")
    if role != "OWNER":
        raise HTTPException(status_code=403, detail="owner_only")
    import re
    from datetime import datetime, timedelta, timezone
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    raw = DIARY_PATH.read_text(encoding="utf-8") if DIARY_PATH.exists() else ""
    blocks = re.findall(rf"## {re.escape(today)}[^\n]*\n(.*?)(?=\n## |\Z)", raw, flags=re.S)
    text = "\n\n".join(x.removesuffix("---").strip() for x in blocks if x.strip())
    text = re.sub(r"^\s*(?:DEBUG|INFO|WARNING|ERROR|TRACE)\b.*$", "", text, flags=re.M)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return JSONResponse({"ok": True, "date": today, "text": text})

@app.post("/api/mobile/chat")
async def mobile_chat_api(
    req: ChatRequest,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    return JSONResponse(await mobile_chat(req.text, person))


@app.get("/api/model")
async def model_info():
    model_files = list(MODEL_DIR.glob("**/*.model3.json"))
    return {
        "ready": bool(model_files),
        "model": (
            "/model/" + str(model_files[0].relative_to(MODEL_DIR))
            if model_files else None
        ),
    }


@app.get("/viewer")
async def viewer():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/download/Yingbao.apk")
async def download_apk():
    apk = ROOT / "android" / "YingbaoApp" / "build" / "Yingbao.apk"
    if not apk.exists():
        raise HTTPException(status_code=404, detail="apk_not_built")
    return FileResponse(
        apk,
        media_type="application/octet-stream",
        filename="Yingbao.apk",
        headers={
            "Content-Disposition": "attachment; filename=Yingbao.apk",
            "Cache-Control": "no-store",
        },
    )


@app.websocket("/ws")
async def websocket_state(ws: WebSocket):
    person = await authenticate_device(
        ws.cookies.get("ying_device", ""),
        ws.cookies.get("ying_session", ""),
    )
    if not person:
        await ws.close(code=4401)
        return

    await ws.accept()
    last_payload = None
    heartbeat = 0
    try:
        while True:
            state = await build_live2d_state()
            payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
            heartbeat += 1
            if payload != last_payload or heartbeat >= 10:
                await ws.send_text(payload)
                last_payload = payload
                heartbeat = 0
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close(code=1011)
        except Exception:
            pass
