# Canvas 双人在线游戏 v2（公网部署版）

这是一个基于 FastAPI + WebSocket 的双人在线游戏。浏览器访问同一个公网地址后，输入相同的总局数即可匹配；当前游戏机制固定使用 6×6 棋盘。

## 本次公网化改造

- 浏览器在 HTTPS 页面下自动使用 `wss://`，在 HTTP 页面下使用 `ws://`。
- 服务端支持云平台通过 `PORT` 环境变量分配端口。
- 启用反向代理头，适配 Render、Railway、Fly.io、Nginx、Caddy 等 HTTPS 入口。
- 增加 `/healthz` 健康检查接口。
- 增加 WebSocket ping/pong，减少公网 NAT、代理空闲断线。
- 明确使用单 worker，避免玩家被分配到不同进程而无法匹配。
- 补充 `numpy` 运行依赖，并移除未使用且未声明的 `pandas` 依赖。

## 本地运行

```bash
python -m pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

打开 `http://127.0.0.1:8000`。局域网内其他设备可打开：

```text
http://你的局域网IP:8000
```

## 最简单的公网部署：Render

1. 将本目录上传到 GitHub 仓库。
2. 登录 Render，选择 **New > Blueprint**，连接该仓库。
3. Render 会读取根目录下的 `render.yaml` 和 `Dockerfile`。
4. 部署完成后，将 Render 给出的 `https://...onrender.com` 地址发给两位玩家。
5. 两人打开同一个地址，输入完全相同的总局数并开始匹配。

Render 免费实例可能休眠，首次打开时启动会较慢；正式长期运行建议使用非休眠实例。

## 使用 Docker 部署

```bash
docker build -t canvas-duel-game .
docker run --rm -p 8000:8000 -e PORT=8000 canvas-duel-game
```

访问 `http://服务器IP:8000`。正式公网环境建议在前面放置带 TLS 证书的 Nginx 或 Caddy，并通过域名使用 HTTPS。

## Nginx 反向代理示例

```nginx
server {
    listen 443 ssl http2;
    server_name game.example.com;

    ssl_certificate     /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

启动容器时可限制允许的域名：

```bash
docker run --rm -p 8000:8000 \
  -e PORT=8000 \
  -e ALLOWED_HOSTS=game.example.com \
  canvas-duel-game
```

## 重要架构限制

当前匹配队列、房间状态和棋局状态均保存在 Python 进程内存中，因此：

- 必须使用 `--workers 1`。
- 云平台实例数必须保持为 1，不能水平扩容。
- 服务重启会中断正在进行的游戏。
- 两名玩家必须连接到同一个实例。
- 当前 `game_logic.py` 的地图索引固定为 6×6，因此界面和服务端都锁定为 6×6。

若后续需要多实例、高可用或大量玩家，应将匹配与房间状态迁移到 Redis，并使用 Redis Pub/Sub 或其他消息系统同步 WebSocket 节点。

## 游戏机制函数

位于 `app/game_logic.py`：

- `create_initial_state(...)`：每局初始共享状态。
- `calculate_turn(...)`：根据双方选择和回合数计算共享状态。
- `get_flashing_cells(...)`：决定本回合结算后闪烁 1 秒的坐标。
- `get_player_view(...)`：根据玩家编号生成玩家独立视图。

## 游戏流程

- 每局 20 回合，每回合 30 秒。
- 双方提交后结算；超时方由服务器随机选择。
- 回合结果发送后，指定格子闪烁 1 秒。
- 每局结束进入休息界面，双方按空格后进入下一局；最长 60 秒，超时自动继续。
- 所有局结束后显示游戏结束。
