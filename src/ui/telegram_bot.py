import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from src.execution.paper_trader import PaperTrader
from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID

logger = logging.getLogger("TelegramBot")

class MemerTelegramBot:
    def __init__(self, paper_trader: PaperTrader):
        self.paper_trader = paper_trader
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").replace('"', '').replace("'", "").strip()
        self.admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").replace('"', '').replace("'", "").strip()
        self.app = None

    async def start(self):
        """Initialize and start the Telegram bot."""
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram bot disabled.")
            return

        request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        self.app = ApplicationBuilder().token(self.token).request(request).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self._start_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._button_handler))
        self.app.add_handler(CallbackQueryHandler(self._callback_handler))

        # Start non-blocking
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        # Notify Admin on Startup
        if self.admin_id:
            try:
                await self.app.bot.send_message(
                    chat_id=self.admin_id,
                    text="🚀 *Memer AI Bot Launched!*\nMonitoring BSC for safe launches...",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send startup message: {e}")
        
        logger.info("Telegram Bot is running and polling.")

    async def _callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline button clicks."""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("close_"):
            symbol = query.data.replace("close_", "")
            success = await self.paper_trader.manual_close(symbol)
            if success:
                await query.edit_message_text(f"❌ *Trade Closed:* `{symbol}` manually exited.")
            else:
                await query.edit_message_text(f"⚠️ Failed to close `{symbol}`. Trade might be already closed.")

    async def send_alert(self, text: str):
        """Send a proactive alert to the admin."""
        if self.app and self.admin_id:
            try:
                await self.app.bot.send_message(chat_id=self.admin_id, text=text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")

    async def _start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command and show buttons."""
        keyboard = [
            [KeyboardButton("💰 Balance"), KeyboardButton("📡 Active Trades")],
            [KeyboardButton("📜 History"), KeyboardButton("📈 Market Stats")],
            [KeyboardButton("🔄 Refresh")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Welcome to *Memer AI Bot Dashboard!* 🤖\nSelect an option below to monitor your paper trading simulation.",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )

    async def _button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle reply button clicks."""
        text = update.message.text
        
        if text == "💰 Balance":
            balance_text = (
                f"💳 *Virtual Simulation Balance*\n\n"
                f"Current: `${self.paper_trader.balance:.2f}`\n"
                f"Initial: `$100.00`"
            )
            await update.message.reply_text(balance_text, parse_mode="Markdown")
            
        elif text == "📡 Active Trades":
            if not self.paper_trader.active_trades:
                await update.message.reply_text("No active paper trades at the moment. 😴")
                return
            
            for t in self.paper_trader.active_trades:
                profit = (t["current_price"] - t["buy_price"]) / t["buy_price"] * 100
                emoji = "📈" if profit >= 0 else "📉"
                msg = (
                    f"{emoji} *{t['symbol']}*\n"
                    f"└ PnL: `{profit:+.2f}%`\n"
                    f"└ Cap: `${t['mcap']:,.0f}`\n"
                    f"└ Liq: `{t['liquidity']:.2f} BNB`\n"
                    f"└ CA: `{t['token']}`"
                )
                keyboard = [[InlineKeyboardButton("❌ Close Trade", callback_data=f"close_{t['symbol']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

        elif text == "📜 History":
            if not self.paper_trader.history:
                await update.message.reply_text("Your trade history is empty. Time to find some gems! 💎")
                return

            total_trades = len(self.paper_trader.history)
            wins = len([t for t in self.paper_trader.history if t.get("status") == "HIT_2X"])
            win_rate = (wins / total_trades) * 100
            
            # Calulate total PnL
            total_pnl = 0
            for t in self.paper_trader.history:
                profit = (t["current_price"] - t["buy_price"]) / t["buy_price"] * 100
                total_pnl += profit

            msg = (
                f"📜 *Historical Performance*\n\n"
                f"Total Trades: `{total_trades}`\n"
                f"Win Rate: `{win_rate:.1f}%` (2X Hits)\n"
                f"Avg PnL: `{total_pnl/total_trades:+.2f}%`\n\n"
                f"_Check 'paper_trades.csv' for full details._"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")

        elif text == "📈 Market Stats":
            await update.message.reply_text("📈 *Market Analytics*\n(Coming soon: Total Scanned / Total Rejected / 24h Meta)")

        elif text == "🔄 Refresh":
            await update.message.reply_text("🔄 Dashboard refreshed!")
