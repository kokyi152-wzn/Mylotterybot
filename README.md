# 🎯 Thai & Laos Lottery Telegram Bot

Myanmar ဘာသာဖြင့် Thai နဲ့ Laos Lottery ဂဏန်းစစ်ပေးသော Telegram Bot

## ✨ Features

| Feature | Description |
|---|---|
| 🇹🇭 Thai Lottery | 1st prize, near 1st, 3-digit front/back, 2-digit စစ်ပေး |
| 🇱🇦 Laos Lottery | 4-digit, 3-digit, 2-digit, 1-digit စစ်ပေး |
| 🔮 Lucky Number | Thai (6, 3, 2 digit) + Laos (4 digit) ကံစမ်းဂဏန်းထုတ်ပေး |
| 📅 Results | Admin ထည့်ထားသော နောက်ဆုံးပေါက်ဂဏန်းကြည့်ရှု |

## 🚀 Setup

### 1. Bot Token ရယူရန်

1. Telegram မှာ [@BotFather](https://t.me/BotFather) ကိုဖွင့်
2. `/newbot` နှိပ်ပြီး bot တည်ဆောက်
3. Token ကိုကူးယူ

### 2. Local Run

```bash
git clone https://github.com/your-username/lottery-bot.git
cd lottery-bot

# Dependencies install
pip install -r requirements.txt

# Environment variables
cp .env.example .env
# .env ဖိုင်ထဲ token ထည့်

python bot.py
```

### 3. GitHub မှာ Deploy

1. Repo ကို GitHub မှာ push လုပ်
2. **Settings → Secrets and variables → Actions** သွား
3. Secrets နှစ်ခုထည့်:
   - `TELEGRAM_BOT_TOKEN` — BotFather မှ ရလာသော token
   - `ADMIN_IDS` — Admin Telegram user ID(s) `,` ဖြင့်ခွဲ (ဥပမာ: `123456789,987654321`)
4. **Actions → Deploy Telegram Bot → Run workflow** နှိပ်

> ⚠️ GitHub Actions free tier သည် 6 နာရီ run time သာ ပေးသောကြောင့် bot ကို 24/7 host လုပ်ရန် [Railway.app](https://railway.app) သို့မဟုတ် [Render.com](https://render.com) ကိုသုံးရန် အကြံပြုသည်။

### 4. Railway.app (Free 24/7 Hosting) — အကြံပြု

1. [railway.app](https://railway.app) မှာ account ဖွင့်
2. New Project → Deploy from GitHub repo
3. Environment Variables ထည့်:
   - `TELEGRAM_BOT_TOKEN`
   - `ADMIN_IDS`
4. Deploy ကလစ်နှိပ်ရုံ — ပြီး!

## 📱 Bot Commands

| Command | Description |
|---|---|
| `/start` | မီနူးပြသ |
| `/thai 123456` | Thai 6-digit စစ်ရန် |
| `/thai 56` | Thai 2-digit စစ်ရန် |
| `/thai 456` | Thai 3-digit စစ်ရန် |
| `/laos 1234` | Laos 4-digit စစ်ရန် |
| `/lucky` | Lucky numbers ထုတ်ရန် |
| `/results` | ပေါက်ဂဏန်းကြည့်ရန် |

### Admin Commands

| Command | Example |
|---|---|
| `/setthai` | `/setthai 1st=123456 near1st=123455,123457 3front=123,456 3back=789,012 2digit=56` |
| `/setlaos` | `/setlaos 4digit=1234 date=17/06/2026` |

## 💬 ဂဏန်းအမြန်စစ်

Command မသုံးဘဲ ဂဏန်းကိုသာ message ပို့လည်း အလိုအလျောက်စစ်ပေးသည်:
- **6 လုံး** → Thai 1st prize စစ်
- **4 လုံး** → Laos စစ်
- **2-3 လုံး** → Thai digit စစ်

## 🛡 Admin Setup

Admin ID ရှာနည်း: [@userinfobot](https://t.me/userinfobot) မှာ `/start` နှိပ်ပါ။
