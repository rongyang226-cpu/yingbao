from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
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
from app.commands import commands_payload

ROOT = Path("/opt/ying")
WEB_DIR = ROOT / "live2d" / "web"
MODEL_DIR = ROOT / "live2d" / "model"

app = FastAPI(title="Yingbao Bridge", version="0.3.0")
MODEL_DIR.mkdir(parents=True, exist_ok=True)
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/model", StaticFiles(directory=str(MODEL_DIR)), name="model")
app.mount("/assets", StaticFiles(directory=str(WEB_DIR / "assets")), name="assets")


@app.middleware("http")
async def record_mobile_requests(request, call_next):
    from time import perf_counter
    from app.live2d.mobile_event_log import record_event
    path = request.url.path
    if not path.startswith("/api/mobile/") and not path.startswith("/api/interaction/"):
        return await call_next(request)
    start = perf_counter()
    labels = {
        "bind": "设备绑定", "chat": "聊天", "appearance": "更换姿态或衣着",
        "weather": "天气", "diary": "日记", "games": "游戏", "logs": "日志",
        "poke": "触碰", "whoami": "身份验证",
    }
    name = next((value for key, value in labels.items() if key in path), "手机操作")
    try:
        response = await call_next(request)
    except Exception as exc:
        record_event("接口错误", f"{name}请求发生异常，耗时{(perf_counter()-start):.2f}秒", error=exc)
        raise
    if request.method != "GET" or response.status_code >= 400:
        kind = "接口错误" if response.status_code >= 400 else "操作完成"
        record_event(kind, f"{name}请求结束，状态码{response.status_code}，耗时{(perf_counter()-start):.2f}秒")
    return response


class BindRequest(BaseModel):
    device_id: str
    access_key: str


class ChatRequest(BaseModel):
    text: str


class PokeRequest(BaseModel):
    area: str = "body"
    streak: int = 1

class LocalTouchEvent(BaseModel):
    zone: str
    text: str

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


