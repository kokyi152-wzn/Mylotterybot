import os
import random
import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from prediction import (
    predict_match,
    format_football_prediction,
    predict_lottery,
    lottery_stats,
    add_history,
    LOTTERY_HISTORY,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# Data stores (in-memory)
# ============================================================
THAI_RESULTS: dict = {}
LAOS_RESULTS: dict = {}

# Predictions store
# { match_id: { user_id: { "name": str, "pick": "home"|"away"|"draw" } } }
PREDICTIONS: dict = {}

# Football matches store
# { match_id: { "home": str, "away": str, "date": str, "time": str,
#               "result": None | "home" | "away" | "draw",
#               "score": None | "X-X" } }
FOOTBALL_MATCHES: dict = {}
_match_counter = 0


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    admin_ids_raw = os.getenv("ADMIN_IDS", "")
    admin_ids = [int(x) for x in admin_ids_raw.split(",") if x.strip().isdigit()]
    return not admin_ids or user_id in admin_ids


def next_match_id() -> str:
    global _match_counter
    _match_counter += 1
    return str(_match_counter)


# ──────────────────────────────────────────────
# /start
# ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("⚽ ဘောလုံးပွဲများ", callback_data="football_menu")],
        [
            InlineKeyboardButton("🇹🇭 Thai Lottery", callback_data="check_thai"),
            InlineKeyboardButton("🇱🇦 Laos Lottery", callback_data="check_laos"),
        ],
        [InlineKeyboardButton("🔮 Lucky Number", callback_data="lucky")],
        [InlineKeyboardButton("📅 ပေါက်ဂဏန်း", callback_data="results")],
    ]
    await update.message.reply_text(
        "🎯 *Lottery & Football Bot မှ ကြိုဆိုပါသည်!*\n\nဘာလုပ်ချင်ပါသလဲ?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ──────────────────────────────────────────────
# /help
# ──────────────────────────────────────────────
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *အသုံးပြုနည်း*\n\n"
        "⚽ *ဘောလုံး*\n"
        "/betpredict ManUtd vs Chelsea — လောင်းကြေး ခန့်မှန်း\n"
        "/matches — ပွဲစာရင်းကြည့်\n"
        "/predict <id> <home|away|draw> — ကြိုတင် guess\n"
        "/mypredicts — ကိုယ့် guess များကြည့်\n\n"
        "🎰 *ထီ ခန့်မှန်း*\n"
        "/lotterypredict — ထီ ခန့်မှန်းချက်\n"
        "/lotterystats — ထီ statistics\n\n"
        "🎰 *Lottery*\n"
        "/thai <ဂဏန်း> — Thai Lottery စစ်\n"
        "/laos <ဂဏန်း> — Laos Lottery စစ်\n"
        "/lucky — Lucky Number\n"
        "/results — ပေါက်ဂဏန်းများ\n\n"
        "👑 *Admin Commands*\n"
        "/addmatch — ပွဲသစ်ထည့်ရန်\n"
        "/setresult — ရလဒ်ထည့်ရန်\n"
        "/delmatch — ပွဲဖျက်ရန်\n"
        "/setthai — Thai ဂဏန်းထည့်\n"
        "/setlaos — Laos ဂဏန်းထည့်"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ══════════════════════════════════════════════
# FOOTBALL SECTION
# ══════════════════════════════════════════════

def result_emoji(result: str | None) -> str:
    return {"home": "🏆", "away": "🏆", "draw": "🤝", None: "⏳"}.get(result, "❓")


def format_match(mid: str, m: dict, show_result: bool = True) -> str:
    home = m["home"]
    away = m["away"]
    date = m.get("date", "")
    time = m.get("time", "")
    score = m.get("score")
    result = m.get("result")

    header = f"*[{mid}] {home} vs {away}*"
    dt = f"📅 {date} {time}".strip()

    if show_result and result:
        if result == "home":
            winner = f"🏆 အနိုင်: *{home}*"
        elif result == "away":
            winner = f"🏆 အနိုင်: *{away}*"
        else:
            winner = "🤝 သရေ"
        score_line = f"⚽ ဂိုး: `{score}`" if score else ""
        parts = [header, dt, winner]
        if score_line:
            parts.append(score_line)
        return "\n".join(p for p in parts if p)
    else:
        status = "⏳ မပြီးသေး" if not result else result_emoji(result) + " ပြီးသွား"
        return "\n".join(p for p in [header, dt, status] if p)


# /matches — list all matches
async def matches_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not FOOTBALL_MATCHES:
        await update.message.reply_text("⚽ ပွဲများ မရှိသေးပါ။")
        return

    pending = {k: v for k, v in FOOTBALL_MATCHES.items() if not v.get("result")}
    done = {k: v for k, v in FOOTBALL_MATCHES.items() if v.get("result")}

    lines = ["⚽ *ဘောလုံးပွဲများ*\n"]

    if pending:
        lines.append("🔜 *ကစားမည့်ပွဲများ*")
        for mid, m in pending.items():
            lines.append(format_match(mid, m, show_result=False))
            lines.append("")

    if done:
        lines.append("✅ *ပြီးဆုံးသွားသောပွဲများ*")
        for mid, m in done.items():
            lines.append(format_match(mid, m, show_result=True))
            lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# /result <id> — check single match result
async def result_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "ပွဲ ID ထည့်ပါ။ ဥပမာ: `/result 1`", parse_mode="Markdown"
        )
        return
    mid = context.args[0]
    m = FOOTBALL_MATCHES.get(mid)
    if not m:
        await update.message.reply_text(f"❌ ပွဲ ID `{mid}` မတွေ့ပါ။", parse_mode="Markdown")
        return
    await update.message.reply_text(format_match(mid, m, show_result=True), parse_mode="Markdown")


