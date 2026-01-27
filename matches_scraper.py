import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


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
            f"{self.config["match_search"]["search_settings"]["level_range"]} over "
            f"{self.config["match_search"]["search_settings"]["level_range"]} weeks."
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
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            self._log(f"Error fetching page: {e}")
            return None

    # =========================
    # Parsing matches
    # =========================
    def parse_matches(self, html_content: str) -> List[Dict]:
        """Extract match info from HTML"""
        soup = BeautifulSoup(html_content, "html.parser")
        matches = []

        containers = soup.find_all("div", class_="contenedorContenidoPartidas")
        self._log(f"Found {len(containers)} match containers in HTML")

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

            cfg_min = self.config["match_search"]["search_settings"]["level_range"]["min"]
            cfg_max = self.config["match_search"]["search_settings"]["level_range"]["max"]

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
            if day_name in time_filters["weekdays"]:
                cfg = time_filters["weekdays"][day_name]
            elif day_name in time_filters["weekends"]:
                cfg = time_filters["weekends"][day_name]

            if cfg and cfg["enabled"] and cfg["start_hour"] <= hour <= cfg["end_hour"]:
                filtered.append(m)

        self._log(f"{len(filtered)} matches remain after time filtering")
        return filtered

    # =========================
    # Adding dates
    # =========================
    def add_date_info(self, matches: List[Dict]) -> List[Dict]:
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

        self._log(f"Added date info to {len(matches)} matches")
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
        all_matches = []

        for start, end in self.get_week_ranges():
            html = self.fetch_matches_page(start, end)
            if html:
                day_matches = self.parse_matches(html)
                all_matches.extend(day_matches)

        filtered = self.filter_matches_by_time(all_matches)
        filtered = self.add_date_info(filtered)
        sorted_matches = self.sort_matches_by_date(filtered)
        self._log(f"Search complete: {len(sorted_matches)} matches found")
        return sorted_matches


def main():
    import json
    import os

    # Initialize scraper
    scraper = StratfordPadelMatchScraper()

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


if __name__ == "__main__":
    main()
