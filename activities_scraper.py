import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class StratfordPadelActivityScraper:
    def __init__(self):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/ActBooking/Agenda.aspx"
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        self.config = self.default_config()

    @staticmethod
    def default_config() -> Dict:
        return {
            "activity_search": {
                "activity_name": ["Train and Play Orange", "Private Class"],
                "days_to_search": 10,
            },
            "time_filters": {
                "weekdays": {
                    "monday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "tuesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "wednesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "thursday": {"enabled": True, "start_hour": 11, "end_hour": 23},
                    "friday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                },
                "weekends": {
                    "saturday": {"enabled": True, "start_hour": 8, "end_hour": 22},
                    "sunday": {"enabled": True, "start_hour": 8, "end_hour": 22},
                },
            },
        }

    # -----------------------
    # Core scraping
    # -----------------------

    def get_date_range(self) -> List[str]:
        today = datetime.now()
        return [
            (today + timedelta(days=i)).strftime("%d-%m-%Y")
            for i in range(self.config["activity_search"]["days_to_search"])
        ]

    def fetch_booking_page(self, date: str) -> Optional[str]:
        try:
            r = requests.get(
                self.base_url,
                params={"d": date},
                headers=self.headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.text
        except requests.RequestException:
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
                info["sign_up_link"] = link
                sessions.append(info)

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
        except Exception:
            return None

    def extract_link(self, container) -> Optional[str]:
        link = container.find("a", class_="boton", string="Sign up")
        if not link:
            return None

        href = link.get("href")
        if href and href.startswith("Info.aspx"):
            return f"https://stratfordpadelclub.matchpoint.com.es/ActBooking/{href}"

        return None

    # -----------------------
    # Filtering & sorting
    # -----------------------

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

        return sorted(filtered, key=lambda x: datetime.strptime(x["date"], "%d/%m/%Y"))

    def search_for_sessions(self) -> List[Dict]:
        all_sessions = []

        for date in self.get_date_range():
            html = self.fetch_booking_page(date)
            if html:
                all_sessions.extend(self.parse_activity_sessions(html))
            time.sleep(0.2)

        return self.filter_sessions(all_sessions)

    # -----------------------
    # Telegram helpers
    # -----------------------

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
            lines.extend(
                [
                    f"*{s['type']}*",
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
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )


def main():
    scraper = StratfordPadelActivityScraper()
    sessions = scraper.search_for_sessions()

    message = scraper.format_sessions_for_telegram(sessions)

    import os

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if bot_token and chat_id:
        scraper.send_to_telegram(message, bot_token, chat_id)
    else:
        print(message)


if __name__ == "__main__":
    main()
