# 莹宝

## 📦 直接下载 APK

[**标准版下载**](https://github.com/rongyang226-cpu/yingbao/releases/latest/download/Yingbao.apk) · [**vivo 兼容版下载**](https://github.com/rongyang226-cpu/yingbao/releases/latest/download/Yingbao-vivo-compat.apk)

GitHub Release 附件，文件名固定为 Yingbao.apk。

莹宝是“萤”的 Android 手机端入口。

## 2.0

- Android 原生客户端
- 专属密钥首次绑定设备
- OWNER 沿用现有身份、关系与长期记忆
- 其他用户拥有独立人物画像与记忆
- 手机端聊天复用 VPS 上的萤核心
- 国内网络兼容：nip.io / sslip.io / 裸 IP HTTPS 三级自动切换，域名 DNS 失败时仍可直连 VPS
- 原比例二次元人物悬浮模型，不做 Q 版
- 透明悬浮窗，无黑色底板
- 人物本体可拖动
- 双指整体等比例缩放，头身比例不变
- 轻点人物触发“戳一戳”
- 长按人物打开聊天
- 状态气泡约每 4.5～5.5 分钟自然出现

当前版本：3.0.0

包名：com.yingbao.app

最低系统：Android 8.0

## 模型状态

2.0 已包含可实际显示和交互的透明 2D 人物资源。

正式 Cubism Live2D（model3.json / moc3 / physics / 分层纹理）仍未制作，因此当前 2D 悬浮人物不冒充 Cubism 模型。后续可直接替换为正式 Cubism 资源。

## 安全

公开仓库不包含 VPS 密钥、API Key、Bot Token、10 把用户密钥、数据库、人物记忆、SSH 私钥或 APK 签名私钥。

## v2.1.0
- VPS raw-IP direct connection is now the first Android route, with an app-pinned HTTPS certificate; DNS domains remain fallback routes.
- Mobile long-term-memory extraction is deferred so it no longer blocks the visible reply.
- DeepSeek HTTP connections are reused to reduce repeated connection setup latency.
- Life/sleep clock is normalized to the shared UTC+8 timeline.
- Character artwork is bundled locally for the floating-window/model fallback.
- Access keys keep permanent first-device binding semantics.


## v3.0.0
- TG 和软件均可使用 `/search 关键词` 调用 VPS 本机 SearXNG，并显示实际来源；联网失败会明确回复。
- TG 和软件均可用 `/image 关键词` 接收真正的图片；软件聊天页可从相册选图发送，收到的原图只暂存用于识图，长期仅留摘要。
- 普通版与 vivo 兼容版使用相同包名和既有签名；兼容版版本码更高，已安装兼容版请继续安装兼容版。
- 固定人设与聊天规则优先发送，提高上下文缓存复用；DeepSeek 建连超时最多重试两次。
- 程序时间和软件时钟跟随 VPS，虚拟活动和记忆以数据库真实记录为准；不把未发生的动作或梦境写成事实。
- 新增 `vps/` 源码快照与部署说明；私人数据库、密钥与签名材料继续留在 VPS。
