import asyncio
import json
import os
import random
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .game_logic import BoardState, calculate_turn, create_initial_state, get_flashing_cells, get_player_view
from .functionWarGame import *

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title='Canvas Duel Game')

# 公网部署时可用逗号分隔域名，例如：game.example.com,www.game.example.com
# 默认允许所有 Host，便于 Render/Railway/Fly.io 等平台首次部署。
allowed_hosts = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '*').split(',') if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ['*'])
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')

TURN_SECONDS = 30
REST_SECONDS = 60
TURNS_PER_GAME = 20


@app.get('/')
async def index():
    return FileResponse(str(BASE_DIR / 'static' / 'index.html'))


@app.get('/healthz')
async def healthz():
    """供公网托管平台和容器编排系统做健康检查。"""
    return {'status': 'ok', 'waitingPlayers': len(waiting)}


class Player:
    def __init__(self, ws: WebSocket, total_games: int, rows: int, cols: int):
        self.id = str(uuid.uuid4())
        self.ws = ws
        self.total_games = total_games
        self.rows = rows
        self.cols = cols
        self.number = 0
        self.room: Optional['GameRoom'] = None

    async def send(self, payload: Dict):
        await self.ws.send_text(json.dumps(payload, ensure_ascii=False))


class GameRoom:
    def __init__(self, p1: Player, p2: Player):
        self.players = [p1, p2]
        p1.number, p2.number = 1, 2
        p1.room = p2.room = self
        self.rows = min(p1.rows, p2.rows)
        self.cols = min(p1.cols, p2.cols)
        self.total_games = min(p1.total_games, p2.total_games)
        self.game_number = 0
        self.turn_number = 0
        self.state: BoardState = create_initial_state(self.rows, self.cols, 1)
        self.selections: Dict[int, List[Tuple[int, int]]] = {}
        self.rest_ready: Set[int] = set()
        self.condition = asyncio.Condition()
        self.closed = False
        self.task = asyncio.create_task(self.run())

    async def safe_send(self, player: Player, payload: Dict):
        try:
            await player.send(payload)
        except Exception:
            self.closed = True

    async def broadcast(self, payload: Dict):
        await asyncio.gather(*(self.safe_send(p, payload) for p in self.players))

    async def send_state_to_each(self, phase: str, seconds: int = 0, flashing=None):
        for p in self.players:
            view = get_player_view(p.number, self.game_number, self.turn_number, self.state)
            payload = {
                'type': 'state', 'phase': phase, 'player': p.number,
                'game': self.game_number, 'totalGames': self.total_games,
                'turn': self.turn_number, 'turnsPerGame': TURNS_PER_GAME,
                'seconds': seconds, 'rows': self.rows, 'cols': self.cols,
                'board': view,
                'flashing': flashing or [],
            }
            await self.safe_send(p, payload)

    async def run(self):
        await asyncio.gather(
            self.safe_send(self.players[0], {'type': 'matched', 'player': 1}),
            self.safe_send(self.players[1], {'type': 'matched', 'player': 2}),
        )
        for game in range(1, self.total_games + 1):
            if self.closed: return
            self.game_number = game
            self.turn_number = 0
            self.state = create_initial_state(self.rows, self.cols, game)
            await self.send_state_to_each('game_start')
            await asyncio.sleep(0.5)

            for turn in range(1, TURNS_PER_GAME + 1):
                if self.closed: return
                self.turn_number = turn
                self.selections = {}
                await self.send_state_to_each('turn', TURN_SECONDS)

                try:
                    async with self.condition:
                        await asyncio.wait_for(self.condition.wait_for(lambda: len(self.selections) == 2 or self.closed), TURN_SECONDS)
                except asyncio.TimeoutError:
                    pass
                if self.closed: return

                for n in (1, 2):
                    if n not in self.selections:
                        count = random.randint(1, max(1, min(4, self.rows * self.cols)))
                        all_cells = [(r, c) for r in range(self.rows) for c in range(self.cols)]
                        self.selections[n] = random.sample(all_cells, count)
                        await self.safe_send(self.players[n - 1], {'type': 'auto_selected', 'cells': self.selections[n]})

                self.state = calculate_turn(self.selections[1], self.selections[2], turn, self.state)
                flashing = get_flashing_cells(self.selections[1], self.selections[2], turn, self.state)
                await self.send_state_to_each('turn_result', flashing=flashing)
                await asyncio.sleep(1.0)
                if checkEndGame(self.state["shapes"]):
                    break

            if game < self.total_games:
                self.rest_ready = set()
                await self.send_state_to_each('rest', REST_SECONDS)
                try:
                    async with self.condition:
                        await asyncio.wait_for(self.condition.wait_for(lambda: len(self.rest_ready) == 2 or self.closed), REST_SECONDS)
                except asyncio.TimeoutError:
                    pass
                if self.closed: return
                await self.broadcast({'type': 'rest_complete'})
            else:
                await self.broadcast({'type': 'game_over'})

    async def submit(self, player: Player, cells):
        if self.turn_number < 1 or self.turn_number > TURNS_PER_GAME: return
        clean = []
        seen = set()
        for item in cells:
            if isinstance(item, list) and len(item) == 2:
                r, c = item
                if isinstance(r, int) and isinstance(c, int) and 0 <= r < self.rows and 0 <= c < self.cols and (r, c) not in seen:
                    seen.add((r, c)); clean.append((r, c))
        async with self.condition:
            if player.number not in self.selections:
                self.selections[player.number] = clean
                self.condition.notify_all()

    async def ready_after_rest(self, player: Player):
        async with self.condition:
            self.rest_ready.add(player.number)
            self.condition.notify_all()


waiting: List[Player] = []
waiting_lock = asyncio.Lock()


async def enqueue(player: Player):
    async with waiting_lock:
        match = None
        for p in waiting:
            if p.rows == player.rows and p.cols == player.cols and p.total_games == player.total_games:
                match = p; break
        if match:
            waiting.remove(match)
            GameRoom(match, player)
        else:
            waiting.append(player)
            await player.send({'type': 'waiting'})


@app.websocket('/ws')
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    player = None
    try:
        hello = await ws.receive_json()
        total_games = max(1, min(100, int(hello.get('totalGames', 1))))
        # 当前游戏机制在 game_logic.py 中固定使用 6x6 地图。
        # 服务端强制使用 6x6，避免恶意或旧客户端传入其他尺寸导致越界。
        rows = 6
        cols = 6
        player = Player(ws, total_games, rows, cols)
        await enqueue(player)
        while True:
            msg = await ws.receive_json()
            if not player.room: continue
            if msg.get('type') == 'submit':
                await player.room.submit(player, msg.get('cells', []))
            elif msg.get('type') == 'rest_ready':
                await player.room.ready_after_rest(player)
    except WebSocketDisconnect:
        pass
    finally:
        if player:
            async with waiting_lock:
                if player in waiting: waiting.remove(player)
            if player.room:
                player.room.closed = True
                for p in player.room.players:
                    if p is not player:
                        await player.room.safe_send(p, {'type': 'opponent_left'})
