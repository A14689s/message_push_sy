import os
import logging
import asyncio
import requests
import python_socks
from telethon import TelegramClient, events
from dotenv import load_dotenv

# ==========================================
# 1. 基础配置与日志
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载 .env 配置文件
load_dotenv()

# ==========================================
# 2. 逻辑工具函数 (必须放在主逻辑之前)
# ==========================================

def parse_env_list(key):
    """解析环境变量中的逗号分隔列表"""
    val = os.getenv(key, '')
    if not val:
        return []
    return [i.strip() for i in val.split(',') if i.strip()]

def prepare_chats(raw_list):
    """解析监听范围：将链接、@账号 转为 Telethon 可识别格式"""
    processed = []
    for item in raw_list:
        if 't.me/' in item:
            processed.append(f"@{item.split('/')[-1]}")
        elif item.lstrip('-').isdigit():
            processed.append(int(item))
        else:
            processed.append(item)
    return processed

def prepare_target_users(raw_list):
    """解析大V列表：支持数字ID和@用户名"""
    processed = []
    for item in raw_list:
        if item.lstrip('-').isdigit():
            processed.append(int(item))
        else:
            # 确保用户名带有 @ 前缀
            processed.append(item if item.startswith('@') else f"@{item}")
    return processed

# ==========================================
# 3. 配置初始化 (调用上述函数)
# ==========================================

API_ID = int(os.getenv('TG_API_ID', '0'))
API_HASH = os.getenv('TG_API_HASH', '')
WEBHOOK_URL = os.getenv('WECOM_WEBHOOK', '')

# 核心过滤规则解析
WATCH_CHATS = prepare_chats(parse_env_list('WATCH_CHATS'))
TARGET_USER_IDS = prepare_target_users(parse_env_list('TARGET_USER_IDS'))
WATCH_TAGS = parse_env_list('WATCH_TAGS')

# 代理配置 (SOCKS5 10808)
proxy = (python_socks.ProxyType.SOCKS5, '127.0.0.1', 10808)

# 初始化客户端
client = TelegramClient(
    'forwarder_session', 
    API_ID, 
    API_HASH, 
    proxy=None,
    connection_retries=None,
    auto_reconnect=True
)

# ==========================================
# 4. 核心功能函数
# ==========================================

def send_to_wecom(text):
    """推送消息到企业微信 Webhook"""
    if len(text.encode('utf-8')) > 4000:
        text = text[:1000] + "\n...(消息过长已截断)"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": text}
    }
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Webhook 发送失败: {e}")

@client.on(events.NewMessage(chats=WATCH_CHATS))
async def handler(event):
    msg = event.message
    text = msg.message
    if not text:
        return

    # 获取发送者信息
    sender = await event.get_sender()
    sender_id = msg.from_id.user_id if hasattr(msg.from_id, 'user_id') else None
    username = getattr(sender, 'username', None)
    if username:
        username = f"@{username}"

    # --- 判定逻辑：大V(is_vip) OR 有标签(has_tag) ---
    is_vip = False
    if TARGET_USER_IDS:
        if (sender_id in TARGET_USER_IDS) or (username and username in TARGET_USER_IDS):
            is_vip = True

    has_tag = False
    if WATCH_TAGS:
        has_tag = any(tag.lower() in text.lower() for tag in WATCH_TAGS)

    # 满足任一条件即转发
    if is_vip or has_tag:
        reason = "🌟 大V发言" if is_vip else "🏷️ 标签命中"
        if is_vip and has_tag: reason = "🔥 关键预警(大V+标签)"
        
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', '群组/频道')
        # 获取发送者昵称，增加空值保护
        first_name = getattr(sender, 'first_name', '') or ''
        last_name = getattr(sender, 'last_name', '') or ''
        sender_name = f"{first_name} {last_name}".strip()
        
        # 如果名字还是空的，就用用户名或 ID 顶替
        if not sender_name: sender_name = username if username else f"ID:{sender_id}"

        formatted_msg = (
            f"### {reason}\n"
            f">**来源群组**: `{chat_title}`\n"
            f">**发布人员**: `{sender_name}`\n"
            f">**消息内容**:\n{text}"
        )
        
        logger.info(f"命中规则: {reason} | 发送者: {sender_name}")
        send_to_wecom(formatted_msg)

# ==========================================
# 5. 启动入口
# ==========================================

async def main():
    await client.start()
    logger.info("=" * 30)
    logger.info("TG 实时转发服务启动成功")
    logger.info(f"监控范围: {WATCH_CHATS}")
    logger.info(f"监控大V: {TARGET_USER_IDS}")
    logger.info(f"监控标签: {WATCH_TAGS}")
    logger.info("=" * 30)
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序已手动停止")