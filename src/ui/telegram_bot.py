import csv
import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
from src.execution.paper_trader import PaperTrader
from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID

logger = logging.getLogger("TelegramBot")

class MemerTelegramBot:
    def __init__(self, paper_trader: PaperTrader):
        self.paper_trader = paper_trader
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "").replace('"', '').replace("'", "").strip()
        self.admin_id = os.getenv("TELEGRAM_ADMIN_ID", "").replace('"', '').replace("'", "").strip()
        self.market_stats = {"scanned": 0, "rejected": 0, "meta_counts": {}}
        self.shutdown_requested = False
        self.app = None

    async def start(self, max_retries: int = 5):
        """Initialize and start the Telegram bot with retry logic."""
        import asyncio
        from telegram.error import NetworkError, TimedOut

        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not found. Telegram bot disabled.")
            return

        request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
        self.app = ApplicationBuilder().token(self.token).request(request).build()

        # Add handlers
        self.app.add_handler(CommandHandler("start", self._start_handler))
        self.app.add_handler(CommandHandler("set_tp", self._set_tp_handler))
        self.app.add_handler(CommandHandler("set_ml", self._set_ml_handler))
        self.app.add_handler(CommandHandler("shutdown", self._shutdown_handler))
        self.app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self._button_handler))
        self.app.add_handler(CallbackQueryHandler(self._callback_handler))

        # Start with retry logic
        for attempt in range(1, max_retries + 1):
            try:
                await self.app.initialize()
                await self.app.start()
                await self.app.updater.start_polling()
                break  # Success
            except (NetworkError, TimedOut) as e:
                if attempt < max_retries:
                    wait = attempt * 5
                    logger.warning(f"Telegram connection failed (attempt {attempt}/{max_retries}): {e}. Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Telegram failed after {max_retries} attempts. Bot disabled.")
                    self.app = None
                    return
        
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
            token_address = query.data.replace("close_", "")
            success = await self.paper_trader.manual_close(token_address)
            if success:
                # Find symbol for better message
                await query.edit_message_text(f"❌ *Trade Closed:* Position manually exited.")
            else:
                await query.edit_message_text(f"⚠️ Failed to close trade. It might be already closed or timed out.")

    async def send_alert(self, text: str):
        """Send a proactive alert to the admin."""
        if self.app and self.admin_id:
            try:
                await self.app.bot.send_message(chat_id=self.admin_id, text=text, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send Telegram alert: {e}")

    async def _start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command and show buttons."""
        ml_label = "🤖 ML: ON" if self.paper_trader.ml_filter_enabled else "🤖 ML: OFF"
        mode_label = f"💰 Mode: {self.paper_trader.trading_mode}"
        keyboard = [
            [KeyboardButton("💰 Balance"), KeyboardButton("📡 Active Trades")],
            [KeyboardButton("📜 History"), KeyboardButton("📈 Market Stats")],
            [KeyboardButton(ml_label), KeyboardButton(mode_label)],
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
                f"💳 *Bot Dashboard - {self.paper_trader.trading_mode} MODE*\n\n"
                f"├ Current: `${self.paper_trader.balance:.2f}`\n"
                f"├ Initial: `$100.00`\n"
                f"├ TP Target: `+{((self.paper_trader.tp_multiplier - 1) * 100):.0f}%` 🎯\n"
                f"└ ML Threshold: `{self.paper_trader.ml_threshold * 100:.0f}%` 🤖"
            )
            await update.message.reply_text(balance_text, parse_mode="Markdown")
            
        elif text == "📡 Active Trades":
            if not self.paper_trader.active_trades:
                await update.message.reply_text("💤 *No active trades.* Monitoring the waves... 🌊", parse_mode="Markdown")
                return
            
            await update.message.reply_text(f"📡 *Monitoring {len(self.paper_trader.active_trades)} Active Positions:*", parse_mode="Markdown")
            
            for t in self.paper_trader.active_trades:
                profit = (t["current_price"] - t["buy_price"]) / t["buy_price"] * 100
                emoji = "🚀" if profit >= 10 else "📈" if profit >= 0 else "📉"
                if profit <= -20: emoji = "⚠️"
                
                msg = (
                    f"{emoji} *{t['symbol']}* ({t['meta']})\n"
                    f"┣ PnL: `{profit:+.2f}%` 💰\n"
                    f"┣ MC: `${t['mcap']:,.0f}`\n"
                    f"┣ Liq: `{t['liquidity']:.2f} BNB` 💧\n"
                    f"┗ `CA: {t['token']}`"
                )
                keyboard = [[InlineKeyboardButton("❌ Close Trade", callback_data=f"close_{t['token']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

        elif text == "📜 History":
            # 1. Gather stats from memory
            mem_history = self.paper_trader.history
            
            # 2. Gather stats from CSV for persistent context
            csv_total = 0
            csv_wins = 0
            csv_pnl = 0.0
            from src.execution.paper_trader import OUTCOMES_FILE
            if os.path.exists(OUTCOMES_FILE):
                try:
                    with open(OUTCOMES_FILE, "r") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            csv_total += 1
                            status = row["status"]
                            current_tp = int((self.paper_trader.tp_multiplier - 1) * 100)
                            if f"HIT_{current_tp}PCT" in status or status == "HIT_20PCT":
                                csv_wins += 1
                            csv_pnl += float(row.get("pnl_pct", "0"))
                except Exception: pass

            total_trades = csv_total
            wins = csv_wins
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
            avg_pnl = (csv_pnl / total_trades) if total_trades > 0 else 0

            history_msg = (
                f"📜 *Lifetime Trade History*\n\n"
                f"📊 *Stats Summary:*\n"
                f"├ Total Trades: `{total_trades}`\n"
                f"├ Win Rate: `{win_rate:.1f}%` (Target: +{((self.paper_trader.tp_multiplier-1)*100):.0f}%)\n"
                f"├ Avg PnL: `{avg_pnl:+.2f}%` per trade\n"
                f"└ Virtual PnL: `${(self.paper_trader.balance - 100):+.2f}`\n\n"
                f"_Showing latest outcomes from simulation.json_"
            )
            await update.message.reply_text(history_msg, parse_mode="Markdown")

        elif text == "📈 Market Stats":
            scanned = self.market_stats.get("scanned", 0)
            rejected = self.market_stats.get("rejected", 0)
            meta_counts = self.market_stats.get("meta_counts", {})
            
            conversion = ( (scanned - rejected) / scanned * 100) if scanned > 0 else 0
            
            # Find Top Meta
            top_meta = "N/A"
            if meta_counts:
                # Filter out 'Generic' for better insight if others exist
                meaningful_metas = {k: v for k, v in meta_counts.items() if k != "Generic"}
                if meaningful_metas:
                    top_meta = max(meaningful_metas, key=meaningful_metas.get)
                else:
                    top_meta = "Generic"

            stats_msg = (
                f"📊 *Live Market Intelligence*\n\n"
                f"🔍 *Activity Overview:*\n"
                f"├ Total Scanned: `{scanned}`\n"
                f"├ Rejected: `{rejected}`\n"
                f"└ Accept Rate: `{conversion:.1f}%` ✅\n\n"
                f"🌋 *Hot Narrative:* `{top_meta}`\n\n"
                f"_Scanner is running on BSC Mainnet._"
            )
            await update.message.reply_text(stats_msg, parse_mode="Markdown")

        elif "🤖 ML:" in text:
            # Toggle ML Filter
            self.paper_trader.ml_filter_enabled = not self.paper_trader.ml_filter_enabled
            self.paper_trader._save_sim_state()
            
            status = "ENABLED" if self.paper_trader.ml_filter_enabled else "DISABLED"
            thresh = f" ({self.paper_trader.ml_threshold*100:.0f}%)" if self.paper_trader.ml_filter_enabled else ""
            await update.message.reply_text(f"🤖 *ML Filter {status}!*{thresh}", parse_mode="Markdown")
            
            # Refresh keyboard
            await self._start_handler(update, context)

        elif "💰 Mode:" in text:
            # Toggle Trading Mode
            current = self.paper_trader.trading_mode
            new_mode = "REAL" if current == "PAPER" else "PAPER"
            
            self.paper_trader.trading_mode = new_mode
            self.paper_trader._save_sim_state()
            
            emoji = "⚠️" if new_mode == "REAL" else "🛡️"
            await update.message.reply_text(f"{emoji} *Trading Mode set to {new_mode}!*", parse_mode="Markdown")
            
            # Refresh keyboard
            await self._start_handler(update, context)

        elif text == "🔄 Refresh":
            await update.message.reply_text("🔄 Dashboard refreshed!")
            await self._start_handler(update, context)

    async def _set_tp_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_tp <percent> command."""
        try:
            if not context.args:
                await update.message.reply_text("❌ Usage: `/set_tp <percent>`\nExample: `/set_tp 50` for +50% target.", parse_mode="Markdown")
                return
            
            percent = float(context.args[0])
            if percent <= 0:
                await update.message.reply_text("❌ Percentage must be greater than 0.")
                return
            
            multiplier = 1 + (percent / 100)
            self.paper_trader.tp_multiplier = multiplier
            self.paper_trader._save_sim_state() # Persist change
            
            await update.message.reply_text(f"✅ *Success!* New Take-Profit target set to *+{percent:.0f}%*.\n_This will apply to all current and future trades._", parse_mode="Markdown")
            logger.info(f"User updated TP to +{percent}%")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please use a number like 20, 50, or 100.")
    async def _shutdown_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /shutdown command to stop the bot remotely."""
        if str(update.effective_user.id) != self.admin_id:
            await update.message.reply_text("⛔ *Unauthorized.* Only the admin can stop the bot.", parse_mode="Markdown")
            return
            
        await update.message.reply_text("🛑 *Shutdown command received.* Stopping Memer AI... Goodbye! 👋", parse_mode="Markdown")
        logger.warning(f"Shutdown requested by user {update.effective_user.id}")
        self.shutdown_requested = True

    async def _set_ml_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_ml <percent> command."""
        try:
            if not context.args:
                await update.message.reply_text("❌ Usage: `/set_ml <percent>`\nExample: `/set_ml 65` for 65% confidence.", parse_mode="Markdown")
                return
            
            percent = float(context.args[0])
            if not (0 < percent <= 100):
                await update.message.reply_text("❌ Percentage must be between 1 and 100.")
                return
            
            self.paper_trader.ml_threshold = percent / 100
            self.paper_trader._save_sim_state()
            
            await update.message.reply_text(f"✅ *Success!* ML Confidence Threshold set to *{percent:.0f}%*.\n_Trades below this probability will be filtered._", parse_mode="Markdown")
            logger.info(f"User updated ML Threshold to {percent}%")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please use a number like 50, 60, or 75.")
