import json
import argparse
import re
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional


def _configure_stdout_encoding() -> None:
    """Avoid UnicodeEncodeError on Windows consoles and when redirecting output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


_configure_stdout_encoding()


import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()


class StratfordPadelMatchScraper:
    def __init__(self, config_path: str = "config.json", verbose: bool = True):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/Matches/Search.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        }

        self.verbose = verbose
        self.config = self.load_config(config_path)
        self._log(
            f"Scraper initialized. Searching for matches with level range "
            f"{self.config['match_search']['search_settings']['level_range']} over "
            f"{self.config['match_search']['search_settings']['weeks_to_search']} weeks."
        )

    # =========================
    # Logging
    # =========================
    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    # =========================
    # Config
    # =========================
    def load_config(self, path: str = "match_config.json") -> Dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            raise RuntimeError(f"Config file not found: {path}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in config file: {e}")

    # =========================
    # Telegram
    # =========================
    @staticmethod
    def send_to_telegram(message: str, bot_token: str, chat_id: str):
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            response = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if response.status_code != 200:
                print("⚠️ Failed to send message to Telegram: " + response.text)
        except requests.RequestException as e:
            print(f"⚠️ Failed to send message to Telegram: {e}")

    @staticmethod
    def format_matches_for_telegram(matches: List[Dict]) -> str:
        """Format a list of matches as a Telegram-friendly Markdown message"""
        if not matches:
            return "❌ No matches found."

        lines = [
            f"🎾 *Stratford Padel – Available Matches ({len(matches)})*",
            f"_Updated: {datetime.now().strftime('%d/%m %H:%M')}_",
            "",
        ]

        for m in matches:
            lines.extend(
                [
                    f"*{m['type']}*",
                    f"📅 {m['date']} ({m['day_of_week']})",
                    f"⏰ {m['time']}",
                    f"🎯 Level: {m['level_range']}",
                    f"🔗 [Join]({m['link']})",
                    "",
                ]
            )

        return "\n".join(lines)

    # =========================
    # Date handling
    # =========================
    def get_week_ranges(self) -> List[tuple]:
        current_date = datetime.now()
        week_ranges = []
        weeks_to_search = self.config["match_search"]["search_settings"]["weeks_to_search"]
        self._log(f"Generating week ranges for {weeks_to_search} weeks")

        for week in range(weeks_to_search):
            start = current_date + timedelta(days=week * 7)
            end = start + timedelta(days=6)
            week_ranges.append((start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")))
            self._log(f"Week {week+1}: {start.strftime('%d/%m/%Y')} -> {end.strftime('%d/%m/%Y')}")

        return week_ranges

    # =========================
    # Fetching pages
    # =========================
    def fetch_matches_page(self, start_date: str, end_date: str) -> Optional[str]:
        """Fetch HTML page for matches in a date range"""
        try:
            level_min = self.config["match_search"]["search_settings"]["level_range"]["min"]
            level_max = self.config["match_search"]["search_settings"]["level_range"]["max"]

            params = self.config["match_search"]["url_parameters"].copy()
            params.update(
                {
                    "idNivelMinimo": f"{level_min:.2f}".replace(".", ","),
                    "idNivelMaximo": f"{level_max:.2f}".replace(".", ","),
                    "fechaDesde": start_date,
                    "fechaHasta": end_date,
                    "horaDesde": "00:00",
                    "horaHasta": "23:59",
                }
            )

            self._log(f"Fetching matches page for {start_date} to {end_date} with params {params}")
            print(self.base_url)
            print(params)
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            self._log(f"Error fetching page: {e}")
            return None

    # =========================
    # Parsing matches
    # =========================
    @staticmethod
    def _extract_match_link(container) -> str:
        """Extract match URL from container onclick or legacy enter link."""
        onclick = container.get("onclick", "")
        if onclick:
            match = re.search(
                r"window\.location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]",
                onclick,
            )
            if match:
                path = match.group(1)
                if path.startswith("/"):
                    return f"https://stratfordpadelclub.matchpoint.com.es{path}"
                if path.startswith("http"):
                    return path
                return f"https://stratfordpadelclub.matchpoint.com.es/Matches/{path}"

        enter_link = container.find("a", class_="boton")
        if enter_link:
            href = enter_link.get("href", "")
            if href.startswith("Match.aspx"):
                return f"https://stratfordpadelclub.matchpoint.com.es/Matches/{href}"
            if href.startswith("/Matches/"):
                return f"https://stratfordpadelclub.matchpoint.com.es{href}"
        return ""

    @staticmethod
    def _parse_calendar(container) -> tuple:
        """Parse month/day/year from divCalendar; returns (day_number, day_name, date_str)."""
        cal = container.find("div", class_="divCalendar")
        if not cal:
            return None, None, None

        spans = [s.get_text(strip=True) for s in cal.find_all("span") if s.get_text(strip=True)]
        if len(spans) < 3:
            return None, None, None

        month_str, day_str, year_str = spans[0], spans[1], spans[2]
        try:
            match_date = datetime.strptime(f"{day_str} {month_str} {year_str}", "%d %b %Y")
            return (
                str(match_date.day),
                match_date.strftime("%A"),
                match_date.strftime("%d/%m/%Y"),
            )
        except ValueError:
            return day_str, None, None

    def parse_matches(self, html_content: str) -> List[Dict]:
        """Extract match info from HTML"""
        soup = BeautifulSoup(html_content, "html.parser")
        matches = []

        containers = soup.find_all(
            "div",
            class_=lambda c: c
            and ("contenedorContenidoPartidas3" in c or "contenedorContenidoPartidas" in c),
        )
        self._log(f"Found {len(containers)} match containers in HTML")

        for c in containers:
            day_span = c.find("span", id=lambda x: x and "LabelDiaSemana" in x)
            day_number_span = c.find("span", id=lambda x: x and "LabelFechaInicio" in x)
            time_span = c.find("span", id=lambda x: x and "LabelHoraInicio" in x)
            level_span = c.find("span", id=lambda x: x and "LabelNivelValor" in x)
            sex_span = c.find("span", id=lambda x: x and "LabelSexoValor" in x)
            sport_span = c.find("span", id=lambda x: x and "LabelDeporte" in x)

            cal_day, cal_weekday, cal_date = self._parse_calendar(c)

            if not time_span or not level_span:
                continue

            day_name = day_span.get_text(strip=True) if day_span else cal_weekday
            day_number = day_number_span.get_text(strip=True) if day_number_span else cal_day
            if not day_number:
                continue

            level_parts = level_span.get_text(strip=True).split(" - ")
            if len(level_parts) != 2:
                continue

            try:
                min_level = float(level_parts[0].replace(",", "."))
                max_level = float(level_parts[1].replace(",", "."))
            except ValueError:
                continue

            cfg_min = self.config["match_search"]["search_settings"]["level_range"]["min"]
            cfg_max = self.config["match_search"]["search_settings"]["level_range"]["max"]

            if not (min_level < cfg_max and max_level > cfg_min):
                continue

            link = self._extract_match_link(c).replace("Match.aspx", "Share.aspx")

            sex = sex_span.get_text(strip=True).lstrip("- ").strip() if sex_span else "Mixed"
            sport = sport_span.get_text(strip=True) if sport_span else "Padel"
            match_type = f"{sex} {sport} Match"

            match_data = {
                "day_name": day_name or "",
                "day_number": day_number,
                "time": time_span.get_text(strip=True),
                "level_min": level_parts[0],
                "level_max": level_parts[1],
                "level_range": f"{level_parts[0]} - {level_parts[1]}",
                "type": match_type,
                "link": link,
            }
            if cal_date:
                match_data["date"] = cal_date
                if day_name:
                    match_data["day_of_week"] = day_name
                elif cal_weekday:
                    match_data["day_of_week"] = cal_weekday
                try:
                    match_data["datetime_obj"] = datetime.strptime(cal_date, "%d/%m/%Y")
                except ValueError:
                    pass

            matches.append(match_data)

        self._log(f"Parsed {len(matches)} matches after filtering by level")
        return matches

    # =========================
    # Filtering
    # =========================
    def filter_matches_by_time(self, matches: List[Dict]) -> List[Dict]:
        filtered = []
        time_filters = self.config["time_filters"]

        for m in matches:
            day_name = m["day_name"].lower()
            hour = int(m["time"].split(":")[0])

            cfg = None
            if day_name in time_filters.get("weekdays", {}):
                cfg = time_filters["weekdays"][day_name]
            elif day_name in time_filters.get("weekends", {}):
                cfg = time_filters["weekends"][day_name]

            if cfg and cfg["enabled"] and cfg["start_hour"] <= hour <= cfg["end_hour"]:
                filtered.append(m)

        self._log(f"{len(filtered)} matches remain after time filtering")
        return filtered

    # =========================
    # Adding dates
    # =========================
    def add_date_info(
        self,
        matches: List[Dict],
        start_date_str: str,
    ) -> List[Dict]:
        """
        Adds correct calendar dates to matches.
        Handles date ranges that span into the next month.
        """
        start_date = datetime.strptime(start_date_str, "%d/%m/%Y")
        start_day = start_date.day

        for m in matches:
            if m.get("date") and m.get("datetime_obj"):
                if not m.get("day_of_week"):
                    m["day_of_week"] = m["datetime_obj"].strftime("%A")
                continue

            day = int(m["day_number"])

            # Base date: first day of queried month
            base_date = start_date.replace(day=1)

            # If day resets, move to next month
            if day < start_day:
                year = base_date.year + (base_date.month == 12)
                month = 1 if base_date.month == 12 else base_date.month + 1
                base_date = base_date.replace(year=year, month=month)

            match_date = base_date.replace(day=day)

            if m.get("day_name"):
                expected_weekday = self.get_weekday_number(m["day_name"])
                if match_date.weekday() != expected_weekday:
                    self._log(
                        f"⚠️ Weekday mismatch: {m['day_name']} "
                        f"but {match_date.strftime('%A')} for {match_date:%d/%m/%Y}"
                    )

            m.update(
                {
                    "date": match_date.strftime("%d/%m/%Y"),
                    "day_of_week": match_date.strftime("%A"),
                    "datetime_obj": match_date,
                }
            )

        return matches

    @staticmethod
    def get_weekday_number(day_name: str) -> int:
        weekdays = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }
        return weekdays.get(day_name, 0)

    @staticmethod
    def sort_matches_by_date(matches: List[Dict]) -> List[Dict]:
        return sorted(matches, key=lambda x: x["datetime_obj"])

    # =========================
    # Full search
    # =========================
    def search_matches(self) -> List[Dict]:
        self._log("Starting full match search...")
        all_matches: List[Dict] = []

        for start, end in self.get_week_ranges():
            html = self.fetch_matches_page(start, end)
            if not html:
                continue

            matches = self.parse_matches(html)
            matches = self.filter_matches_by_time(matches)
            matches = self.add_date_info(matches, start)

            all_matches.extend(matches)

        sorted_matches = self.sort_matches_by_date(all_matches)
        self._log(f"Search complete: {len(sorted_matches)} matches found")
        return sorted_matches


def main():
    import os

    _configure_stdout_encoding()

    parser = argparse.ArgumentParser(description="Scrape Stratford Padel matches.")
    parser.add_argument(
        "--send-to-telegram",
        action="store_true",
        help="If set, send Telegram message.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to config file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    # Initialize scraper
    scraper = StratfordPadelMatchScraper(config_path=args.config, verbose=args.verbose)

    # Run search
    matches = scraper.search_matches()

    # Print results nicely
    if not matches:
        print("❌ No matches found.")
        return

    print(f"🎾 Found {len(matches)} matches:\n")
    for m in matches:
        print(
            f"{m['type']}\n"
            f"📅 {m['date']} ({m['day_of_week']})\n"
            f"⏰ {m['time']}\n"
            f"🎯 Level: {m['level_range']}\n"
            f"🔗 Link: {m['link']}\n"
            "-----------------------"
        )

    if args.send_to_telegram:
        # Get Telegram token and chat id (from config or arg)
        telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not telegram_bot_token or not telegram_chat_id:
            print("❌ Telegram bot token and chat id must be provided (via args or config).")
            return

        message = scraper.format_matches_for_telegram(matches)
        StratfordPadelMatchScraper.send_to_telegram(message, telegram_bot_token, telegram_chat_id)
        print(f"✅ Sent Telegram message: {message}")


if __name__ == "__main__":
    main()
