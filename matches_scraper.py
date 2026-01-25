import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class StratfordPadelMatchScraper:
    def __init__(self):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/Matches/Search.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        }

        self.config = self.get_default_config()

    @staticmethod
    def get_default_config() -> Dict:
        """Default configuration"""
        return {
            "search_settings": {
                "level_range": {"min": 2.0, "max": 2.5},
                "weeks_to_search": 3,
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
            "url_parameters": {
                "sexo": "todos",
                "amigos": "false",
                "jugado": "false",
                "idDeporte": "undefined",
                "nivel": "false",
                "idcentro": "undefined",
            },
        }

    def get_week_ranges(self) -> List[tuple]:
        """Generate start/end date tuples for the number of weeks to search"""
        current_date = datetime.now()
        week_ranges = []
        weeks_to_search = self.config["search_settings"]["weeks_to_search"]

        for week in range(weeks_to_search):
            start = current_date + timedelta(days=week * 7)
            end = start + timedelta(days=6)
            week_ranges.append((start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")))

        return week_ranges

    def fetch_matches_page(self, start_date: str, end_date: str) -> Optional[str]:
        """Fetch HTML page for matches in a date range"""
        try:
            level_min = self.config["search_settings"]["level_range"]["min"]
            level_max = self.config["search_settings"]["level_range"]["max"]

            params = self.config["url_parameters"].copy()
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

            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException:
            return None

    def parse_matches(self, html_content: str) -> List[Dict]:
        """Extract match info from HTML"""
        soup = BeautifulSoup(html_content, "html.parser")
        matches = []

        containers = soup.find_all("div", class_="contenedorContenidoPartidas")

        for c in containers:
            day_span = c.find("span", id=lambda x: x and "LabelDiaSemana" in x)
            day_number_span = c.find("span", id=lambda x: x and "LabelFechaInicio" in x)
            time_span = c.find("span", id=lambda x: x and "LabelHoraInicio" in x)
            level_span = c.find("span", id=lambda x: x and "LabelNivelValor" in x)
            enter_link = c.find("a", class_="boton")

            if not all([day_span, day_number_span, time_span, level_span]):
                continue

            level_parts = level_span.get_text(strip=True).split(" - ")
            if len(level_parts) != 2:
                continue

            try:
                min_level = float(level_parts[0].replace(",", "."))
                max_level = float(level_parts[1].replace(",", "."))
            except ValueError:
                continue

            cfg_min = self.config["search_settings"]["level_range"]["min"]
            cfg_max = self.config["search_settings"]["level_range"]["max"]

            if not (min_level < cfg_max and max_level > cfg_min):
                continue

            link = ""
            if enter_link:
                link = enter_link.get("href", "")
                if link.startswith("Match.aspx"):
                    link = f"https://stratfordpadelclub.matchpoint.com.es/Matches/{link}"

            matches.append(
                {
                    "day_name": day_span.get_text(strip=True),
                    "day_number": day_number_span.get_text(strip=True),
                    "time": time_span.get_text(strip=True),
                    "level_min": level_parts[0],
                    "level_max": level_parts[1],
                    "level_range": f"{level_parts[0]} - {level_parts[1]}",
                    "type": "Mixed Padel Match",
                    "link": link,
                }
            )

        return matches

    def filter_matches_by_time(self, matches: List[Dict]) -> List[Dict]:
        """Filter matches using weekday/weekend time config"""
        filtered = []
        time_filters = self.config["time_filters"]

        for m in matches:
            day_name = m["day_name"].lower()
            hour = int(m["time"].split(":")[0])

            cfg = None
            if day_name in time_filters["weekdays"]:
                cfg = time_filters["weekdays"][day_name]
            elif day_name in time_filters["weekends"]:
                cfg = time_filters["weekends"][day_name]

            if cfg and cfg["enabled"] and cfg["start_hour"] <= hour <= cfg["end_hour"]:
                filtered.append(m)

        return filtered

    def add_date_info(self, matches: List[Dict]) -> List[Dict]:
        """Add actual date and weekday info to matches"""
        current = datetime.now()

        for m in matches:
            day_name = m["day_name"]
            day_number = int(m["day_number"])
            target_weekday = self.get_weekday_number(day_name)
            days_to_add = (target_weekday - current.weekday()) % 7

            match_date = current + timedelta(days=days_to_add)
            while match_date.day != day_number:
                match_date += timedelta(days=7)

            m["date"] = match_date.strftime("%d/%m/%Y")
            m["day_of_week"] = match_date.strftime("%A")
            m["datetime_obj"] = match_date

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

    def search_matches(self) -> List[Dict]:
        """Full search: fetch, parse, filter, add dates, sort"""
        all_matches = []

        for start, end in self.get_week_ranges():
            html = self.fetch_matches_page(start, end)
            if html:
                all_matches.extend(self.parse_matches(html))

        filtered = self.filter_matches_by_time(all_matches)
        filtered = self.add_date_info(filtered)
        return self.sort_matches_by_date(filtered)


# def main():
#     import json

#     import typer

#     # Allow the callback to run directly when no command is provided
#     app = typer.Typer(invoke_without_command=True)

#     @app.callback(invoke_without_command=True)
#     def cli(
#         level_min: float = typer.Option(None, help="Minimum player level"),
#         level_max: float = typer.Option(None, help="Maximum player level"),
#         weeks: int = typer.Option(None, help="Weeks to search"),
#         weekdays: str = typer.Option(None, help="Weekday config JSON"),
#         weekends: str = typer.Option(None, help="Weekend config JSON"),
#         verbose: bool = typer.Option(False, help="Verbose logging"),
#     ):
#         scraper = StratfordPadelMatchScraper()

#         if level_min is not None:
#             scraper.config["search_settings"]["level_range"]["min"] = level_min
#         if level_max is not None:
#             scraper.config["search_settings"]["level_range"]["max"] = level_max
#         if weeks is not None:
#             scraper.config["search_settings"]["weeks_to_search"] = weeks
#         if weekdays:
#             scraper.config["time_filters"]["weekdays"] = json.loads(weekdays)
#         if weekends:
#             scraper.config["time_filters"]["weekends"] = json.loads(weekends)
#         if verbose:
#             scraper.config["debug_settings"]["verbose_logging"] = True

#         scraper.config["debug_settings"]["save_raw_html"] = False
#         scraper.search_for_matches()

#     # This actually runs the Typer CLI
#     app()


# if __name__ == "__main__":
#     main()