# Admin: /addmatch home=ManUtd away=Chelsea date=18/06/2026 time=21:00
async def add_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text(
            "အသုံးပြုနည်း:\n"
            "`/addmatch home=ManUtd away=Chelsea date=18/06/2026 time=21:00`",
            parse_mode="Markdown",
        )
        return

    data: dict = {}
    for arg in context.args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            data[k.strip()] = v.strip()

    if "home" not in data or "away" not in data:
        await update.message.reply_text("❌ `home` နဲ့ `away` လိုအပ်သည်", parse_mode="Markdown")
        return

    mid = next_match_id()
    FOOTBALL_MATCHES[mid] = {
        "home": data["home"],
        "away": data["away"],
        "date": data.get("date", ""),
        "time": data.get("time", ""),
        "result": None,
        "score": None,
    }
    await update.message.reply_text(
        f"✅ ပွဲထည့်ပြီး (ID: `{mid}`)\n{data['home']} vs {data['away']}",
        parse_mode="Markdown",
    )


# Admin: /setresult id=1 result=home score=2-1
# result values: home | away | draw
async def set_result(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text(
            "အသုံးပြုနည်း:\n"
            "`/setresult id=1 result=home score=2-1`\n"
            "result တန်ဖိုး: `home` | `away` | `draw`",
            parse_mode="Markdown",
        )
        return

    data: dict = {}
    for arg in context.args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            data[k.strip()] = v.strip()

    mid = data.get("id")
    res = data.get("result", "").lower()
    score = data.get("score")

    if not mid or res not in ("home", "away", "draw"):
        await update.message.reply_text(
            "❌ `id` နဲ့ `result` (home/away/draw) လိုအပ်သည်", parse_mode="Markdown"
        )
        return

    m = FOOTBALL_MATCHES.get(mid)
    if not m:
        await update.message.reply_text(f"❌ ပွဲ ID `{mid}` မတွေ့ပါ။", parse_mode="Markdown")
        return

    m["result"] = res
    if score:
        m["score"] = score

    home = m["home"]
    away = m["away"]

    if res == "home":
        result_msg = f"🏆 *{home}* အနိုင်ရသည်!"
    elif res == "away":
        result_msg = f"🏆 *{away}* အနိုင်ရသည်!"
    else:
        result_msg = f"🤝 သရေ!"

    score_line = f"\n⚽ ဂိုး: `{score}`" if score else ""

    # Tally predictions
    preds = PREDICTIONS.get(mid, {})
    winners = [v["name"] for v in preds.values() if v["pick"] == res]
    losers_count = len(preds) - len(winners)

    pred_lines = ""
    if preds:
        pred_lines = (
            f"\n\n🎯 *Guess ရလဒ်*\n"
            f"  ✅ မှန်သူ  : {len(winners)} ယောက်\n"
            f"  ❌ မှားသူ  : {losers_count} ယောက်"
        )
        if winners:
            names = ", ".join(winners[:10])
            if len(winners) > 10:
                names += f" နှင့် အခြား {len(winners)-10} ယောက်"
            pred_lines += f"\n\n🥳 *မှန်သူများ:*\n{names}"

    await update.message.reply_text(
        f"✅ ရလဒ်ထည့်ပြီး\n\n"
        f"[{mid}] *{home} vs {away}*\n"
        f"{result_msg}{score_line}{pred_lines}",
        parse_mode="Markdown",
    )


# /predict <id> <home|away|draw>
async def predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if len(context.args) < 2:
        await update.message.reply_text(
            "ဥပမာ: `/predict 1 home` သို့မဟုတ် `/predict 1 away` သို့မဟုတ် `/predict 1 draw`",
            parse_mode="Markdown",
        )
        return

    mid = context.args[0]
    pick = context.args[1].lower()

    if pick not in ("home", "away", "draw"):
        await update.message.reply_text(
            "❌ `home` | `away` | `draw` တစ်ခုသာ ရွေးပါ", parse_mode="Markdown"
        )
        return

    m = FOOTBALL_MATCHES.get(mid)
    if not m:
        await update.message.reply_text(f"❌ ပွဲ ID `{mid}` မတွေ့ပါ။", parse_mode="Markdown")
        return

    if m.get("result"):
        await update.message.reply_text("❌ ဒီပွဲ ပြီးသွားပြီ။ Guess မလုပ်နိုင်တော့ပါ။")
        return

    if mid not in PREDICTIONS:
        PREDICTIONS[mid] = {}

    uid = user.id
    name = user.first_name or user.username or str(uid)

    already = PREDICTIONS[mid].get(uid)
    PREDICTIONS[mid][uid] = {"name": name, "pick": pick}

    pick_label = {"home": f"🏠 {m['home']}", "away": f"✈️ {m['away']}", "draw": "🤝 သရေ"}[pick]

    if already:
        old_label = {"home": f"🏠 {m['home']}", "away": f"✈️ {m['away']}", "draw": "🤝 သရေ"}[already["pick"]]
        await update.message.reply_text(
            f"🔄 *Guess ပြောင်းပြီး*\n\n"
            f"ပွဲ: *{m['home']} vs {m['away']}*\n"
            f"ဟောင်း: {old_label}\n"
            f"သစ်: {pick_label}",
            parse_mode="Markdown",
        )
    else:
        total = len(PREDICTIONS[mid])
        await update.message.reply_text(
            f"✅ *Guess သိမ်းဆည်းပြီး*\n\n"
            f"ပွဲ: *{m['home']} vs {m['away']}*\n"
            f"မင်းရွေး: {pick_label}\n\n"
            f"👥 ဒီပွဲ guess လုပ်သူ: {total} ယောက်",
            parse_mode="Markdown",
        )


# /mypredicts — show own predictions
async def my_predicts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    found = []
    for mid, preds in PREDICTIONS.items():
        if uid in preds:
            m = FOOTBALL_MATCHES.get(mid)
            if not m:
                continue
            pick = preds[uid]["pick"]
            pick_label = {"home": f"🏠 {m['home']}", "away": f"✈️ {m['away']}", "draw": "🤝 သရေ"}[pick]
            result = m.get("result")
            if result:
                correct = "✅ မှန်" if result == pick else "❌ မှားသည်"
                status = f"{correct}"
            else:
                status = "⏳ မပြီးသေး"
            found.append(f"[{mid}] *{m['home']} vs {m['away']}*\n  ရွေး: {pick_label} — {status}")

    if not found:
        await update.message.reply_text("မင်း guess မထားသေးပါ။ `/predict <id> <home|away|draw>` နှိပ်ပါ", parse_mode="Markdown")
        return

    lines = ["🎯 *မင်းရဲ့ Guess များ*\n"] + found
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


# ──────────────────────────────────────────────
# Prediction commands
# ──────────────────────────────────────────────

# /betpredict ManUtd vs Chelsea
async def bet_predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not os.getenv("FOOTBALLDATA_KEY"):
        await update.message.reply_text("⚠️ FOOTBALLDATA_KEY မထည့်သေးပါ။")
        return
    text = " ".join(context.args)
    if "vs" not in text.lower():
        await update.message.reply_text(
            "ဥပမာ: `/betpredict ManUtd vs Chelsea`", parse_mode="Markdown"
        )
        return
    parts = text.lower().split("vs", 1)
    home_name = parts[0].strip()
    away_name = parts[1].strip()
    if not home_name or not away_name:
        await update.message.reply_text(
            "ဥပမာ: `/betpredict ManUtd vs Chelsea`", parse_mode="Markdown"
        )
        return
    msg = await update.message.reply_text("⏳ ခန့်မှန်းနေသည်...")
    try:
        pred = await predict_match(home_name, away_name)
    except Exception as e:
        await msg.edit_text(f"❌ API Error: {e}")
        return
    await msg.edit_text(format_football_prediction(pred), parse_mode="Markdown")


# /lotterypredict
async def lottery_predict_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(predict_lottery(), parse_mode="Markdown")


# /lotterystats
async def lottery_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(lottery_stats(), parse_mode="Markdown")


# Admin: /addhistory thai_2digit=56,78,12 laos_4digit=1234,5678
async def add_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text(
            "ဥပမာ:\n"
            "`/addhistory thai_2digit=56,78,12`\n"
            "`/addhistory thai_3back=123,456 laos_4digit=1234,5678`\n\n"
            "Keys: `thai_2digit`, `thai_3front`, `thai_3back`, `laos_4digit`",
            parse_mode="Markdown",
        )
        return
    added = []
    for arg in context.args:
        if "=" in arg:
            key, vals = arg.split("=", 1)
            key = key.strip()
            numbers = [v.strip() for v in vals.split(",") if v.strip()]
            if numbers:
                add_history(key, numbers)
                added.append(f"{key}: {len(numbers)} ခု")
    if added:
        await update.message.reply_text("✅ မှတ်တမ်းထည့်ပြီး\n" + "\n".join(added))
    else:
        await update.message.reply_text("❌ ဘာမှ ထည့်မရပါ")


# Admin: /delmatch <id>
async def del_match(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text("ဥပမာ: `/delmatch 1`", parse_mode="Markdown")
        return
    mid = context.args[0]
    if mid in FOOTBALL_MATCHES:
        m = FOOTBALL_MATCHES.pop(mid)
        await update.message.reply_text(
            f"🗑 ပွဲ [{mid}] {m['home']} vs {m['away']} ဖျက်ပြီး"
        )
    else:
        await update.message.reply_text(f"❌ ပွဲ ID `{mid}` မတွေ့ပါ။", parse_mode="Markdown")


# ══════════════════════════════════════════════
# LOTTERY SECTION (unchanged)
# ══════════════════════════════════════════════

def check_thai_number(number: str) -> str:
    if not THAI_RESULTS:
        return "⚠️ Thai Lottery ဂဏန်းများ မရှိသေးပါ။ Admin မှ ထည့်ပေးရန် လိုအပ်ပါသည်။"
    number = number.strip()
    wins = []
    r = THAI_RESULTS

    if len(number) == 6 and number == r.get("1st", ""):
        wins.append("🥇 ပထမဆု (1st Prize) — ဆုကြီးပေါက်သည်!")
    if len(number) == 6 and number in r.get("near1st", []):
        wins.append("🎖 ပထမဆုနီးပါး (Near 1st) ပေါက်သည်!")
    if len(number) == 2 and number == r.get("2digit", ""):
        wins.append("✅ ၂လုံးနောက် (2-Digit) ပေါက်သည်!")
    if len(number) == 6 and number[-2:] == r.get("2digit", ""):
        wins.append("✅ ၂လုံးနောက် (2-Digit) ပေါက်သည်!")
    if len(number) == 3 and number in r.get("3digit_front", []):
        wins.append("✅ ၃လုံးရှေ့ (3-Digit Front) ပေါက်သည်!")
    if len(number) == 6 and number[:3] in r.get("3digit_front", []):
        wins.append("✅ ၃လုံးရှေ့ (3-Digit Front) ပေါက်သည်!")
    if len(number) == 3 and number in r.get("3digit_back", []):
        wins.append("✅ ၃လုံးနောက် (3-Digit Back) ပေါက်သည်!")
    if len(number) == 6 and number[-3:] in r.get("3digit_back", []):
        wins.append("✅ ၃လုံးနောက် (3-Digit Back) ပေါက်သည်!")

    if wins:
        return f"🎉 *ဂဏန်း {number}*\n\n" + "\n".join(wins)
    return f"❌ *ဂဏန်း {number}* — ဆုမပေါက်ပါ။"


async def thai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("ဥပမာ: `/thai 123456`", parse_mode="Markdown")
        return
    await update.message.reply_text(check_thai_number(context.args[0]), parse_mode="Markdown")


def check_laos_number(number: str) -> str:
    if not LAOS_RESULTS:
        return "⚠️ Laos Lottery ဂဏန်းများ မရှိသေးပါ။ Admin မှ ထည့်ပေးရန် လိုအပ်ပါသည်။"
    number = number.strip()
    r = LAOS_RESULTS
    winning = r.get("4digit", "")
    date = r.get("date", "")
    wins = []

    if len(number) == 4 and number == winning:
        wins.append("🥇 ၄လုံးတိကျ ပေါက်သည်!")
    if len(number) >= 3 and number[-3:] == winning[-3:]:
        wins.append("✅ ၃လုံးနောက် ပေါက်သည်!")
    if len(number) >= 2 and number[-2:] == winning[-2:]:
        wins.append("✅ ၂လုံးနောက် ပေါက်သည်!")
    if len(number) >= 1 and number[-1:] == winning[-1:]:
        wins.append("✅ ၁လုံးနောက် ပေါက်သည်!")

    if wins:
        return f"🎉 *ဂဏန်း {number}* (Laos {date})\n\n" + "\n".join(wins)
    return f"❌ *ဂဏန်း {number}* — ဆုမပေါက်ပါ (Laos {date})။"


async def laos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("ဥပမာ: `/laos 1234`", parse_mode="Markdown")
        return
    await update.message.reply_text(check_laos_number(context.args[0]), parse_mode="Markdown")


def generate_lucky() -> str:
    lines = [
        "🔮 *Lucky Numbers ထုတ်ပေးသည်*\n",
        f"🇹🇭 Thai 6-digit : `{random.randint(100000, 999999)}`",
        f"🇹🇭 Thai 2-digit : `{random.randint(10, 99)}`",
        f"🇹🇭 Thai 3-digit : `{random.randint(100, 999)}`",
        f"🇱🇦 Laos 4-digit : `{random.randint(1000, 9999)}`",
        "",
        "_ဂဏန်းများသည် ကံကြမ္မာတင် ဆုံးဖြတ်သော အတွက် တာဝန်မယူနိုင်ပါ။_",
    ]
    return "\n".join(lines)


async def lucky_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(generate_lucky(), parse_mode="Markdown")


async def results_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lines = ["📅 *နောက်ဆုံး ပေါက်ဂဏန်းများ*\n"]
    if THAI_RESULTS:
        r = THAI_RESULTS
        lines += [
            "🇹🇭 *Thai Lottery*",
            f"  ပထမဆု (1st)      : `{r.get('1st', '-')}`",
            f"  နီးပါး (Near 1st): `{', '.join(r.get('near1st', []))}`",
            f"  ၃လုံးရှေ့         : `{', '.join(r.get('3digit_front', []))}`",
            f"  ၃လုံးနောက်        : `{', '.join(r.get('3digit_back', []))}`",
            f"  ၂လုံးနောက်        : `{r.get('2digit', '-')}`",
        ]
    else:
        lines.append("🇹🇭 Thai Lottery — မရှိသေးပါ")
    lines.append("")
    if LAOS_RESULTS:
        r = LAOS_RESULTS
        lines += [
            "🇱🇦 *Laos Lottery*",
            f"  ရက်စွဲ   : {r.get('date', '-')}",
            f"  ၄လုံး    : `{r.get('4digit', '-')}`",
        ]
    else:
        lines.append("🇱🇦 Laos Lottery — မရှိသေးပါ")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def set_thai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text(
            "`/setthai 1st=123456 near1st=123455,123457 3front=123,456 3back=789,012 2digit=56`",
            parse_mode="Markdown",
        )
        return
    global THAI_RESULTS
    data: dict = {}
    for arg in context.args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            if k == "near1st":
                data["near1st"] = v.split(",")
            elif k == "3front":
                data["3digit_front"] = v.split(",")
            elif k == "3back":
                data["3digit_back"] = v.split(",")
            elif k in ("1st", "2digit"):
                data[k] = v
    THAI_RESULTS = data
    await update.message.reply_text("✅ Thai Lottery ဂဏန်းများ သိမ်းဆည်းပြီး")


async def set_laos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Admin ခွင့်မပြု")
        return
    if not context.args:
        await update.message.reply_text(
            "`/setlaos 4digit=1234 date=17/06/2026`", parse_mode="Markdown"
        )
        return
    global LAOS_RESULTS
    data: dict = {}
    for arg in context.args:
        if "=" in arg:
            k, v = arg.split("=", 1)
            data[k] = v
    LAOS_RESULTS = data
    await update.message.reply_text("✅ Laos Lottery ဂဏန်းများ သိမ်းဆည်းပြီး")


# ──────────────────────────────────────────────
# Inline keyboard callbacks
# ──────────────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "football_menu":
        keyboard = [
            [InlineKeyboardButton("📋 ပွဲစာရင်းကြည့်", callback_data="fb_list")],
            [InlineKeyboardButton("🎯 ကြိုတင် Guess လုပ်ရန်", callback_data="fb_predict")],
            [InlineKeyboardButton("🔍 ပွဲရလဒ်စစ်ရန်", callback_data="fb_check")],
            [InlineKeyboardButton("📊 ကိုယ့် Guess ကြည့်", callback_data="fb_mypredicts")],
            [InlineKeyboardButton("🔙 နောက်သို့", callback_data="back_main")],
        ]
        await query.message.reply_text(
            "⚽ *ဘောလုံးပွဲများ*\nဘာလုပ်ချင်ပါသလဲ?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "fb_list":
        if not FOOTBALL_MATCHES:
            await query.message.reply_text("⚽ ပွဲများ မရှိသေးပါ။")
            return
        lines = ["⚽ *ဘောလုံးပွဲများ*\n"]
        for mid, m in FOOTBALL_MATCHES.items():
            pcount = len(PREDICTIONS.get(mid, {}))
            lines.append(format_match(mid, m, show_result=True))
            if not m.get("result"):
                lines.append(f"  👥 Guess လုပ်သူ: {pcount} ယောက်")
            lines.append("")
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")

    elif query.data == "fb_check":
        await query.message.reply_text(
            "ပွဲ ID ထည့်ပါ။ ဥပမာ: `/result 1`", parse_mode="Markdown"
        )

    elif query.data == "fb_predict":
        await query.message.reply_text(
            "🎯 *ကြိုတင် Guess လုပ်ရန်*\n\n"
            "ဥပမာ:\n"
            "`/predict 1 home` — ပထမအသင်းနိုင်မယ်\n"
            "`/predict 1 away` — ဒုတိယအသင်းနိုင်မယ်\n"
            "`/predict 1 draw` — သရေဖြစ်မယ်\n\n"
            "ပွဲစာရင်း ကြည့်ရန် /matches",
            parse_mode="Markdown",
        )

    elif query.data == "fb_mypredicts":
        uid = query.from_user.id
        found = []
        for mid, preds in PREDICTIONS.items():
            if uid in preds:
                m = FOOTBALL_MATCHES.get(mid)
                if not m:
                    continue
                pick = preds[uid]["pick"]
                pick_label = {"home": f"🏠 {m['home']}", "away": f"✈️ {m['away']}", "draw": "🤝 သရေ"}[pick]
                result = m.get("result")
                if result:
                    status = "✅ မှန်" if result == pick else "❌ မှားသည်"
                else:
                    status = "⏳ မပြီးသေး"
                found.append(f"[{mid}] *{m['home']} vs {m['away']}*\n  ရွေး: {pick_label} — {status}")
        if not found:
            await query.message.reply_text("မင်း guess မထားသေးပါ။ `/predict <id> <home|away|draw>` နှိပ်ပါ", parse_mode="Markdown")
        else:
            lines = ["📊 *မင်းရဲ့ Guess များ*\n"] + found
            await query.message.reply_text("\n\n".join(lines), parse_mode="Markdown")

    elif query.data == "back_main":
        keyboard = [
            [InlineKeyboardButton("⚽ ဘောလုံးပွဲများ", callback_data="football_menu")],
            [
                InlineKeyboardButton("🇹🇭 Thai Lottery", callback_data="check_thai"),
                InlineKeyboardButton("🇱🇦 Laos Lottery", callback_data="check_laos"),
            ],
            [InlineKeyboardButton("🔮 Lucky Number", callback_data="lucky")],
            [InlineKeyboardButton("📅 ပေါက်ဂဏန်း", callback_data="results")],
        ]
        await query.message.reply_text(
            "🎯 *ပင်မမီနူး*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    elif query.data == "check_thai":
        await query.message.reply_text(
            "🇹🇭 ဂဏန်းထည့်ပါ:\n`/thai 123456`", parse_mode="Markdown"
        )
    elif query.data == "check_laos":
        await query.message.reply_text(
            "🇱🇦 ဂဏန်းထည့်ပါ:\n`/laos 1234`", parse_mode="Markdown"
        )
    elif query.data == "lucky":
        await query.message.reply_text(generate_lucky(), parse_mode="Markdown")
    elif query.data == "results":
        lines = ["📅 *နောက်ဆုံး ပေါက်ဂဏန်းများ*\n"]
        if THAI_RESULTS:
            r = THAI_RESULTS
            lines += [
                "🇹🇭 *Thai Lottery*",
                f"  ပထမဆု (1st)      : `{r.get('1st', '-')}`",
                f"  နီးပါး (Near 1st): `{', '.join(r.get('near1st', []))}`",
                f"  ၃လုံးရှေ့         : `{', '.join(r.get('3digit_front', []))}`",
                f"  ၃လုံးနောက်        : `{', '.join(r.get('3digit_back', []))}`",
                f"  ၂လုံးနောက်        : `{r.get('2digit', '-')}`",
            ]
        else:
            lines.append("🇹🇭 Thai Lottery — မရှိသေးပါ")
        lines.append("")
        if LAOS_RESULTS:
            r = LAOS_RESULTS
            lines += [
                "🇱🇦 *Laos Lottery*",
                f"  ရက်စွဲ   : {r.get('date', '-')}",
                f"  ၄လုံး    : `{r.get('4digit', '-')}`",
            ]
        else:
            lines.append("🇱🇦 Laos Lottery — မရှိသေးပါ")
        await query.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ──────────────────────────────────────────────
# Plain message handler
# ──────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()
    if text.isdigit():
        if len(text) == 6:
            await update.message.reply_text(check_thai_number(text), parse_mode="Markdown")
        elif len(text) == 4:
            await update.message.reply_text(check_laos_number(text), parse_mode="Markdown")
        elif len(text) in (2, 3):
            await update.message.reply_text(check_thai_number(text), parse_mode="Markdown")
        else:
            await update.message.reply_text("2, 3, 4 သို့မဟုတ် 6 လုံး ဂဏန်း ထည့်ပါ။")
    else:
        await update.message.reply_text(
            "ဂဏန်းတစ်ခု ထည့်ပါ သို့မဟုတ် /start နှိပ်ပါ။"
        )


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable မထည့်သေးပါ!")

    app = Application.builder().token(token).build()

    # Lottery
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("thai", thai_command))
    app.add_handler(CommandHandler("laos", laos_command))
    app.add_handler(CommandHandler("lucky", lucky_command))
    app.add_handler(CommandHandler("results", results_command))
    app.add_handler(CommandHandler("setthai", set_thai))
    app.add_handler(CommandHandler("setlaos", set_laos))

    # Football (manual)
    app.add_handler(CommandHandler("matches", matches_command))
    app.add_handler(CommandHandler("result", result_command))
    app.add_handler(CommandHandler("predict", predict_command))
    app.add_handler(CommandHandler("mypredicts", my_predicts))
    app.add_handler(CommandHandler("addmatch", add_match))
    app.add_handler(CommandHandler("setresult", set_result))
    app.add_handler(CommandHandler("delmatch", del_match))

    # Predictions
    app.add_handler(CommandHandler("betpredict", bet_predict_command))
    app.add_handler(CommandHandler("lotterypredict", lottery_predict_command))
    app.add_handler(CommandHandler("lotterystats", lottery_stats_command))
    app.add_handler(CommandHandler("addhistory", add_history_command))

    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot စတင်နေသည်...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    asyncio.run(main())
