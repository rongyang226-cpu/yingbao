import fs from "node:fs";
import { spawn } from "node:child_process";
import { QQBot } from "@tencent-connect/qqbot-nodejs";


function loadEnv(path) {
    const result = {};

    for (const raw of fs.readFileSync(path, "utf8").split(/\r?\n/)) {
        const line = raw.trim();

        if (!line || line.startsWith("#"))
            continue;

        const pos = line.indexOf("=");

        if (pos < 0)
            continue;

        result[line.slice(0, pos).trim()] =
            line.slice(pos + 1).trim();
    }

    return result;
}


function runPython(script, payload) {
    return new Promise((resolve, reject) => {
        const child = spawn(
            "/opt/ying/.venv/bin/python",
            [script],
            {
                cwd: "/opt/ying",
                env: {
                    ...process.env,
                    PYTHONPATH: "/opt/ying",
                    YING_DB_PATH: "/opt/ying/data/qq/qq.db",
                },
                stdio: ["pipe", "pipe", "pipe"],
            }
        );

        let stdout = "";
        let stderr = "";

        child.stdout.on("data", d => {
            stdout += d.toString();
        });

        child.stderr.on("data", d => {
            stderr += d.toString();
        });

        child.on("error", reject);

        child.on("close", code => {
            if (code !== 0) {
                reject(
                    new Error(
                        `Python exited ${code}: ${stderr}`
                    )
                );
                return;
            }

            try {
                const lines = stdout
                    .trim()
                    .split(/\r?\n/)
                    .filter(Boolean);

                const data = JSON.parse(lines.at(-1));

                resolve(data.reply || "");
            } catch (err) {
                reject(
                    new Error(
                        `Invalid Python output: ${stdout}\n${stderr}`
                    )
                );
            }
        });

        child.stdin.end(
            JSON.stringify(payload)
        );
    });
}


function getSenderId(msg) {
    return String(
        msg?.senderId
        || msg?.sender_id
        || msg?.sender?.id
        || msg?.sender?.openid
        || msg?.author?.id
        || msg?.author?.openid
        || msg?.raw?.author?.id
        || msg?.raw?.author?.openid
        || ""
    );
}


function getSenderName(msg) {
    return String(
        msg?.senderName
        || msg?.sender_name
        || msg?.sender?.displayName
        || msg?.sender?.nickname
        || msg?.sender?.username
        || msg?.author?.username
        || msg?.author?.nickname
        || msg?.raw?.author?.username
        || msg?.raw?.author?.nickname
        || ""
    ).trim();
}


const env = loadEnv(
    "/opt/ying/.env.qq_official"
);

const ownerOpenId = env.QQBOT_OWNER_OPENID;
const groupReplyAt = new Map();

if (!ownerOpenId)
    throw new Error("QQBOT_OWNER_OPENID missing");


const bot = new QQBot({
    appId: env.QQBOT_APP_ID,
    appSecret: env.QQBOT_APP_SECRET,
    transport: "websocket",
    tokenPrefetch: "sync",
});


bot.on("ready", () => {
    console.log(
        "===== CAT OFFICIAL SERVICE V2 ====="
    );
    console.log("READY = PASS");
    console.log("OWNER PRIVATE = ENABLED");
    console.log("GROUP CHAT = ENABLED");
});


bot.on("message", async (_ctx, msg) => {
    const target = msg?.replyTarget;

    if (!target)
        return;

    let text = String(
        msg?.content || ""
    ).trim();

    // The gateway may deliver a rich-media group message with no text.
    // Archive its metadata without storing any image bytes.
    if (!text && target.scope === "group" && msg?.attachments?.length)
        text = "（群媒体消息，未提取视觉内容）";

    if (!text)
        return;


    /*
     * OWNER 私聊
     */
    if (target.scope === "c2c") {
        if (target.targetId !== ownerOpenId)
            return;

        try {
            console.log(
                "OWNER PRIVATE MESSAGE = RECEIVED"
            );

            const reply = await runPython(
                "/opt/ying/app/platforms/qq_official/owner_reply_cli.py",
                {
                    text,
                    message_id: target.msgId,
                }
            );

            if (!reply)
                return;

            await bot.send({
                target,
                content: reply,
            });

            console.log(
                "OWNER PRIVATE SEND = PASS"
            );

        } catch (err) {
            console.error(
                "OWNER PRIVATE ERROR:",
                err?.message || err
            );
        }

        return;
    }


    /*
     * 官方 QQ 群聊
     */
    if (target.scope === "group") {
        const senderId = getSenderId(msg);
        if (msg?.senderIsBot) return;

        if (!senderId) {
            console.error(
                "GROUP MESSAGE WITHOUT SENDER ID"
            );
            return;
        }

        const senderName =
            getSenderName(msg) || "群友";

        const isOwner =
            senderId === ownerOpenId;
        const cooldownKey = `${target.targetId}:${senderId}`;
        const bridgeCooldown = Date.now() - (groupReplyAt.get(cooldownKey) || 0) < 60000;

        const reference = msg?.raw?.message_reference || msg?.raw?.reply || null;
        const referencedAuthor = reference?.author || null;
        const referencedOpenId = String(
            referencedAuthor?.member_openid || referencedAuthor?.openid || ""
        );
        const mentions = Array.isArray(msg?.mentions) ? msg.mentions : [];
        const calledByName = text.replace(/^[\s，,。.!！?？]+/, "").startsWith("猫猫");
        const mentionedBot = Boolean(
            msg?.rawEventType === "GROUP_AT_MESSAGE_CREATE"
            || mentions.some(m => m?.is_you === true)
            || calledByName
        );

        try {
            console.log(
                "GROUP MESSAGE = RECEIVED"
            );

            const reply = await runPython(
                "/opt/ying/app/platforms/qq_official/group_reply_cli.py",
                {
                    group_id: target.targetId,
                    user_id: senderId,
                    display_name:
                        isOwner
                            ? "洛小灵"
                            : senderName,
                    text,
                    message_id: target.msgId,

                    mentioned_bot: mentionedBot,
                    mentions_other: mentions.some(m => m?.is_you !== true),
                    bridge_cooldown: bridgeCooldown,
                    replied_message_id: reference?.message_id || reference?.id || null,
                    reply_to_user_id: referencedOpenId
                        ? (referencedOpenId === ownerOpenId ? "913565158" : referencedOpenId)
                        : null,
                    reply_to_name: referencedAuthor?.username || null,

                    replied_to_bot: Boolean(
                        msg?.repliedToBot
                        || msg?.replied_to_bot
                    ),

                    is_owner: isOwner,
                }
            );

            /*
             * 普通群聊随机不参与时，
             * Python 会返回空 reply。
             */
            if (!reply) {
                console.log(
                    "GROUP MESSAGE = NO REPLY"
                );
                return;
            }

            await bot.send({
                target,
                content: reply,
            });
            groupReplyAt.set(cooldownKey, Date.now());

            console.log(
                "GROUP SEND = PASS"
            );

        } catch (err) {
            console.error(
                "GROUP ERROR:",
                err?.message || err
            );
        }
    }
});


bot.on("error", err => {
    console.error(
        "QQ SDK ERROR:",
        err?.message || err
    );
});


await bot.start();
