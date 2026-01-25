import json
import sys
from datetime import datetime, timedelta

# Check for required dependencies
try:
    import re
    import time
    from typing import Dict, List, Optional

    import requests
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Please install required packages:")
    print("pip install requests beautifulsoup4 lxml")
    sys.exit(1)

print("Search Initiated")


class StratfordPadelMatchScraper:
    def __init__(self, config_file: str = "config.json"):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/Matches/Search.aspx"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Load configuration
        self.config = self.load_config(config_file)
        print("Match scraper initialized successfully!")
        print(f"Configuration loaded from: {config_file}")

    def load_config(self, config_file: str) -> Dict:
        """
        Load configuration from JSON file

        Args:
            config_file: Path to configuration file

        Returns:
            Configuration dictionary
        """
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            print(f"Configuration loaded successfully!")
            return config
        except FileNotFoundError:
            print(f"Configuration file '{config_file}' not found. Using default settings.")
            return self.get_default_config()
        except json.JSONDecodeError as e:
            print(f"Error parsing configuration file: {e}. Using default settings.")
            return self.get_default_config()

    def get_default_config(self) -> Dict:
        """
        Get default configuration if config file is not available

        Returns:
            Default configuration dictionary
        """
        return {
            "search_settings": {
                "level_range": {"min": 2.0, "max": 2.5},
                "weeks_to_search": 3,
                "output_filename": "padel_matches_2_00_2_50.txt",
            },
            "time_filters": {
                "weekends": {"enabled": True, "description": "All day"},
                "weekdays": {
                    "tuesday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "friday": {"enabled": True, "start_hour": 18, "end_hour": 23},
                    "monday": {"enabled": True, "start_hour": 19, "end_hour": 23},
                    "wednesday": {"enabled": True, "start_hour": 19, "end_hour": 23},
                    "thursday": {"enabled": True, "start_hour": 19, "end_hour": 23},
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
            "debug_settings": {"save_raw_html": False, "verbose_logging": True},
        }

    def get_date_range_3_weeks(self) -> List[str]:
        """
        Generate a list of dates for the next 3 weeks

        Returns:
            List of dates in DD/MM/YYYY format
        """
        dates = []
        current_date = datetime.now()

        for i in range(21):  # 3 weeks = 21 days
            future_date = current_date + timedelta(days=i)
            dates.append(future_date.strftime("%d/%m/%Y"))

        return dates

    def get_week_ranges(self) -> List[tuple]:
        """
        Generate separate week ranges based on configuration

        Returns:
            List of tuples containing (start_date, end_date) for each week
        """
        current_date = datetime.now()
        week_ranges = []
        weeks_to_search = self.config["search_settings"]["weeks_to_search"]

        for week in range(weeks_to_search):
            start_date = current_date + timedelta(days=week * 7)
            end_date = start_date + timedelta(days=6)  # 7 days total (0-6)

            week_ranges.append((start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y")))

        return week_ranges

    def fetch_matches_page(self, start_date: str, end_date: str) -> Optional[str]:
        """
        Fetch the matches search page for a specific date range

        Args:
            start_date: Start date in DD/MM/YYYY format
            end_date: End date in DD/MM/YYYY format

        Returns:
            HTML content as string or None if failed
        """
        try:
            print(f"Fetching matches from {start_date} to {end_date}")
            # Get level range from config
            level_min = self.config["search_settings"]["level_range"]["min"]
            level_max = self.config["search_settings"]["level_range"]["max"]

            # Build parameters from config
            params = self.config["url_parameters"].copy()
            params.update(
                {
                    "idNivelMinimo": f"{level_min:.2f}".replace(".", ","),
                    "idNivelMaximo": f"{level_max:.2f}".replace(".", ","),
                    "fechaDesde": start_date,
                    "fechaHasta": end_date,
                    "horaDesde": "00:00",  # No URL-level time filtering
                    "horaHasta": "23:59",  # No URL-level time filtering
                }
            )

            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()

            # Save raw HTML if enabled in config
            if self.config["debug_settings"]["save_raw_html"]:
                with open("raw_matches_page.html", "w", encoding="utf-8") as f:
                    f.write(response.text)
                print("Raw HTML saved to: raw_matches_page.html")

            return response.text

        except requests.RequestException as e:
            print(f"Error fetching matches page: {e}")
            return None

    def parse_matches(self, html_content: str) -> List[Dict]:
        """
        Parse HTML content to extract match details and links

        Args:
            html_content: Raw HTML content from the matches page

        Returns:
            List of dictionaries containing match details
        """
        soup = BeautifulSoup(html_content, "html.parser")
        matches = []

        # Find all match containers - look for the contenedorContenidoPartidas class
        match_containers = soup.find_all("div", class_="contenedorContenidoPartidas")

        for container in match_containers:
            try:
                # Extract day and time
                day_span = container.find("span", id=lambda x: x and "LabelDiaSemana" in x)
                day_number_span = container.find("span", id=lambda x: x and "LabelFechaInicio" in x)
                time_span = container.find("span", id=lambda x: x and "LabelHoraInicio" in x)

                if not all([day_span, day_number_span, time_span]):
                    continue

                day_name = day_span.get_text(strip=True)
                day_number = day_number_span.get_text(strip=True)
                time = time_span.get_text(strip=True)

                # Extract level range
                level_span = container.find("span", id=lambda x: x and "LabelNivelValor" in x)
                if not level_span:
                    continue

                level_text = level_span.get_text(strip=True)
                # Parse level range (e.g., "3,50 - 4,00")
                level_parts = level_text.split(" - ")
                if len(level_parts) != 2:
                    continue

                level_min = level_parts[0]
                level_max = level_parts[1]

                # Check if level is within our target range from config
                try:
                    min_level = float(level_min.replace(",", "."))
                    max_level = float(level_max.replace(",", "."))

                    # Get target range from config
                    target_min = self.config["search_settings"]["level_range"]["min"]
                    target_max = self.config["search_settings"]["level_range"]["max"]

                    # Check if the level range overlaps with our target range
                    # Accept if: min_level < target_max AND max_level > target_min
                    if min_level < target_max and max_level > target_min:
                        # Find the Enter link in this container
                        enter_link = container.find("a", class_="boton")
                        match_link = ""
                        if enter_link:
                            match_link = enter_link.get("href", "")
                            # Make the link absolute if it's relative
                            if match_link.startswith("Match.aspx"):
                                match_link = (
                                    f"https://stratfordpadelclub.matchpoint.com.es/Matches/{match_link}"
                                )

                        match_info = {
                            "day_name": day_name,
                            "day_number": day_number,
                            "time": time,
                            "level_min": level_min,
                            "level_max": level_max,
                            "level_range": f"{level_min} - {level_max}",
                            "type": "Mixed Padel Match",
                            "link": match_link,
                        }
                        matches.append(match_info)
                except ValueError:
                    continue

            except Exception as e:
                if self.config["debug_settings"]["verbose_logging"]:
                    print(f"Error parsing match container: {e}")
                continue

        return matches

    def filter_matches_by_time(self, matches: List[Dict]) -> List[Dict]:
        """
        Filter matches based on time criteria from configuration

        Args:
            matches: List of match dictionaries

        Returns:
            Filtered list of matches
        """
        filtered_matches = []
        time_filters = self.config["time_filters"]

        for match in matches:
            day_name = match["day_name"].lower()
            time_str = match["time"]

            try:
                hour = int(time_str.split(":")[0])

                # Weekdays
                if day_name in time_filters["weekdays"]:
                    cfg = time_filters["weekdays"][day_name]
                    if cfg["enabled"] and cfg["start_hour"] <= hour <= cfg["end_hour"]:
                        filtered_matches.append(match)
                # Weekends now handled separately per day
                elif day_name in time_filters["weekends"]:
                    cfg = time_filters["weekends"][day_name]
                    if cfg["enabled"] and cfg["start_hour"] <= hour <= cfg["end_hour"]:
                        filtered_matches.append(match)

            except (ValueError, IndexError):
                continue

        return filtered_matches

    def add_date_info(self, matches: List[Dict]) -> List[Dict]:
        """
        Add proper date information to matches

        Args:
            matches: List of match dictionaries

        Returns:
            List of matches with date information
        """
        current_date = datetime.now()

        for match in matches:
            day_name = match["day_name"]
            day_number = int(match["day_number"])

            # Find the next occurrence of this day of week
            target_weekday = self.get_weekday_number(day_name)
            current_weekday = current_date.weekday()

            # Calculate days to add to get to the target weekday
            days_to_add = (target_weekday - current_weekday) % 7

            # If it's today and the day number matches, use today
            if days_to_add == 0 and day_number == current_date.day:
                match_date = current_date
            else:
                # Find the next occurrence
                match_date = current_date + timedelta(days=days_to_add)

                # If the day number doesn't match, add another week
                while match_date.day != day_number:
                    match_date += timedelta(days=7)

            match["date"] = match_date.strftime("%d/%m/%Y")
            match["day_of_week"] = match_date.strftime("%A")
            match["datetime_obj"] = match_date

        return matches

    def get_weekday_number(self, day_name: str) -> int:
        """
        Convert day name to weekday number (0=Monday, 6=Sunday)

        Args:
            day_name: Day name (Monday, Tuesday, etc.)

        Returns:
            Weekday number
        """
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

    def sort_matches_by_date(self, matches: List[Dict]) -> List[Dict]:
        """
        Sort matches by date (earliest first)

        Args:
            matches: List of match dictionaries

        Returns:
            Sorted list of matches
        """
        return sorted(matches, key=lambda x: x["datetime_obj"])

    def print_matches(self, matches: List[Dict]):
        """
        Print match details to the console instead of writing to a file.

        Args:
            matches: List of match dictionaries
        """
        level_min = self.config["search_settings"]["level_range"]["min"]
        level_max = self.config["search_settings"]["level_range"]["max"]
        weeks_to_search = self.config["search_settings"]["weeks_to_search"]

        print("=" * 80)
        print("PADEL MATCHES - STRATFORD PADEL CLUB")
        print(f"Level: {level_min:.2f} - {level_max:.2f}")
        print("=" * 80)
        print(f"Generated on: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        print(f"Search Method: {weeks_to_search} separate week calls")
        print(f"Total Matches Found: {len(matches)}")
        print("Time Filter: Based on configuration")
        print("=" * 80)
        print()

        if not matches:
            print("No matches found matching the criteria.")
            return

        for i, match in enumerate(matches, 1):
            print(f"Match {i}:")
            print(f"  Date: {match['date']} ({match['day_of_week']})")
            print(f"  Time: {match['time']}")
            print(f"  Level: {match['level_range']}")
            print(f"  Type: {match['type']}")
            if match.get("link"):
                print(f"  Link: {match['link']}")
            print("-" * 50)

        print(f"\nTotal matches printed: {len(matches)}")

    def output_summary_for_github_actions(
        self, all_matches: List[Dict], filtered_matches: List[Dict], sorted_matches: List[Dict]
    ):
        """
        Output summary statistics for GitHub Actions integration

        Args:
            all_matches: All matches found
            filtered_matches: Matches after time filtering
            sorted_matches: Sorted matches with dates
        """
        level_min = self.config["search_settings"]["level_range"]["min"]
        level_max = self.config["search_settings"]["level_range"]["max"]

        summary = {
            "total_matches": len(all_matches),
            "filtered_matches": len(filtered_matches),
            "level_range": {"min": level_min, "max": level_max},
            "weeks_searched": self.config["search_settings"]["weeks_to_search"],
            "search_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "matches": [],
        }

        # Add all filtered matches with their details
        for match in sorted_matches:
            summary["matches"].append(
                {
                    "date": match["date"],
                    "day": match["day_of_week"],
                    "time": match["time"],
                    "level_range": match["level_range"],
                    "link": match.get("link", ""),
                }
            )

        # Write summary to file for GitHub Actions
        with open("matches_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        # Also print to console in a format that can be captured by GitHub Actions
        print(f"::set-output name=total_matches::{len(all_matches)}")
        print(f"::set-output name=filtered_matches::{len(filtered_matches)}")
        print(f"::set-output name=level_range::{level_min:.2f}-{level_max:.2f}")

    def search_for_matches(self):
        """
        Main method to search for matches using configuration settings
        """
        level_min = self.config["search_settings"]["level_range"]["min"]
        level_max = self.config["search_settings"]["level_range"]["max"]
        weeks_to_search = self.config["search_settings"]["weeks_to_search"]
        output_filename = self.config["search_settings"]["output_filename"]

        print(
            f"Searching for Padel matches (Level {level_min:.2f}-{level_max:.2f}) in the next {weeks_to_search} weeks..."
        )
        current_date = datetime.now()
        print(f"Starting from: {current_date.strftime('%d/%m/%Y')}")

        # Get week ranges based on configuration
        week_ranges = self.get_week_ranges()
        print(f"Will search {len(week_ranges)} separate weeks:")
        for i, (start, end) in enumerate(week_ranges, 1):
            print(f"  Week {i}: {start} to {end}")

        all_matches = []

        # Fetch and parse each week separately
        for i, (start_date, end_date) in enumerate(week_ranges, 1):
            if self.config["debug_settings"]["verbose_logging"]:
                print(f"\n--- Week {i}: {start_date} to {end_date} ---")

            # Fetch the matches page for this week
            html_content = self.fetch_matches_page(start_date, end_date)
            if not html_content:
                print(f"Failed to fetch matches for week {i}.")
                continue

            # Parse matches for this week
            week_matches = self.parse_matches(html_content)
            if self.config["debug_settings"]["verbose_logging"]:
                print(
                    f"Week {i}: Found {len(week_matches)} matches with level {level_min:.2f}-{level_max:.2f}"
                )

            # Add to total matches
            all_matches.extend(week_matches)

        print(f"\nTotal matches found across all weeks: {len(all_matches)}")

        # Filter by time criteria
        time_filtered_matches = self.filter_matches_by_time(all_matches)
        print(f"After time filtering: {len(time_filtered_matches)} matches")

        # Add date information
        matches_with_dates = self.add_date_info(time_filtered_matches)

        # Sort by date
        sorted_matches = self.sort_matches_by_date(matches_with_dates)

        # Write to file
        self.print_matches(sorted_matches)

        # # Output summary for GitHub Actions
        # self.output_summary_for_github_actions(all_matches, time_filtered_matches, sorted_matches)

        # Print summary to console
        print(f"\n{'='*80}")
        print(f"SEARCH COMPLETE")
        print(f"{'='*80}")
        print(f"Total matches found: {len(all_matches)}")
        print(f"After time filtering: {len(time_filtered_matches)}")
        print(f"Results written to: {output_filename}")
        print(f"{'='*80}")


def main():
    import json

    import typer

    app = typer.Typer(help="Stratford Padel Club Match Finder")

    @app.callback()
    def cli(
        level_min: float = typer.Option(None, help="Minimum player level"),
        level_max: float = typer.Option(None, help="Maximum player level"),
        weeks: int = typer.Option(None, help="Weeks to search"),
        weekdays: str = typer.Option(None, help="Weekday config JSON"),
        weekends: str = typer.Option(None, help="Weekend config JSON"),
        verbose: bool = typer.Option(False, help="Verbose logging"),
    ):
        scraper = StratfordPadelMatchScraper()

        if level_min is not None:
            scraper.config["search_settings"]["level_range"]["min"] = level_min
        if level_max is not None:
            scraper.config["search_settings"]["level_range"]["max"] = level_max
        if weeks is not None:
            scraper.config["search_settings"]["weeks_to_search"] = weeks
        if weekdays:
            scraper.config["time_filters"]["weekdays"] = json.loads(weekdays)
        if weekends:
            scraper.config["time_filters"]["weekends"] = json.loads(weekends)
        if verbose:
            scraper.config["debug_settings"]["verbose_logging"] = True

        scraper.config["debug_settings"]["save_raw_html"] = False

        scraper.search_for_matches()


if __name__ == "__main__":
    main()
