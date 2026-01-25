import json
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
import typer
from bs4 import BeautifulSoup

print("Search Initiated")


class StratfordPadelActivityScraper:
    def __init__(self, config_file: str = "config.json"):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/ActBooking/Agenda.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Load configuration
        self.config = self.load_config(config_file)
        print("Activity scraper initialized successfully!")

        # Parse activity names from config
        activity_name_config = self.config.get("activity_search", {}).get(
            "activity_name", "Train and Play Orange"
        )
        self.activity_names = (
            activity_name_config if isinstance(activity_name_config, list) else [activity_name_config]
        )

        # Days to search
        self.days_to_search = self.config.get("activity_search", {}).get("days_to_search", 45)

        # Output files
        self.output_filename = self.config.get("activity_search", {}).get(
            "output_filename", "activity_sessions.txt"
        )
        self.all_sessions_filename = "all_activity_sessions.txt"

    def load_config(self, config_file: str) -> Dict:
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            print(f"Configuration loaded from {config_file}")
            return config
        except (FileNotFoundError, json.JSONDecodeError):
            print(f"Using default configuration")
            return self.default_config()

    def default_config(self) -> Dict:
        return {
            "activity_search": {
                "activity_name": ["Train and Play Orange"],
                "days_to_search": 45,
                "output_filename": "activity_sessions.txt",
            },
            "time_filters": {
                "weekdays": {
                    "monday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "tuesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "wednesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "thursday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "friday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                },
                "weekends": {"enabled": True, "start_hour": 0, "end_hour": 23},
            },
            "debug_settings": {"verbose_logging": True},
        }

    def get_date_range(self) -> List[str]:
        dates = []
        today = datetime.now()
        for i in range(self.days_to_search):
            dates.append((today + timedelta(days=i)).strftime("%d-%m-%Y"))
        return dates

    def fetch_booking_page(self, date: str) -> Optional[str]:
        try:
            response = requests.get(self.base_url, params={"d": date}, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching page for {date}: {e}")
            return None

    def parse_activity_sessions(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        sessions = []
        containers = soup.find_all("div", class_="contenedor2Columnas2")

        for container in containers:
            title_span = container.find("span", class_="textoTituloPubli2")
            if not title_span:
                continue
            activity_name = title_span.get_text().strip()
            if not any(name in activity_name for name in self.activity_names):
                continue

            # Extract session info
            info = self.extract_session_info(container)
            if not info:
                continue

            # Extract sign-up link
            link = self.extract_link(container)
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
        time_filters = self.config.get("time_filters", {})
        filtered = []
        for s in sessions:
            day = s["day_of_week"]
            start_hour = int(s["time"].split("-")[0].split(":")[0])
            if day in ["Saturday", "Sunday"]:
                cfg = time_filters.get("weekends", {})
            else:
                cfg = time_filters.get("weekdays", {}).get(day.lower(), {})
            if cfg.get("enabled", True) and cfg.get("start_hour", 0) <= start_hour <= cfg.get("end_hour", 23):
                filtered.append(s)
        return filtered

    def sort_sessions_by_date(self, sessions: List[Dict]) -> List[Dict]:
        return sorted(sessions, key=lambda x: datetime.strptime(x["date"], "%d/%m/%Y"))

    def print_sessions(self, sessions: List[Dict]):
        print("=" * 50)
        print(f"Searching activities: {', '.join(self.activity_names)}")
        print(f"Generated on: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"Total sessions: {len(sessions)}")
        print("=" * 50)
        for s in sessions:
            print(f"{s['type']} - {s['date']} ({s['day_of_week']}) {s['time']} - {s['instructor']}")
            print(f"Vacancies: {s['vacancies']} | Sign-up: {s['sign_up_link']}")
            print("-" * 50)

    def search_for_sessions(self):
        dates = self.get_date_range()
        all_sessions = []

        for date in dates:
            html = self.fetch_booking_page(date)
            if not html:
                continue
            day_sessions = self.parse_activity_sessions(html)
            all_sessions.extend(day_sessions)
            time.sleep(0.5)

        all_sessions = self.add_day_of_week(all_sessions)
        available = [s for s in all_sessions if "Complete" not in s["status"]]
        filtered = self.filter_sessions_by_time(available)
        filtered_sorted = self.sort_sessions_by_date(filtered)

        self.print_sessions(filtered_sorted)


def main():
    app = typer.Typer()

    @app.callback(invoke_without_command=True)
    def cli(
        activity_names: str = typer.Option(None, help="Comma-separated activity names"),
        days: int = typer.Option(None, help="Days to search"),
        weekdays: str = typer.Option(None, help="Weekday time filter JSON"),
        weekends: str = typer.Option(None, help="Weekend time filter JSON"),
        verbose: bool = typer.Option(False, help="Verbose logging"),
    ):
        scraper = StratfordPadelActivityScraper()
        if activity_names:
            scraper.activity_names = [name.strip() for name in activity_names.split(",")]
        if days:
            scraper.days_to_search = days
        if weekdays:
            scraper.config["time_filters"]["weekdays"] = json.loads(weekdays)
        if weekends:
            scraper.config["time_filters"]["weekends"] = json.loads(weekends)
        if verbose:
            scraper.config["debug_settings"]["verbose_logging"] = True

        scraper.search_for_sessions()

    app()


if __name__ == "__main__":
    main()
