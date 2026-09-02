"""Telegram notification service for strategy signals and updates."""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.crypto import decrypt_credential

logger = logging.getLogger(__name__)


class TelegramNotificationService:
    """Service for sending Telegram notifications."""

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize the Telegram notification service.

        Args:
            bot_token: Telegram Bot API token (decrypted)
            chat_id: Telegram chat ID (group or user)
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> dict:
        """
        Send a message to the Telegram chat.

        Args:
            text: Message text (supports HTML formatting)
            parse_mode: Parse mode (HTML or Markdown)
            disable_web_page_preview: Whether to disable link previews

        Returns:
            Telegram API response
        """
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def send_message_sync(
        self,
        text: str,
        *,
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True,
    ) -> dict:
        """Synchronous send helper for thread-based runners."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def test_connection(self) -> tuple[bool, str]:
        """
        Test the bot connection and chat access.

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            url = f"{self.base_url}/getMe"
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return False, f"Failed to get bot info: {response.text}"
                bot_info = response.json()
                if not bot_info.get("ok"):
                    return False, f"Bot info request failed: {response.text}"

            # Test sending a message
            test_message = "🔔 PrompTrading Strategy Bot connected successfully!"
            await self.send_message(test_message)
            return True, f"Connected as @{bot_info.get('result', {}).get('username', 'unknown')}"
        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False, str(e)


def send_signal_notification(
    db: Session,
    subscription_id: str,
    signal_info: dict,
    config: dict,
) -> bool:
    """
    Send a trading signal notification to Telegram.

    Args:
        db: Database session
        subscription_id: Strategy subscription ID
        signal_info: Signal details (symbol, side, price, etc.)
        config: Telegram configuration

    Returns:
        True if notification sent successfully
    """
    from control_plane.models import StrategySubscription

    if not config.get("enabled", False):
        return False

    if not config.get("notify_on_signal", True):
        return False

    subscription = None
    try:
        subscription = db.query(StrategySubscription).filter_by(id=subscription_id).first()
        if not subscription:
            return False

        # Decrypt bot token
        bot_token = decrypt_credential(config["bot_token"])
        chat_id = config["chat_id"]

        service = TelegramNotificationService(bot_token, chat_id)

        # Build message
        symbol = signal_info.get("symbol", "Unknown")
        side = signal_info.get("side", "UNKNOWN")
        price = signal_info.get("price", 0)
        template_name = subscription.template.name if subscription.template else "Strategy"

        emoji = "🟢" if side.upper() == "BUY" else "🔴"
        side_text = "BUY" if side.upper() == "BUY" else "SELL"

        message = (
            f"{emoji} <b>{template_name}</b>\n\n"
            f"📊 <b>Signal:</b> {side_text} {symbol}\n"
            f"💰 <b>Price:</b> ${price:,.2f}\n"
            f"⏰ <b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"📁 <b>Source:</b> Template subscription"
        )

        service.send_message_sync(message)

        # Update last notification time
        subscription.telegram_last_notification_at = datetime.now(timezone.utc)
        subscription.telegram_notification_error = None
        db.commit()

        return True

    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
        if subscription:
            subscription.telegram_notification_error = str(e)
            db.commit()
        return False


def send_execution_notification(
    db: Session,
    subscription_id: str,
    execution_info: dict,
    config: dict,
) -> bool:
    """Send a trade execution notification to Telegram."""
    from control_plane.models import StrategySubscription

    if not config.get("enabled", False):
        return False

    if not config.get("notify_on_execution", True):
        return False

    subscription = None
    try:
        subscription = db.query(StrategySubscription).filter_by(id=subscription_id).first()
        if not subscription:
            return False

        bot_token = decrypt_credential(config["bot_token"])
        chat_id = config["chat_id"]

        service = TelegramNotificationService(bot_token, chat_id)

        symbol = execution_info.get("symbol", "Unknown")
        side = execution_info.get("side", "UNKNOWN")
        size = execution_info.get("size", 0)
        filled_size = execution_info.get("filled_size", 0)
        order_type = execution_info.get("order_type", "market")
        template_name = subscription.template.name if subscription.template else "Strategy"

        emoji = "✅" if filled_size > 0 else "⚠️"
        status = "Filled" if filled_size > 0 else "Pending"

        message = (
            f"{emoji} <b>{template_name}</b> - Order {status}\n\n"
            f"📊 <b>Order:</b> {side.upper()} {symbol}\n"
            f"📝 <b>Type:</b> {order_type}\n"
            f"📦 <b>Size:</b> {size} / {filled_size}\n"
            f"⏰ <b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )

        service.send_message_sync(message)

        subscription.telegram_last_notification_at = datetime.now(timezone.utc)
        subscription.telegram_notification_error = None
        db.commit()

        return True

    except Exception as e:
        logger.error(f"Failed to send execution notification: {e}")
        if subscription:
            subscription.telegram_notification_error = str(e)
            db.commit()
        return False


def send_error_notification(
    db: Session,
    subscription_id: str,
    error_message: str,
    config: dict,
) -> bool:
    """Send an error notification to Telegram."""
    from control_plane.models import StrategySubscription

    if not config.get("enabled", False):
        return False

    if not config.get("notify_on_error", True):
        return False

    subscription = None
    try:
        subscription = db.query(StrategySubscription).filter_by(id=subscription_id).first()
        if not subscription:
            return False

        bot_token = decrypt_credential(config["bot_token"])
        chat_id = config["chat_id"]

        service = TelegramNotificationService(bot_token, chat_id)

        template_name = subscription.template.name if subscription.template else "Strategy"

        message = (
            f"⚠️ <b>{template_name}</b> - Error\n\n"
            f"❌ <b>Error:</b>\n<pre>{error_message[:500]}</pre>\n\n"
            f"⏰ <b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )

        service.send_message_sync(message)

        subscription.telegram_last_notification_at = datetime.now(timezone.utc)
        subscription.telegram_notification_error = None
        db.commit()

        return True

    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        if subscription:
            subscription.telegram_notification_error = str(e)
            db.commit()
        return False
