import re
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class StratfordPadelActivityScraper:
    def __init__(self):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/ActBooking/Agenda.aspx"
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        # Runtime-configurable (set by Streamlit)
        self.config = {
            "days_ahead": 5,
            "time_filters": {
                "saturday": {
                    "enabled": True,
                    "start_hour": 10,
                    "end_hour": 22,
                    "description": "10am-10pm",
                },
                "sunday": {"enabled": True, "start_hour": 12, "end_hour": 20, "description": "12pm-8pm"},
                "monday": {"enabled": True, "start_hour": 12, "end_hour": 23, "description": "12-11pm"},
                "tuesday": {"enabled": True, "start_hour": 12, "end_hour": 23, "description": "12-11pm"},
                "wednesday": {
                    "enabled": True,
                    "start_hour": 12,
                    "end_hour": 23,
                    "description": "12-11pm",
                },
                "thursday": {"enabled": True, "start_hour": 12, "end_hour": 23, "description": "12-11pm"},
                "friday": {"enabled": True, "start_hour": 12, "end_hour": 23, "description": "12-11pm"},
            },
            "keywords": [
                "Train and Play Green",
                "Padel Academy Green",
                "Private Class",
                "PadelConnect Intermediates",
            ],
        }

    # -------------------------
    # Helpers
    # -------------------------

    def get_dates(self) -> List[str]:
        dates = []
        today = datetime.now()
        for i in range(self.config["days_ahead"]):
            d = today + timedelta(days=i)
            dates.append(d.strftime("%d-%m-%Y"))
        return dates

    # -------------------------
    # Fetch
    # -------------------------
    def fetch_day(self, date: str = None) -> Optional[str]:
        print(f"Fetching agenda for {date}")

        try:
            r = requests.get(
                self.base_url,
                params={"d": date, "m": ""},
                headers=self.headers,
                timeout=10,
            )
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"❌ Failed to fetch {date}: {e}")
            return None

    def parse_sessions(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        sessions = []

        containers = soup.find_all("div", class_="contenedor2Columnas2")
        print(f"Found {len(containers)} containers")

        for c in containers:
            # -------------------------
            # Title
            # -------------------------
            title_span = c.find("span", class_="textoTituloPubli2")
            if not title_span:
                continue

            title = title_span.get_text(strip=True)

            # Exact keyword filtering (case-sensitive)
            if self.config.get("keywords"):
                if not any(k in title for k in self.config["keywords"]):
                    continue

            # -------------------------
            # Date & time
            # -------------------------
            datetime_span = c.find("span", id=lambda x: x and "LabelHorarioValor" in x)
            if not datetime_span:
                continue

            m = re.search(
                r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})-(\d{2}:\d{2})",
                datetime_span.get_text(strip=True),
            )
            if not m:
                continue

            date_str, start_time, end_time = m.groups()
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            day_name = date_obj.strftime("%A")

            # -------------------------
            # Time filter
            # -------------------------
            cfg = self.config["time_filters"].get(day_name.lower())
            hour = int(start_time.split(":")[0])

            if not cfg or not cfg["enabled"]:
                continue
            if not (cfg["start_hour"] <= hour <= cfg["end_hour"]):
                continue

            # -------------------------
            # Instructor
            # -------------------------
            instructor = "N/A"
            instructor_span = c.find("span", id=lambda x: x and "LabelProfesor" in x)
            if instructor_span:
                instructor = instructor_span.get_text(strip=True)

            # -------------------------
            # Vacancies
            # -------------------------
            vacancies = "N/A"
            vacancies_span = c.find("span", id=lambda x: x and "LabelPlazasDisponibles" in x)
            if vacancies_span:
                vacancies = vacancies_span.get_text(strip=True)

            # -------------------------
            # Court / location
            # -------------------------
            court = None
            court_span = c.find("span", id=lambda x: x and "LabelUbicacion" in x)
            if court_span:
                court = court_span.get_text(strip=True)

            # -------------------------
            # Levels (NEW)
            # -------------------------
            levels = None
            levels_span = c.find("span", id=lambda x: x and "LabelNiveles" in x)
            if levels_span:
                levels = levels_span.get_text(strip=True)

            # -------------------------
            # Signup link
            # -------------------------
            link = None
            link_tag = c.find("a", class_="boton")
            if link_tag and link_tag.get("href"):
                href = link_tag["href"]
                if href.startswith("Info.aspx"):
                    link = f"https://stratfordpadelclub.matchpoint.com.es/ActBooking/{href}"
                elif href.startswith("/"):
                    link = f"https://stratfordpadelclub.matchpoint.com.es{href}"
                elif href.startswith("http"):
                    link = href

            if not link:
                continue

            # -------------------------
            # Final session
            # -------------------------
            sessions.append(
                {
                    "title": title,
                    "date": date_str,
                    "day_name": day_name,
                    "time": f"{start_time}-{end_time}",
                    "instructor": instructor,
                    "vacancies": vacancies,
                    "court": court,
                    "levels": levels,
                    "link": link,
                }
            )

        return sessions

    # -------------------------
    # Main entry
    # -------------------------
    def search(self) -> List[Dict]:
        print("🚀 Starting activity search")

        results = []
        dates = self.get_dates()
        print(f"Checking {len(dates)} days")

        for d in dates:
            html = self.fetch_day(d)
            if not html:
                continue

            day_sessions = self.parse_sessions(html)
            print(f"→ {len(day_sessions)} valid sessions found")

            results.extend(day_sessions)

        print(f"✅ Total activities collected: {len(results)}")
        return results


def main():
    """Main function to run the scraper"""
    print("Starting Stratford Padel Club Activity Finder...")

    try:
        scraper = StratfordPadelActivityScraper()
    except Exception as e:
        print(f"Error initializing scraper: {e}")
        return

    try:
        # Search for activity sessions based on config
        scraper.search()
    except KeyboardInterrupt:
        print("\nSearch interrupted by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