@app.get("/api/mobile/commands")
async def mobile_commands(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    role = str(person.get("person_role") or person.get("role") or person.get("access_role") or "USER")
    return JSONResponse(commands_payload("mobile", role == "OWNER"))


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
    except Exception as exc:
        from app.live2d.mobile_event_log import record_event
        record_event("天气错误", "城市搜索失败", error=exc)
        raise HTTPException(status_code=503, detail="城市搜索暂时不可用")

@app.get("/api/mobile/weather")
async def weather_current(
    lat: float, lon: float, tz: str,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    try:
        return JSONResponse(await current_weather(lat, lon, tz))
    except ValueError as exc:
        from app.live2d.mobile_event_log import record_event
        record_event("天气错误", "天气查询位置无效", error=exc)
        raise HTTPException(status_code=400, detail="城市位置无效")
    except Exception as exc:
        from app.live2d.mobile_event_log import record_event
        record_event("天气错误", "实时天气获取失败", error=exc)
        raise HTTPException(status_code=503, detail="天气暂时不可用")


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
        raise HTTPException(status_code=400, detail={"invalid_pose":"姿态不支持","invalid_outfit":"衣服不支持"}.get(str(exc),"外观设置无效"))
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
@app.post("/api/mobile/touch")
async def mobile_touch(
    req: LocalTouchEvent,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    await _auth(ying_device, ying_session)
    names = {"head": "头部", "hair": "头发", "hand": "手边", "skirt": "裙摆", "feet": "脚边"}
    if req.zone not in names or len(req.text) > 80:
        raise HTTPException(status_code=400, detail="触碰记录无效")
    from app.live2d.mobile_event_log import record_event
    record_event("触碰回应", f"轻触{names[req.zone]}，萤回应：{req.text}")
    return {"ok": True}


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


GAME_NAMES = {"2048": "2048", "chess": "国际象棋", "gomoku": "五子棋", "jump_jump": "跳一跳", "match3": "三消", "go": "围棋"}
GAME_SESSIONS = ROOT / "games" / "sessions"
_game_lock = asyncio.Lock()


def _game_summary(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    game = str(data.get("game") or path.name.split("_")[0])
    if game not in GAME_NAMES or data.get("mode") != "real":
        raise ValueError("游戏记录未通过验证")
    score = data.get("score")
    winner = data.get("winner") or data.get("result")
    winner = {"black": "你赢了" if data.get("participants") else "黑方胜", "white": "萤赢了" if data.get("participants") else "白方胜", "draw": "和棋"}.get(winner, winner)
    summary = (f"得分 {score}" if score is not None else f"结果 {winner}" if winner else "已结束")
    return {
        "编号": path.name,
        "游戏": game,
        "名称": GAME_NAMES[game],
        "时间": data.get("ended_at") or data.get("finished_at") or data.get("started_at") or "",
        "总结": summary,
        "步数": data.get("move_count") or len(data.get("moves") or data.get("history") or []),
        "已验证": True,
    }


MOBILE_2048_DIR = ROOT / "games" / "mobile_sessions"
_mobile2048_lock = asyncio.Lock()


def _mobile2048_file(person_id: int) -> Path:
    return MOBILE_2048_DIR / f"{int(person_id)}_2048.json"


def _mobile2048_response(state: dict) -> dict:
    return {"棋盘": state["board"], "得分": state["score"], "最大数字": max(max(row) for row in state["board"]), "步数": len(state["moves"]), "结束": state.get("finished", False), "对局编号": state.get("session", "")}


async def _game_owner(ying_device: str | None, ying_session: str | None) -> dict:
    person = await _auth(ying_device, ying_session)
    if str(person.get("person_role") or person.get("role")) != "OWNER":
        raise HTTPException(status_code=403, detail="仅本人可以操作游戏")
    return person


@app.get("/api/mobile/games/2048/current")
async def current_mobile_2048(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    path = _mobile2048_file(person["person_id"])
    if not path.exists():
        return {"无对局": True}
    return _mobile2048_response(json.loads(path.read_text(encoding="utf-8")))


@app.post("/api/mobile/games/2048/start")
async def start_mobile_2048(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    from games.real.game2048 import Game2048
    from app.live2d.mobile_event_log import record_event
    async with _mobile2048_lock:
        game = Game2048()
        state = {"game": "2048", "mode": "real", "started_at": datetime.now(timezone.utc).isoformat(), "board": game.board, "score": 0, "moves": [], "finished": False}
        MOBILE_2048_DIR.mkdir(parents=True, exist_ok=True)
        path = _mobile2048_file(person["person_id"])
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        record_event("游戏开始", "你在手机上开始一局真实的2048，规则运行在 VPS", game="2048")
        return _mobile2048_response(state)


class Mobile2048Move(BaseModel):
    direction: str


@app.post("/api/mobile/games/2048/move")
async def move_mobile_2048(
    req: Mobile2048Move,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    if req.direction not in {"left", "right", "up", "down"}:
        raise HTTPException(status_code=400, detail="移动方向无效")
    from games.real.game2048 import Game2048
    from app.live2d.mobile_event_log import record_event
    async with _mobile2048_lock:
        path = _mobile2048_file(person["person_id"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="请先开始对局")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("finished"):
            return _mobile2048_response(state)
        game = Game2048.__new__(Game2048)
        game.board = state["board"]
        game.score = state["score"]
        changed = game.move(req.direction)
        if not changed:
            return _mobile2048_response(state)
        state["board"] = game.board
        state["score"] = game.score
        step = len(state["moves"]) + 1
        state["moves"].append({"turn": step, "direction": req.direction, "score": game.score, "max_tile": game.max_tile(), "board": [row[:] for row in game.board]})
        state["finished"] = not game.can_move() or game.max_tile() >= 2048
        names = {"left": "左", "right": "右", "up": "上", "down": "下"}
        record_event("游戏操作", f"2048 第{step}步向{names[req.direction]}滑动，得分{game.score}，最大数字{game.max_tile()}", game="2048")
        if state["finished"]:
            state.update(ended_at=datetime.now(timezone.utc).isoformat(), move_count=step, max_tile=game.max_tile(), won=game.max_tile()>=2048, final_board=game.board)
            GAME_SESSIONS.mkdir(parents=True, exist_ok=True)
            filename="2048_mobile_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+"_"+str(person["person_id"])+".json"
            (GAME_SESSIONS / filename).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            state["session"] = filename
            record_event("游戏完成", f"手机2048对局结束，共{step}步，得分{game.score}", game="2048", result={"编号": filename})
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return _mobile2048_response(state)


def _together2048_file(person_id: int) -> Path:
    return MOBILE_2048_DIR / f"{int(person_id)}_2048_together.json"


def _together2048_response(state: dict) -> dict:
    return {**_mobile2048_response(state), "一起玩": True, "最近一步": state.get("last", ""), "你走的步数": sum(m.get("actor") == "你" for m in state["moves"]), "萤走的步数": sum(m.get("actor") == "萤" for m in state["moves"])}


@app.get("/api/mobile/games/2048/together/current")
async def current_together_2048(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    path = _together2048_file(person["person_id"])
    return _together2048_response(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {"无对局": True}


@app.post("/api/mobile/games/2048/together/start")
async def start_together_2048(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    from games.real.game2048 import Game2048
    from app.live2d.mobile_event_log import record_event
    async with _mobile2048_lock:
        game = Game2048()
        state = {"game": "2048", "mode": "real", "participants": ["你", "萤"], "started_at": datetime.now(timezone.utc).isoformat(), "board": game.board, "score": 0, "moves": [], "finished": False, "last": "轮到你"}
        MOBILE_2048_DIR.mkdir(parents=True, exist_ok=True)
        _together2048_file(person["person_id"]).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        record_event("一起游戏", "你与萤开始合作玩2048；轮流走棋，真实规则运行在 VPS", game="2048")
        return _together2048_response(state)


@app.post("/api/mobile/games/2048/together/move")
async def move_together_2048(
    req: Mobile2048Move,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    if req.direction not in {"left", "right", "up", "down"}:
        raise HTTPException(status_code=400, detail="移动方向无效")
    from games.real.game2048 import Game2048, choose_move
    from app.live2d.mobile_event_log import record_event
    async with _mobile2048_lock:
        path = _together2048_file(person["person_id"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="请先开始一起玩的对局")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("finished"):
            return _together2048_response(state)
        game = Game2048.__new__(Game2048)
        game.board = state["board"]
        game.score = state["score"]
        if not game.move(req.direction):
            return _together2048_response(state)
        directions = {"left": "左", "right": "右", "up": "上", "down": "下"}
        def remember(actor: str, direction: str):
            number = len(state["moves"]) + 1
            state["moves"].append({"turn": number, "actor": actor, "direction": direction, "score": game.score, "max_tile": game.max_tile(), "board": [row[:] for row in game.board]})
            record_event("一起游戏", f"第{number}步{actor}向{directions[direction]}移动，合作得分{game.score}", game="2048")
        remember("你", req.direction)
        reply = "你向" + directions[req.direction] + "走了一步"
        if game.can_move() and game.max_tile() < 2048:
            ai_direction = choose_move(game)
            if ai_direction and game.move(ai_direction):
                remember("萤", ai_direction)
                reply += "；萤接着向" + directions[ai_direction] + "走了一步"
        state.update(board=game.board, score=game.score, last=reply, finished=not game.can_move() or game.max_tile() >= 2048)
        if state["finished"]:
            state.update(ended_at=datetime.now(timezone.utc).isoformat(), move_count=len(state["moves"]), max_tile=game.max_tile(), won=game.max_tile()>=2048, final_board=game.board)
            GAME_SESSIONS.mkdir(parents=True, exist_ok=True)
            filename = "2048_together_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(person["person_id"]) + ".json"
            (GAME_SESSIONS / filename).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            state["session"] = filename
            record_event("一起游戏", f"你与萤的合作局结束，共{len(state['moves'])}步，得分{game.score}", game="2048")
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return _together2048_response(state)


_gomoku_lock = asyncio.Lock()


def _together_gomoku_file(person_id: int) -> Path:
    return MOBILE_2048_DIR / f"{int(person_id)}_gomoku_together.json"


def _gomoku_response(state: dict) -> dict:
    return {"棋盘": state["board"], "步数": len(state["moves"]), "结束": bool(state.get("finished")), "胜者": state.get("winner"), "最近一步": state.get("last", ""), "对局编号": state.get("session", ""), "一起玩": True}


@app.get("/api/mobile/games/gomoku/together/current")
async def current_together_gomoku(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    path = _together_gomoku_file(person["person_id"])
    return _gomoku_response(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {"无对局": True}


@app.post("/api/mobile/games/gomoku/together/start")
async def start_together_gomoku(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    from games.real.gomoku import Gomoku
    from app.live2d.mobile_event_log import record_event
    async with _gomoku_lock:
        game = Gomoku()
        state = {"game": "gomoku", "mode": "real", "participants": {"black": "你", "white": "萤"}, "started_at": datetime.now(timezone.utc).isoformat(), "board": game.board, "moves": [], "finished": False, "winner": None, "last": "你执黑棋先走"}
        MOBILE_2048_DIR.mkdir(parents=True, exist_ok=True)
        _together_gomoku_file(person["person_id"]).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        record_event("一起游戏", "你和萤开始五子棋；你执黑棋，萤执白棋", game="五子棋")
        return _gomoku_response(state)


class TogetherGomokuMove(BaseModel):
    row: int
    col: int


@app.post("/api/mobile/games/gomoku/together/move")
async def move_together_gomoku(
    req: TogetherGomokuMove,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _game_owner(ying_device, ying_session)
    from games.real.gomoku import Gomoku, BLACK, WHITE, choose_move
    from app.live2d.mobile_event_log import record_event
    async with _gomoku_lock:
        path = _together_gomoku_file(person["person_id"])
        if not path.exists():
            raise HTTPException(status_code=404, detail="请先开始五子棋")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("finished"):
            return _gomoku_response(state)
        game = Gomoku()
        game.board = state["board"]
        game.moves = state["moves"]
        if not game.place(req.row, req.col, BLACK):
            raise HTTPException(status_code=400, detail="这里不能落子")
        game.moves[-1]["actor"] = "你"
        record_event("一起游戏", f"五子棋第{len(game.moves)}手，你在第{req.row+1}行第{req.col+1}列落黑棋", game="五子棋")
        description = f"你落在第{req.row+1}行第{req.col+1}列"
        winner = "black" if game.win(req.row, req.col, BLACK) else None
        if winner is None and game.available():
            choice = choose_move(game, WHITE)
            if choice is not None:
                row, col = choice
                game.place(row, col, WHITE)
                game.moves[-1]["actor"] = "萤"
                record_event("一起游戏", f"五子棋第{len(game.moves)}手，萤在第{row+1}行第{col+1}列落白棋", game="五子棋")
                description += f"；萤落在第{row+1}行第{col+1}列"
                if game.win(row, col, WHITE):
                    winner = "white"
        if winner is None and not game.available():
            winner = "draw"
        state.update(board=game.board, moves=game.moves, last=description, winner=winner, finished=winner is not None)
        if state["finished"]:
            state.update(finished_at=datetime.now(timezone.utc).isoformat(), move_count=len(game.moves))
            GAME_SESSIONS.mkdir(parents=True, exist_ok=True)
            filename = "gomoku_together_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + str(person["person_id"]) + ".json"
            (GAME_SESSIONS / filename).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            state["session"] = filename
            result_name = {"black": "你赢了", "white": "萤赢了", "draw": "和棋"}[winner]
            record_event("一起游戏", f"五子棋结束：{result_name}，共{len(game.moves)}手", game="五子棋")
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        return _gomoku_response(state)


@app.get("/api/mobile/games")
async def mobile_games(
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    if str(person.get("person_role") or person.get("role")) != "OWNER":
        raise HTTPException(status_code=403, detail="仅本人可查看游戏")
    files = sorted(GAME_SESSIONS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    recent = []
    for path in files:
        try:
            recent.append(_game_summary(path))
        except (ValueError, OSError, json.JSONDecodeError):
            continue
        if len(recent) >= 24:
            break
    return {"游戏": [{"编号": key, "名称": label} for key, label in GAME_NAMES.items()], "最近对局": recent}


@app.get("/api/mobile/games/session/{session_id}")
async def mobile_game_session(
    session_id: str,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    if str(person.get("person_role") or person.get("role")) != "OWNER":
        raise HTTPException(status_code=403, detail="仅本人可查看游戏")
    import re
    if not re.fullmatch(r"[a-z0-9_]+\.json", session_id):
        raise HTTPException(status_code=400, detail="对局编号无效")
    path = GAME_SESSIONS / session_id
    if not path.is_file() or path.stat().st_size > 2_000_000:
        raise HTTPException(status_code=404, detail="找不到对局")
    try:
        info = _game_summary(path)
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="对局记录损坏")
    return {"对局": info, "数据": data}


@app.post("/api/mobile/games/{game}/play")
async def mobile_game_play(
    game: str,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    if str(person.get("person_role") or person.get("role")) != "OWNER":
        raise HTTPException(status_code=403, detail="仅本人可以启动游戏")
    if game not in GAME_NAMES:
        raise HTTPException(status_code=400, detail="游戏不支持")
    if _game_lock.locked():
        raise HTTPException(status_code=409, detail="正在运行另一场游戏")
    from app.activity.entertainment import play_real_game
    from app.live2d.mobile_event_log import record_event
    async with _game_lock:
        record_event("游戏开始", f"按用户操作启动{GAME_NAMES[game]}真实引擎", game=GAME_NAMES[game])
        try:
            outcome = await asyncio.wait_for(play_real_game(game), timeout=110)
            path = Path(outcome["session_file"])
            if path.parent.resolve() != GAME_SESSIONS.resolve():
                raise ValueError("对局记录位置无效")
            info = _game_summary(path)
            record_event("游戏完成", f"{GAME_NAMES[game]}真实对局结束；{info['总结']}；共{info['步数']}步", game=GAME_NAMES[game], result={"编号": path.name, "得分": outcome["result"].get("score"), "步数": info["步数"]})
            return {"对局": info}
        except Exception as exc:
            record_event("游戏错误", f"{GAME_NAMES[game]}运行失败，已停止本次对局", game=GAME_NAMES[game], error=exc)
            raise HTTPException(status_code=503, detail="游戏运行失败，错误已写入日志")


@app.get("/api/mobile/logs")
async def mobile_logs(
    limit: int = 80,
    ying_device: str | None = Cookie(default=None),
    ying_session: str | None = Cookie(default=None),
):
    person = await _auth(ying_device, ying_session)
    if str(person.get("person_role") or person.get("role")) != "OWNER":
        raise HTTPException(status_code=403, detail="仅本人可查看日志")
    from app.activity.life_log import read_recent_life_log
    from app.live2d.mobile_event_log import recent_events
    limit = max(1, min(limit, 160))
    items = [
        {"时间": item.get("time", ""), "类型": "生活", "说明": item.get("detail") or "状态更新", "心情": item.get("mood") or "", "想法": item.get("thought") or ""}
        for item in read_recent_life_log(limit)
    ]
    items.extend(recent_events(limit))
    items.sort(key=lambda item: item.get("时间", ""), reverse=True)
    return {"记录": items[:limit]}

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
