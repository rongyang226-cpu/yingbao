# 萤 VPS 后端

此目录是 VPS 上正在运行的 Python 源码快照（app、games、launchers）。
Android 两版共用同一 VPS、数据库和人物状态。原图只在当次视觉理解期间暂存于
`/tmp`；图片摘要按人物和聊天范围写入数据库。

## 服务入口

- TG：`launchers/run_tg.py`
- 手机页面与 API：`app.live2d.server:app`，默认仅监听 `127.0.0.1:8765`
- 自建网页与图片检索：VPS 本机 `127.0.0.1:8888` 的 SearXNG。
  容器须使用 host 网络并将 GRANIAN_HOST 设为 127.0.0.1、GRANIAN_PORT
  设为 8888；启用 JSON 搜索格式。普通网页优先 Bing 引擎，图片使用
  Wikicommons 与 Bing Images。外部网络断开时结果应明确为空，不补造来源。
- `/search 关键词`、`/image 关键词` 同时在 TG 与手机聊天中可用。

在 `/opt/ying` 配置自己的 `.env` 和数据库，再按 `requirements.txt`
安装依赖。不要把 `.env`、`data/`、签名密钥或用户聊天记录提交到仓库。
软件端的绑定、TG OWNER、图片摘要与普通长期记忆使用同一个人物 ID。
