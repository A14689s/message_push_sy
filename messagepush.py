import os
import logging
import asyncio
import requests
import python_socks
from telethon import TelegramClient, events
from dotenv import load_dotenv
# 自动判断：如果是在服务器(Linux)运行则不使用代理，本地(Windows)则使用代理
import sys
# 初始化日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加载配置
load_dotenv()

API_ID = int(os.getenv('TG_API_ID'))
API_HASH = os.getenv('TG_API_HASH')
# 解析监控列表
WATCH_CHATS = [int(i.strip()) if i.strip().replace('-', '').isdigit() else i.strip() for i in os.getenv('WATCH_CHATS', '').split(',')]
WATCH_TAGS = [i.strip() for i in os.getenv('WATCH_TAGS', '').split(',')]
TARGET_USER_IDS = [i.strip() for i in os.getenv('TARGET_USER_IDS', '').split(',')]
ALLOWED_BOT_ID = os.getenv('ALLOWED_BOT_ID')
# Webhooks
WEBHOOK_TAG = os.getenv('WEBHOOK_TAG')
WEBHOOK_VIP = os.getenv('WEBHOOK_VIP')
WEBHOOK_BOT = os.getenv('WEBHOOK_BOT')


def push_to_wecom(url, text):
    """通用推送函数"""
    print(f"DEBUG: 准备推送到 URL: {url}") 
    if not url:
        print("DEBUG: URL 为空，取消推送")
        return
    try:
        payload = {"msgtype": "markdown", "markdown": {"content": text}}
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        logger.error(f"推送出错: {e}")

def get_sender_name(sender):
    """获取发送者昵称的健壮函数"""
    if not sender: return "未知用户"
    first = getattr(sender, 'first_name', '') or ''
    last = getattr(sender, 'last_name', '') or ''
    name = f"{first} {last}".strip()
    if not name:
        name = getattr(sender, 'username', '') or str(sender.id)
    return name

proxy = (python_socks.ProxyType.HTTP, '127.0.0.1', 10809)

client = TelegramClient('forwarder_session', API_ID, API_HASH, proxy=proxy, connection_retries=None, auto_reconnect=True)

@client.on(events.NewMessage)
async def handler(event):
    try:
        sender = await event.get_sender()
        text = event.text or ''
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', '私信')
        sender_id = str(event.sender_id)
        username = f"@{sender.username}" if getattr(sender, 'username', None) else ""
       
        
        # --- 修改后的逻辑 A: 仅允许特定机器人 X 的私信 ---
        if event.is_private and getattr(sender, 'bot', False):
            # 只有当发送者 ID 匹配我们允许的 ID 时才转发
            if sender_id == ALLOWED_BOT_ID:
                logger.info(f"✅ 捕获目标机器人 X 的消息")
                msg = f"### 🤖 目标机器人私信\n**内容**:\n{event.text}"
                push_to_wecom(WEBHOOK_BOT, msg)
            else:
                # 如果是其他机器人，记录日志但跳过推送
                logger.info(f"⏭️ 跳过非目标机器人消息 (ID: {sender_id})")
            return

        # --- 逻辑 B: 指定群组监控 ---
        # 匹配数字ID或用户名
        is_in_watch_chats = False
        if event.chat_id in WATCH_CHATS or str(event.chat_id) in WATCH_CHATS:
            is_in_watch_chats = True
        
        if is_in_watch_chats:
            # 1. 检查大V (VIP)
            is_vip = sender_id in TARGET_USER_IDS or (username and username in TARGET_USER_IDS)
            if is_vip:
                logger.info(f"🌟 命中大V: {get_sender_name(sender)}")
                msg = f"### 🌟 大V发言\n**来源**: {get_sender_name(sender)}\n**群组**: {chat_title}\n**内容**:\n{text}"
                push_to_wecom(WEBHOOK_VIP, msg)

            # 2. 检查标签 (TAG)
            has_tag = any(tag in text for tag in WATCH_TAGS)
            if has_tag:
                logger.info(f"🏷️ 命中标签")
                msg = f"### 🏷️ 标签命中\n**来源**: {get_sender_name(sender)}\n**群组**: {chat_title}\n**内容**:\n{text}"
                push_to_wecom(WEBHOOK_TAG, msg)

    except Exception as e:
        logger.error(f"处理消息异常: {e}")

async def main():
    logger.info("==============================")
    logger.info("三路分流转发服务启动成功")
    logger.info(f"监控群组: {WATCH_CHATS}")
    logger.info(f"监控大V: {TARGET_USER_IDS}")
    logger.info(f"监控标签: {WATCH_TAGS}")
    logger.info("==============================")
    await client.start()
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())