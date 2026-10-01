import csv
import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest
from src.execution.paper_trader import PaperTrader
from src.config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_ID, WALLET_ADDRESS

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
        self.app.add_handler(CommandHandler("set_amount", self._set_amount_handler))
        self.app.add_handler(CommandHandler("help", self._help_handler))
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
            except Exception as e:
                if attempt < max_retries:
                    wait = attempt * 3
                    logger.warning(f"Telegram connection attempt {attempt}/{max_retries} failed: {e}. Retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"Telegram initialization failed after {max_retries} attempts. Continuing without Telegram alerts.")
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
            [KeyboardButton(f"💵 Currency: {self.paper_trader.amount_currency}"), KeyboardButton("🔄 Refresh")],
            [KeyboardButton("❓ Help"), KeyboardButton("🎲 Realism: " + ("ON" if self.paper_trader.realism_mode else "OFF"))]
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
            mode = self.paper_trader.trading_mode
            
            if mode == "REAL":
                try:
                    # Fetch Real BNB Balance
                    w3 = self.paper_trader.feature_extractor.w3
                    balance_wei = await w3.eth.get_balance(WALLET_ADDRESS) if WALLET_ADDRESS else 0
                    bnb_balance = balance_wei / 1e18
                    
                    # Fetch Real SOL Balance if connected
                    sol_balance_str = "N/A (Key missing)"
                    if hasattr(self, 'solana_trader') and self.solana_trader and self.solana_trader.is_wallet_connected():
                        sol_bal = await self.solana_trader.get_sol_balance()
                        sol_addr = self.solana_trader.public_key_str
                        sol_balance_str = f"`{sol_bal:.4f} SOL` ({sol_addr[:4]}...{sol_addr[-4:]})"

                    # Entry Size display depends on currency
                    if self.paper_trader.amount_currency == "USD":
                        entry_disp = f"${self.paper_trader.trade_amount_usd:.2f} (USD)"
                    else:
                        entry_disp = f"{self.paper_trader.trade_amount_bnb} BNB"
                    
                    realism_status = "STRESS TEST 🎲" if self.paper_trader.realism_mode else "LIVE EXECUTION ⚠️"

                    balance_text = (
                        f"🏦 *Live Wallet Balances*\n\n"
                        f"🟡 *BSC Wallet:* `{bnb_balance:.4f} BNB`\n"
                        f"├ Address: `{WALLET_ADDRESS[:6]}...{WALLET_ADDRESS[-4:] if WALLET_ADDRESS else ''}`\n\n"
                        f"🟣 *Solana Wallet:* {sol_balance_str}\n\n"
                        f"├ Entry Size: `{entry_disp}` 🚀\n"
                        f"├ Target: `+{((self.paper_trader.tp_multiplier - 1) * 100):.0f}%` 🎯\n"
                        f"└ Status: `{realism_status}`"
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch real balance: {e}")
                    balance_text = "❌ *Error:* Could not fetch real wallet balance. Check your RPC or Address."
            else:
                # Simulation Balance
                balance_text = (
                    f"💳 *Bot Dashboard - PAPER MODE*\n\n"
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
            
            # Refresh real-time market prices for active positions
            try:
                await self.paper_trader.update_active_trade_prices()
            except Exception as e:
                logger.warning(f"Failed to refresh prices for active trades: {e}")
            
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
            
        elif "💵 Currency:" in text:
            # Toggle Currency Mode
            current = self.paper_trader.amount_currency
            new_mode = "USD" if current == "BNB" else "BNB"
            self.paper_trader.amount_currency = new_mode
            self.paper_trader._save_sim_state()
            
            await update.message.reply_text(f"💵 *Trade Amount currency set to {new_mode}!*")
            await self._start_handler(update, context)

        elif "🎲 Realism:" in text:
            # Toggle Realism Mode
            self.paper_trader.realism_mode = not self.paper_trader.realism_mode
            self.paper_trader._save_sim_state()
            
            status = "ON (10% Slippage + $0.50 Gas)" if self.paper_trader.realism_mode else "OFF (Ideal Parameters)"
            await update.message.reply_text(f"🎲 *Realism Mode {status}!*", parse_mode="Markdown")
            await self._start_handler(update, context)

        elif text == "❓ Help":
            await self._help_handler(update, context)

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

    async def _set_amount_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_amount <val> command."""
        try:
            curr = self.paper_trader.amount_currency
            if not context.args:
                example = "50" if curr == "USD" else "0.1"
                await update.message.reply_text(f"❌ Usage: `/set_amount <value>`\nExample: `/set_amount {example}` for {curr} entries.", parse_mode="Markdown")
                return
            
            val = float(context.args[0])
            if val <= 0:
                await update.message.reply_text("❌ Amount must be greater than 0.")
                return
            
            if curr == "USD":
                self.paper_trader.trade_amount_usd = val
                # Show estimation
                price = await self.paper_trader.feature_extractor.get_bnb_price()
                est_bnb = val / price
                await update.message.reply_text(f"✅ *Success!* Real Trade Amount set to *${val} USD*.\n_Estimated entry: {est_bnb:.4f} BNB (at ${price:,.0f}/BNB)_", parse_mode="Markdown")
            else:
                self.paper_trader.trade_amount_bnb = val
                await update.message.reply_text(f"✅ *Success!* Real Trade Amount set to *{val} BNB*.", parse_mode="Markdown")
            
            self.paper_trader._save_sim_state()
            logger.info(f"User updated Trade Amount to {val} {curr}")
            
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please use a number like 0.1 or 50.")

    async def _help_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all available commands."""
        help_text = (
            "📖 *Memer AI - Command List*\n\n"
            "*Configuration*\n"
            "├ `/set_amount <bnb>` - Set entry size (Real Mode)\n"
            "├ `/set_tp <percent>` - Set take-profit (e.g. 50)\n"
            "└ `/set_ml <percent>` - Set ML threshold (e.g. 70)\n\n"
            "*Monitoring*\n"
            "├ `/history` - View past performance\n"
            "└ `/start` - Refresh main dashboard\n\n"
            "*System*\n"
            "└ `/shutdown` - Remote stop the bot 🛑\n\n"
            "_Use the buttons below for quick navigation!_"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")
