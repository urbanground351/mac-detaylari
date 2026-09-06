"""Flashscore weekly matches and preview summary scraper.

Fetches weekly matches for configured Turkish leagues and extracts
only the editorial preview/summary text for each match.
Does NOT extract odds, injured players, statistics, venue, etc.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config.json")
CONFIG: dict[str, Any] = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"


def clean(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def is_turkey_competition(competition: str | None, config: dict[str, Any]) -> bool:
    if not competition:
        return False
    c = competition.casefold()
    return any(x.casefold() in c for x in config.get("allowed_competitions", []))



def fetch_weekly_fixtures(
    fixture_url: str,
    days_ahead: int = 7,
    round_filter: str | None = None,
    session: requests.Session | None = None,
    timeout: int = 30
) -> list[dict[str, Any]]:
    """Fetch fixtures from Flashscore league fixtures URL and filter to weekly window or round."""
    s = session or requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://www.flashscore.com/"})
    r = s.get(fixture_url, timeout=timeout)
    r.raise_for_status()

    m = re.search(r"initialFeeds\[['\"]fixtures['\"]\]\s*=\s*\{\s*data:\s*`([^`]+)`", r.text)
    if not m:
        m = re.search(r"initialFeeds\[['\"]summary-fixtures['\"]\]\s*=\s*\{\s*data:\s*`([^`]+)`", r.text)
    if not m:
        return []

    records = m.group(1).split("~")
    matches = []

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=1)
    week_end = now + timedelta(days=days_ahead)

    current_tournament = "Super Lig"
    for rec in records:
        if rec.startswith("ZA") or "\xacZA" in rec:
            f = dict(re.findall(r"([A-Z0-9_]+)[\xac\xf7\ufffd]([^\xac\xf7\ufffd~]*)", rec))
            if "ZA" in f:
                current_tournament = f.get("ZA", current_tournament)

        if rec.startswith("AA") or "\xacAA" in rec or "¬AA" in rec:
            f = dict(re.findall(r"([A-Z0-9_]+)[\xac\xf7\ufffd]([^\xac\xf7\ufffd~]*)", rec))
            mid = f.get("AA")
            if not mid:
                continue
            ts = int(f.get("AD", 0))
            dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            round_name = f.get("ER")

            include = False
            if round_filter and round_filter.lower() != "current":
                if round_name and round_filter.lower() in round_name.lower():
                    include = True
            elif dt and (week_start <= dt <= week_end):
                include = True

            if include:
                wu = f.get("WU") or "home"
                wv = f.get("WV") or "away"
                px = f.get("PX") or ""
                py = f.get("PY") or ""
                match_url = f"https://www.flashscore.com/match/football/{wu}-{px}/{wv}-{py}/?mid={mid}"
                matches.append({
                    "match_id": mid,
                    "tournament_name": current_tournament,
                    "round": round_name,
                    "datetime_utc": dt.isoformat() if dt else None,
                    "home_team": f.get("AE"),
                    "away_team": f.get("AF"),
                    "home_slug": wu,
                    "away_slug": wv,
                    "home_id": px,
                    "away_id": py,
                    "state_code": f.get("AB"),
                    "url": match_url
                })

    if round_filter and round_filter.lower() == "current" and matches:
        first_round = matches[0].get("round")
        matches = [match_item for match_item in matches if match_item.get("round") == first_round]

    return matches


def extract_fluent_summary(soup: BeautifulSoup) -> str | None:
    """Extract clean, fluent, multi-paragraph editorial preview/summary text."""
    preview_el = soup.select_one("[class*=preview_preview]") or soup.select_one("[class*=preview]")
    if not preview_el:
        return None

    paragraphs = []
    for child in preview_el.find_all(["p", "div", "h3", "h4"]):
        if not child.find(["p", "div"]):
            t = child.get_text(" ", strip=True)
            t = re.sub(r"\s+([.,;:!?])", r"\1", t)
            if t and len(t) > 2 and t not in paragraphs:
                if t.lower() not in (
                    "flashscore preview",
                    "show full preview",
                    "this content was generated using ai.",
                    "show more",
                    "show less",
                    "advertisement"
                ):
                    paragraphs.append(t)

    if not paragraphs:
        t = preview_el.get_text(" ", strip=True)
        return clean(t) if len(t) > 20 else None

    return "\n\n".join(paragraphs)


def extract_match_summary(
    mid: str,
    meta: dict[str, Any],
    page,
    timeout: int = 20
) -> dict[str, Any]:
    """Load match page and extract only the match identification and summary text."""
    match_url = meta.get("url") or f"https://www.flashscore.com/match/{mid}/"

    home_name = meta.get("home_team")
    away_name = meta.get("away_team")
    tournament_name = meta.get("tournament_name") or "Super Lig"
    round_name = meta.get("round")
    dt_str = meta.get("datetime_utc")

    summary_text = None

    if page:
        try:
            page.goto(match_url, wait_until="domcontentloaded", timeout=timeout * 1000)
            page.wait_for_timeout(1800)
            html = page.content()
            soup = BeautifulSoup(html, "lxml")

            if not home_name:
                h_el = soup.select_one(".duelParticipant__home, [class*=participantHome]")
                if h_el: home_name = clean(h_el.get_text(strip=True))
            if not away_name:
                a_el = soup.select_one(".duelParticipant__away, [class*=participantAway]")
                if a_el: away_name = clean(a_el.get_text(strip=True))

            b_el = soup.select_one("[class*=breadcrumb]")
            if b_el:
                b_text = b_el.get_text(" | ", strip=True)
                if " - " in b_text:
                    parts = b_text.split(" - ")
                    if not round_name and len(parts) > 1:
                        round_name = clean(parts[-1].split("|")[0])
                    t_part = parts[0].split("|")[-1].strip()
                    if t_part:
                        tournament_name = t_part

            if not dt_str:
                t_el = soup.select_one(".duelParticipant__startTime")
                if t_el:
                    raw_time = clean(t_el.get_text(strip=True))
                    try:
                        parsed_dt = datetime.strptime(raw_time, "%d.%m.%Y %H:%M").replace(tzinfo=timezone.utc)
                        dt_str = parsed_dt.isoformat()
                    except Exception:
                        pass

            summary_text = extract_fluent_summary(soup)

        except Exception as e:
            pass

    dt_local = None
    if dt_str:
        try:
            dt_obj = datetime.fromisoformat(dt_str)
            dt_local = dt_obj.astimezone().strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    return {
        "match_id": mid,
        "url": match_url,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "tournament": tournament_name,
        "round": round_name,
        "match_time": dt_local or dt_str,
        "home_team": home_name,
        "away_team": away_name,
        "summary": summary_text
    }


def save_matches_to_file(matches: list[dict[str, Any]], out_path: Path) -> None:
    """Save/update matches in target JSON file without duplicating existing entries."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if out_path.exists():
        try:
            loaded = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
        except json.JSONDecodeError:
            existing = []

    match_map = {m.get("match_id") or m.get("url"): m for m in existing}
    for m in matches:
        key = m.get("match_id") or m.get("url")
        match_map[key] = m

    updated_list = list(match_map.values())
    out_path.write_text(json.dumps(updated_list, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Flashscore haftalık maçların sadece summary/preview yazılarını çeken scraper")
    parser.add_argument("url", nargs="?", default=None, help="Belirli bir maç URL'si veya fikstür URL'si (boşsa config'deki haftalık ligler taranır)")
    parser.add_argument("--days", type=int, default=int(CONFIG.get("days_ahead", 7)), help="Kaç günlük maçların çekileceği (varsayılan: 7)")
    parser.add_argument("--round", default=None, help="Spesifik raunt filtresi (ör: 'current' veya 'Round 4')")
    parser.add_argument("--league", default=None, help="Belirli bir lig slug'ı (ör: 'super-lig', '1-lig')")
    parser.add_argument("--out", default="data/matches.json", help="Çıktı JSON dosya yolu")
    parser.add_argument("--only-with-summary", action="store_true", help="Yalnızca summary metni bulunan maçları kaydet")
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Referer": "https://www.flashscore.com/"})
    timeout = int(CONFIG.get("timeout_seconds", 30))
    delay = float(CONFIG.get("request_delay_seconds", 0.5))
    output_path = Path(args.out)

    target_fixtures: list[str] = []
    single_match_id: str | None = None
    single_match_url: str | None = None

    if args.url:
        if "/match/" in args.url:
            single_match_url = args.url
            mid_match = re.search(r"mid=([A-Za-z0-9]+)", args.url) or re.search(r"/match/([A-Za-z0-9]+)/?", args.url)
            single_match_id = mid_match.group(1) if mid_match else None
        else:
            target_fixtures.append(args.url)
    elif args.league:
        target_fixtures.append(f"https://www.flashscore.com/football/turkey/{args.league}/fixtures/")
    else:
        target_fixtures = CONFIG.get("fixture_urls", [
            "https://www.flashscore.com/football/turkey/super-lig/fixtures/",
            "https://www.flashscore.com/football/turkey/1-lig/fixtures/"
        ])

    print("==================================================")
    print("      Flashscore Haftalık Maç Summary Kazıyıcı")
    print("==================================================")

    from playwright.sync_api import sync_playwright
    playwright_context = sync_playwright().start()
    browser = playwright_context.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA, locale="en-US")

    try:
        # Case A: Single match
        if single_match_id:
            print(f"[*] Tek maç çekiliyor: ID={single_match_id} URL={single_match_url}")
            meta = {"match_id": single_match_id, "url": single_match_url}
            res = extract_match_summary(single_match_id, meta, page=page, timeout=timeout)
            save_matches_to_file([res], output_path)
            print(f"[OK] Maç kaydedildi: {output_path}")
            print(json.dumps(res, ensure_ascii=False, indent=2))
            return 0

        # Case B: Weekly fixtures
        all_matches_to_scrape: list[dict[str, Any]] = []
        for fix_url in target_fixtures:
            print(f"[*] Fikstür taranıyor: {fix_url} (Gün penceresi: {args.days} gün)...")
            try:
                found = fetch_weekly_fixtures(fix_url, days_ahead=args.days, round_filter=args.round, session=session, timeout=timeout)
                print(f"    -> Bulunan haftalık maç sayısı: {len(found)}")
                all_matches_to_scrape.extend(found)
            except Exception as exc:
                print(f"[!] Fikstür alınırken hata ({fix_url}): {exc}")

        seen_ids = set()
        unique_matches = []
        for m in all_matches_to_scrape:
            if m["match_id"] not in seen_ids:
                seen_ids.add(m["match_id"])
                unique_matches.append(m)

        total = len(unique_matches)
        print(f"\n[+] Toplam işlenecek haftalık maç sayısı: {total}")
        if total == 0:
            print("[i] Belirtilen tarih aralığında maç bulunamadı.")
            return 0

        scraped_results = []
        for i, m in enumerate(unique_matches, 1):
            mid = m["match_id"]
            home = m.get("home_team", "Ev")
            away = m.get("away_team", "Dep")
            rnd = m.get("round", "")
            print(f"[{i}/{total}] Çekiliyor: {home} vs {away} ({rnd})...", end="", flush=True)
            try:
                match_res = extract_match_summary(mid, m, page=page, timeout=timeout)
                if args.only_with_summary and not match_res.get("summary"):
                    print(" [Summary yok, atlandı]")
                    continue
                scraped_results.append(match_res)
                save_matches_to_file([match_res], output_path)
                status_note = "Tamamlandı (Summary bulundu)" if match_res.get("summary") else "Tamamlandı (Henüz summary yok)"
                print(f" {status_note}.")
            except Exception as e:
                print(f" HATA: {e}")
            if delay > 0 and i < total:
                time.sleep(delay)

        print(f"\n[OK] Toplam {len(scraped_results)} maç başarıyla '{output_path}' dosyasına kaydedildi!")
        return 0

    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        if playwright_context:
            try: playwright_context.stop()
            except Exception: pass


if __name__ == "__main__":
    raise SystemExit(main())
