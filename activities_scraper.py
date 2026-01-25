import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import typer
from bs4 import BeautifulSoup


class StratfordPadelActivityScraper:
    def __init__(self):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/ActBooking/Agenda.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        }
        self.config = self.default_config()

    @staticmethod
    def default_config() -> Dict:
        return {
            "activity_search": {
                "activity_name": ["Train and Play Orange", "Private Class"],
                "days_to_search": 7,
            },
            "time_filters": {
                "weekdays": {
                    "monday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "tuesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "wednesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "thursday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "friday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                },
                "weekends": {
                    "saturday": {"enabled": True, "start_hour": 8, "end_hour": 22},
                    "sunday": {"enabled": True, "start_hour": 8, "end_hour": 22},
                },
            },
        }

    def get_date_range(self) -> List[str]:
        today = datetime.now()
        return [
            (today + timedelta(days=i)).strftime("%d-%m-%Y")
            for i in range(self.config["activity_search"]["days_to_search"])
        ]

    def fetch_booking_page(self, date: str) -> Optional[str]:
        try:
            response = requests.get(self.base_url, params={"d": date}, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return None

    def parse_activity_sessions(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        sessions = []
        containers = soup.find_all("div", class_="contenedor2Columnas2")

        for c in containers:
            title_span = c.find("span", class_="textoTituloPubli2")
            if not title_span:
                continue
            activity_name = title_span.get_text(strip=True)
            if not any(name in activity_name for name in self.config["activity_search"]["activity_name"]):
                continue

            info = self.extract_session_info(c)
            if not info:
                continue

            link = self.extract_link(c)
            if not link:
                continue

            info["sign_up_link"] = link
            sessions.append(info)

        return sessions

    def extract_session_info(self, container) -> Optional[Dict]:
        try:
            dt_span = container.find("span", id=lambda x: x and "LabelHorarioValor" in x)
            status_span = container.find("span", id=lambda x: x and "LabelEstadoActividadValor" in x)
            court_span = container.find("span", id=lambda x: x and "LabelLugarValor" in x)
            instructor_span = container.find("span", id=lambda x: x and "LabelMonitorValor" in x)

            dt_text = dt_span.get_text(strip=True)
            dt_match = re.search(r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}-\d{2}:\d{2})", dt_text)
            if not dt_match:
                return None

            status = status_span.get_text(strip=True)
            vacancies = int(re.search(r"(\d+)", status).group(1)) if "vacancies available" in status else None

            return {
                "type": container.find("span", class_="textoTituloPubli2").get_text(strip=True),
                "date": dt_match.group(1),
                "time": dt_match.group(2),
                "status": status,
                "court": court_span.get_text(strip=True) if court_span else "",
                "instructor": instructor_span.get_text(strip=True) if instructor_span else "",
                "vacancies": vacancies,
            }
        except Exception:
            return None

    def extract_link(self, container) -> Optional[str]:
        try:
            link_tag = container.find("a", class_="boton", string="Sign up")
            if link_tag:
                href = link_tag.get("href")
                if href.startswith("Info.aspx"):
                    return f"https://stratfordpadelclub.matchpoint.com.es/ActBooking/{href}"
            return None
        except Exception:
            return None

    def add_day_of_week(self, sessions: List[Dict]) -> List[Dict]:
        for s in sessions:
            try:
                s["day_of_week"] = datetime.strptime(s["date"], "%d/%m/%Y").strftime("%A")
            except Exception:
                s["day_of_week"] = "Unknown"
        return sessions

    def filter_sessions_by_time(self, sessions: List[Dict]) -> List[Dict]:
        time_filters = self.config["time_filters"]
        filtered = []

        for s in sessions:
            day = s["day_of_week"]
            start_hour = int(s["time"].split("-")[0].split(":")[0])

            if day in ["Saturday", "Sunday"]:
                cfg = time_filters.get("weekends", {}).get(day.lower(), time_filters.get("weekends", {}))
            else:
                cfg = time_filters.get("weekdays", {}).get(day.lower(), {})

            if cfg.get("enabled", True) and cfg.get("start_hour", 0) <= start_hour <= cfg.get("end_hour", 23):
                filtered.append(s)

        return filtered

    def sort_sessions_by_date(self, sessions: List[Dict]) -> List[Dict]:
        return sorted(sessions, key=lambda x: datetime.strptime(x["date"], "%d/%m/%Y"))

    def search_for_sessions(self) -> List[Dict]:
        """Main method: fetch, parse, filter, sort"""
        all_sessions = []

        for date in self.get_date_range():
            html = self.fetch_booking_page(date)
            if not html:
                continue
            day_sessions = self.parse_activity_sessions(html)
            all_sessions.extend(day_sessions)
            time.sleep(0.1)

        all_sessions = self.add_day_of_week(all_sessions)
        available = [s for s in all_sessions if "Complete" not in s["status"]]
        filtered_sorted = self.sort_sessions_by_date(self.filter_sessions_by_time(available))

        # Return for Streamlit usage
        return filtered_sorted


# def main():
#     app = typer.Typer()

#     @app.callback(invoke_without_command=True)
#     def cli(
#         activity_names: str = typer.Option(None, help="Comma-separated activity names"),
#         days: int = typer.Option(None, help="Days to search"),
#         weekdays: str = typer.Option(None, help="Weekday time filter JSON"),
#         weekends: str = typer.Option(None, help="Weekend time filter JSON"),
#         verbose: bool = typer.Option(False, help="Verbose logging"),
#     ):
#         scraper = StratfordPadelActivityScraper()
#         if activity_names:
#             scraper.config["activity_search"]["activity_name"] = [
#                 name.strip() for name in activity_names.split(",")
#             ]
#         if days:
#             scraper.config["activity_search"]["days_to_search"] = days
#         if weekdays:
#             scraper.config["time_filters"]["weekdays"] = json.loads(weekdays)
#         if weekends:
#             scraper.config["time_filters"]["weekends"] = json.loads(weekends)
#         if verbose:
#             scraper.config["debug_settings"]["verbose_logging"] = True

#         scraper.search_for_sessions()

#     app()


# if __name__ == "__main__":
#     main()
