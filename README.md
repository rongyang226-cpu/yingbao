# 莹宝

## 📦 直接下载 APK

[**点击下载 莹宝 v0.1.0**](./dist/Yingbao-v0.1.0.apk)

> 如果 GitHub App 里没有直接下载，请点文件后选择 Download。

莹宝是“萤”的 Android 手机端入口。

## 现在有什么

- Android 原生客户端
- 首次输入专属密钥并绑定设备
- 一台设备对应一个人物身份
- OWNER 沿用现有萤的人物关系与长期记忆
- 其他用户拥有各自独立的人物画像与聊天记忆
- 手机端聊天复用 VPS 上现有的萤核心
- 轻戳萤触发即时文字反应
- 长按萤进入聊天
- 大约每 4.5～5.5 分钟出现一次状态气泡
- Android 系统悬浮窗
- HTTPS 连接 VPS

## 下载

仓库里的 `dist/Yingbao-v0.1.0.apk` 是当前测试版 APK。

当前版本：`0.1.0`

包名：`com.yingbao.app`

最低系统：Android 8.0

## Live2D 状态

客户端和 VPS 的 Live2D 状态桥已经接好，但正式 Cubism 模型资源尚未加入。

当前仓库不包含 `.model3.json`、纹理和 Cubism 工程文件。

## 安全

这个公开仓库不会包含以下内容：

- VPS 的 `.env`
- DeepSeek API Key
- Telegram Bot Token
- 10 把用户密钥
- SQLite 数据库
- 人物记忆
- VPS SSH 私钥
- APK 签名私钥

这些私密数据只保存在 VPS。

## 目录

- `android/` Android 客户端源码
- `scripts/build.sh` 无 Gradle 的轻量构建脚本
- `dist/` 已签名测试 APK

> 这是项目早期测试版本，接口和 UI 仍会继续调整。
