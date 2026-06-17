"""
Prediction engine:
  1. Football match win-probability using football-data.org API
  2. Thai / Laos lottery hot-cold number analysis
"""

import os
import httpx
from collections import Counter

# ──────────────────────────────────────────────
# football-data.org helpers
# ──────────────────────────────────────────────
FD_BASE = "https://api.football-data.org/v4"


def _fd_headers() -> dict:
    return {"X-Auth-Token": os.getenv("FOOTBALLDATA_KEY", "")}


async def _fd_get(path: str, params: dict | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{FD_BASE}{path}", headers=_fd_headers(), params=params or {})
        r.raise_for_status()
        return r.json()


# Fetch last N finished matches for a team
async def _team_recent_form(team_id: int, limit: int = 5) -> list[dict]:
    data = await _fd_get(f"/teams/{team_id}/matches", {"status": "FINISHED", "limit": limit})
    return data.get("matches", [])


# Fetch head-to-head between two teams
async def _head_to_head(team1_id: int, team2_id: int, limit: int = 5) -> list[dict]:
    data = await _fd_get("/matches", {"homeTeam": team1_id, "awayTeam": team2_id, "limit": limit})
    matches = data.get("matches", [])
    if len(matches) < 3:
        # Also try reversed
        data2 = await _fd_get("/matches", {"homeTeam": team2_id, "awayTeam": team1_id, "limit": limit})
        matches += data2.get("matches", [])
    return matches[:limit]


# Search team by name
async def search_team(name: str) -> list[dict]:
    data = await _fd_get("/teams", {"name": name})
    return data.get("teams", [])


def _form_score(matches: list[dict], team_id: int) -> float:
    """Return a score 0-1 based on recent results (win=1, draw=0.5, loss=0)."""
    if not matches:
        return 0.5
    pts = 0.0
    for m in matches[-5:]:
        home_id = m["homeTeam"]["id"]
        away_id = m["awayTeam"]["id"]
        home_g = m["score"]["fullTime"]["home"]
        away_g = m["score"]["fullTime"]["away"]
        if home_g is None or away_g is None:
            continue
        if home_id == team_id:
            if home_g > away_g:
                pts += 1
            elif home_g == away_g:
                pts += 0.5
        elif away_id == team_id:
            if away_g > home_g:
                pts += 1
            elif away_g == home_g:
                pts += 0.5
    return pts / max(len(matches), 1)


def _h2h_edge(matches: list[dict], team_id: int) -> float:
    """Return 0-1 based on head-to-head wins."""
    if not matches:
        return 0.5
    wins = 0
    for m in matches:
        home_id = m["homeTeam"]["id"]
        home_g = m["score"]["fullTime"]["home"]
        away_g = m["score"]["fullTime"]["away"]
        if home_g is None or away_g is None:
            continue
        if home_id == team_id:
            if home_g > away_g:
                wins += 1
        else:
            if away_g > home_g:
                wins += 1
    return wins / len(matches)


async def predict_match(home_name: str, away_name: str) -> dict:
    """
    Predict a match between two teams.
    Returns: {home, away, home_win_pct, draw_pct, away_win_pct,
              home_form, away_form, h2h_note, verdict}
    """
    # Search teams
    home_teams = await search_team(home_name)
    away_teams = await search_team(away_name)

    if not home_teams:
        return {"error": f"'{home_name}' အသင်း မတွေ့ပါ"}
    if not away_teams:
        return {"error": f"'{away_name}' အသင်း မတွေ့ပါ"}

    home_team = home_teams[0]
    away_team = away_teams[0]
    home_id = home_team["id"]
    away_id = away_team["id"]
    home_name_api = home_team["name"]
    away_name_api = away_team["name"]

    # Fetch recent form and h2h concurrently
    home_matches, away_matches, h2h = await _parallel_fetch(home_id, away_id)

    home_form = _form_score(home_matches, home_id)
    away_form = _form_score(away_matches, away_id)
    h2h_home = _h2h_edge(h2h, home_id)

    # Home advantage weight: 0.1
    home_advantage = 0.1

    # Weighted score
    home_score = home_form * 0.45 + h2h_home * 0.35 + home_advantage * 0.20
    away_score = away_form * 0.45 + (1 - h2h_home) * 0.35

    total = home_score + away_score
    if total == 0:
        home_win = away_win = 0.4
        draw = 0.2
    else:
        raw_home = home_score / total
        raw_away = away_score / total
        # Draw probability is higher when scores are close
        diff = abs(raw_home - raw_away)
        draw = max(0.10, 0.30 - diff * 0.5)
        remain = 1 - draw
        home_win = raw_home * remain
        away_win = raw_away * remain

    # Form label
    def form_label(score: float) -> str:
        if score >= 0.75:
            return "🔥 ကောင်း"
        if score >= 0.5:
            return "👍 သင့်တော်"
        if score >= 0.25:
            return "😐 အလတ်"
        return "❄️ မကောင်း"

    # H2H note
    h2h_games = len([m for m in h2h if m["score"]["fullTime"]["home"] is not None])
    h2h_note = f"မှတ်တမ်း {h2h_games} ပွဲ" if h2h_games else "H2H မှတ်တမ်း မရှိ"

    # Verdict
    if home_win > away_win + 0.10:
        verdict = f"🏠 *{home_name_api}* နိုင်ဖွယ်ရှိ"
    elif away_win > home_win + 0.10:
        verdict = f"✈️ *{away_name_api}* နိုင်ဖွယ်ရှိ"
    else:
        verdict = "🤝 ပွဲမဆုံးဖြတ်နိုင် (သရေဖြစ်နိုင်)"

    return {
        "home": home_name_api,
        "away": away_name_api,
        "home_win_pct": round(home_win * 100, 1),
        "draw_pct": round(draw * 100, 1),
        "away_win_pct": round(away_win * 100, 1),
        "home_form": form_label(home_form),
        "away_form": form_label(away_form),
        "h2h_note": h2h_note,
        "verdict": verdict,
    }


async def _parallel_fetch(home_id: int, away_id: int):
    import asyncio
    results = await asyncio.gather(
        _team_recent_form(home_id),
        _team_recent_form(away_id),
        _head_to_head(home_id, away_id),
        return_exceptions=True,
    )
    home_m = results[0] if not isinstance(results[0], Exception) else []
    away_m = results[1] if not isinstance(results[1], Exception) else []
    h2h = results[2] if not isinstance(results[2], Exception) else []
    return home_m, away_m, h2h


def format_football_prediction(pred: dict) -> str:
    if "error" in pred:
        return f"❌ {pred['error']}"

    home = pred["home"]
    away = pred["away"]
    hw = pred["home_win_pct"]
    dw = pred["draw_pct"]
    aw = pred["away_win_pct"]

    # Visual bar
    def bar(pct: float, width: int = 10) -> str:
        filled = round(pct / 100 * width)
        return "█" * filled + "░" * (width - filled)

    lines = [
        f"⚽ *{home}* vs *{away}*",
        f"\n📊 *ခန့်မှန်းကိန်းဂဏန်း*",
        f"🏠 {home[:15]:<15} {hw:5.1f}%  {bar(hw)}",
        f"🤝 သရေ{'':13} {dw:5.1f}%  {bar(dw)}",
        f"✈️ {away[:15]:<15} {aw:5.1f}%  {bar(aw)}",
        f"\n📈 *ပုံစံ (Form)*",
        f"  🏠 {home}: {pred['home_form']}",
        f"  ✈️ {away}: {pred['away_form']}",
        f"  🔄 H2H: {pred['h2h_note']}",
        f"\n🎯 *ကျွန်ုပ်၏ ခန့်မှန်းချက်*",
        f"  {pred['verdict']}",
        f"\n⚠️ _ဤသည် statistical estimate မျှသာဖြစ်သည်။_",
        f"_ကြေးငွေ လောင်းကြပ်ခြင်းမပြုရန် တိုက်တွန်းသည်။_",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Lottery prediction (hot/cold analysis)
# ──────────────────────────────────────────────

# Historical data store — admin feeds past results
# { "thai_1st": [...], "thai_2digit": [...], "thai_3front": [...],
#   "thai_3back": [...], "laos_4digit": [...] }
LOTTERY_HISTORY: dict[str, list[str]] = {
    "thai_1st": [],
    "thai_2digit": [],
    "thai_3front": [],
    "thai_3back": [],
    "laos_4digit": [],
}


def add_history(key: str, numbers: list[str]) -> None:
    if key in LOTTERY_HISTORY:
        LOTTERY_HISTORY[key].extend(numbers)
        # Keep last 100 entries per key
        LOTTERY_HISTORY[key] = LOTTERY_HISTORY[key][-100:]


def _hot_cold(numbers: list[str], top_n: int = 5) -> tuple[list, list]:
    """Return (hot_numbers, cold_numbers) from a list."""
    if not numbers:
        return [], []
    c = Counter(numbers)
    hot = [n for n, _ in c.most_common(top_n)]
    cold = [n for n, _ in c.most_common()[:-top_n - 1:-1]]
    return hot, cold


def _digit_frequency(numbers: list[str]) -> dict[str, int]:
    """Count per-digit (0-9) frequency across all numbers."""
    freq: dict[str, int] = {str(d): 0 for d in range(10)}
    for num in numbers:
        for ch in num:
            if ch.isdigit():
                freq[ch] += 1
    return freq


def predict_lottery() -> str:
    lines = ["🔮 *ထီ ခန့်မှန်းချက် (Statistical)*\n"]

    sections = [
        ("Thai 2-digit", "thai_2digit", 2),
        ("Thai 3-digit Front", "thai_3front", 3),
        ("Thai 3-digit Back", "thai_3back", 3),
        ("Laos 4-digit", "laos_4digit", 4),
    ]

    has_data = False
    for label, key, digits in sections:
        history = LOTTERY_HISTORY.get(key, [])
        if not history:
            lines.append(f"📌 *{label}*: မှတ်တမ်းမရှိသေး")
            continue
        has_data = True
        hot, cold = _hot_cold(history)
        freq = _digit_frequency(history)
        hot_digits = sorted(freq.items(), key=lambda x: -x[1])[:3]
        cold_digits = sorted(freq.items(), key=lambda x: x[1])[:3]

        # Generate suggestion based on hot digits
        suggestion = _generate_suggestion(hot_digits, digits)

        lines.append(f"🎯 *{label}*")
        lines.append(f"  🔥 မကြာမကြာ ပေါ်သော: `{'`, `'.join(hot[:3])}`")
        lines.append(f"  ❄️ ကြာကြာ မပေါ်သော: `{'`, `'.join(cold[:3])}`")
        lines.append(f"  💡 အကြံပြု: `{suggestion}`")
        lines.append(f"  📊 မှတ်တမ်း: {len(history)} ခု")
        lines.append("")

    if not has_data:
        lines.append(
            "⚠️ မှတ်တမ်းမရှိသေးပါ။\n"
            "Admin မှ `/addhistory` ဖြင့် past results ထည့်ပေးပါ"
        )

    lines.append("⚠️ _ဤသည် frequency analysis မျှသာဖြစ်သည်_")
    lines.append("_ထီပေါက်ကြောင်း အာမခံချက်မရှိပါ_")
    return "\n".join(lines)


def _generate_suggestion(hot_digits: list, length: int) -> str:
    """Build a suggested number from hot digits."""
    import random
    pool = [d for d, _ in hot_digits] * 3
    pool += [str(random.randint(0, 9)) for _ in range(length)]
    random.shuffle(pool)
    return "".join(pool[:length])


def lottery_stats() -> str:
    """Show statistics summary of all lottery history."""
    lines = ["📊 *ထီ မှတ်တမ်း Statistics*\n"]
    for key, history in LOTTERY_HISTORY.items():
        label = key.replace("_", " ").title()
        if not history:
            lines.append(f"📌 {label}: မှတ်တမ်းမရှိ")
            continue
        c = Counter(history)
        top3 = c.most_common(3)
        lines.append(f"🎯 *{label}* ({len(history)} ခု)")
        lines.append(f"  Top: " + " | ".join(f"`{n}` x{cnt}" for n, cnt in top3))
    return "\n".join(lines)
