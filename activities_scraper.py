import json
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class StratfordPadelActivityScraper:
    def __init__(self, config_path: str = "config.json", verbose: bool = True):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/ActBooking/Agenda.aspx"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        self.verbose = verbose
        self.config = self.load_config(config_path)
        self._log(
            f"Scraper initialized. Searching for activities: {self.config['activity_search']['activity_name']}"
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
    @staticmethod
    def load_config(path: str = "config.json") -> Dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise RuntimeError(f"Config file not found: {path}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in config file: {e}")

    # =========================
    # Core scraping
    # =========================
    def get_date_range(self) -> List[str]:
        today = datetime.now()
        days = self.config["activity_search"]["days_to_search"]
        self._log(f"Generating date range for next {days} days")
        return [(today + timedelta(days=i)).strftime("%d-%m-%Y") for i in range(days)]

    def fetch_activity_levels(self, info_url: str) -> Optional[str]:
        try:
            self._log(f"Fetching activity details: {info_url}")
            r = requests.get(info_url, headers=self.headers, timeout=10)
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")

            levels_span = soup.find("span", id=lambda x: x and "LabelNiveles" in x)
            if levels_span:
                return levels_span.get_text(strip=True)

            return None
        except Exception as e:
            self._log(f"Failed to fetch levels from {info_url}: {e}")
            return None

    def fetch_booking_page(self, date: str) -> Optional[str]:
        try:
            self._log(f"Fetching booking page for {date}")
            r = requests.get(
                self.base_url,
                params={"d": date},
                headers=self.headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            self._log(f"Error fetching {date}: {e}")
            return None

    def parse_activity_sessions(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        sessions = []

        for c in soup.find_all("div", class_="contenedor2Columnas2"):
            title = c.find("span", class_="textoTituloPubli2")
            if not title:
                continue

            activity_name = title.get_text(strip=True)
            if not any(name in activity_name for name in self.config["activity_search"]["activity_name"]):
                continue

            info = self.extract_session_info(c)
            link = self.extract_link(c)

            if info and link:
                info_url = link  # Info.aspx
                share_url = link.replace("Info.aspx", "Share.aspx")

                # 👇 Only fetch levels for specific activities
                if any(x in info["type"].lower() for x in ["train and play", "matchplay", "academy"]):
                    levels = self.fetch_activity_levels(info_url)
                    info["levels"] = levels
                else:
                    info["levels"] = None

                info["sign_up_link"] = share_url
                sessions.append(info)

                self._log(
                    f"Found session: {info['type']} on {info['date']} at {info['time']} "
                    f"(levels={info['levels']})"
                )

        return sessions

    def extract_session_info(self, container) -> Optional[Dict]:
        try:
            dt_span = container.find("span", id=lambda x: x and "LabelHorarioValor" in x)
            status_span = container.find("span", id=lambda x: x and "LabelEstadoActividadValor" in x)
            instructor_span = container.find("span", id=lambda x: x and "LabelMonitorValor" in x)

            match = re.search(
                r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}-\d{2}:\d{2})",
                dt_span.get_text(strip=True),
            )
            if not match:
                return None

            status = status_span.get_text(strip=True)
            vacancies = int(re.search(r"(\d+)", status).group(1)) if "vacancies available" in status else None

            return {
                "type": container.find("span", class_="textoTituloPubli2").get_text(strip=True),
                "date": match.group(1),
                "time": match.group(2),
                "day_of_week": datetime.strptime(match.group(1), "%d/%m/%Y").strftime("%A"),
                "instructor": instructor_span.get_text(strip=True) if instructor_span else "",
                "status": status,
                "vacancies": vacancies,
            }
        except Exception as e:
            self._log(f"Failed to extract session info: {e}")
            return None

    def extract_link(self, container) -> Optional[str]:
        link = container.find("a", class_="boton", string="Sign up")
        if link:
            href = link.get("href")
            if href and href.startswith("Info.aspx"):
                return f"https://stratfordpadelclub.matchpoint.com.es/ActBooking/{href}"
        return None

    # =========================
    # Filtering & sorting
    # =========================
    def filter_sessions(self, sessions: List[Dict]) -> List[Dict]:
        filtered = []
        for s in sessions:
            if "Complete" in s["status"]:
                continue

            start_hour = int(s["time"].split(":")[0])
            day = s["day_of_week"].lower()

            cfg = (
                self.config["time_filters"]["weekends"].get(day)
                if day in ["saturday", "sunday"]
                else self.config["time_filters"]["weekdays"].get(day, {})
            )

            if cfg.get("enabled") and cfg["start_hour"] <= start_hour <= cfg["end_hour"]:
                filtered.append(s)
                self._log(f"Session {s['type']} on {s['date']} at {s['time']} passed time filter")

        return sorted(filtered, key=lambda x: datetime.strptime(x["date"], "%d/%m/%Y"))

    def search_for_sessions(self) -> List[Dict]:
        all_sessions = []

        for date in self.get_date_range():
            html = self.fetch_booking_page(date)
            if html:
                day_sessions = self.parse_activity_sessions(html)
                all_sessions.extend(day_sessions)
                self._log(f"Total sessions found so far: {len(all_sessions)}")
            time.sleep(0.2)

        self._log(f"Finished fetching sessions. Filtering now...")
        return self.filter_sessions(all_sessions)

    # =========================
    # Telegram helpers
    # =========================
    @staticmethod
    def format_sessions_for_telegram(sessions: List[Dict]) -> str:
        if not sessions:
            return "❌ No matching padel activities found."

        lines = [
            "🎾 *Stratford Padel – Available Activities*",
            f"_Updated: {datetime.now().strftime('%d/%m %H:%M')}_",
            "",
        ]

        for s in sessions:
            name = s["type"]
            if s.get("levels"):
                name = f"{name} ({s['levels']})"
            lines.extend(
                [
                    f"*{name}*",
                    f"📅 {s['date']} ({s['day_of_week']})",
                    f"⏰ {s['time']}",
                    f"👤 {s['instructor']}",
                    f"🪑 Vacancies: {s['vacancies'] if s['vacancies'] is not None else '—'}",
                    f"👉 [Sign up]({s['sign_up_link']})",
                    "",
                ]
            )

        return "\n".join(lines)

    @staticmethod
    def send_to_telegram(message: str, bot_token: str, chat_id: str):
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )

        print("Telegram response:", resp.status_code, resp.text)


def main():
    import os

    scraper = StratfordPadelActivityScraper(verbose=True)
    sessions = scraper.search_for_sessions()
    message = scraper.format_sessions_for_telegram(sessions)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        scraper.send_to_telegram(message, bot_token, chat_id)
    else:
        print(message)


if __name__ == "__main__":
    main()
