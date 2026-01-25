from datetime import datetime, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup


class StratfordPadelActivityScraper:
    def __init__(self):
        self.base_url = "https://stratfordpadelclub.matchpoint.com.es/Activities/Search.aspx"
        self.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        self.config = {
            "days_ahead": 14,
            "time_filters": {},
            "keywords": [],
        }

    # -------------------------
    # Date range
    # -------------------------
    def get_date_range(self):
        today = datetime.now()
        end = today + timedelta(days=self.config["days_ahead"])
        return today.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")

    # -------------------------
    # Fetch page
    # -------------------------
    def fetch_activities_page(self) -> Optional[str]:
        start_date, end_date = self.get_date_range()

        params = {
            "fechaDesde": start_date,
            "fechaHasta": end_date,
        }

        try:
            r = requests.get(
                self.base_url,
                headers=self.headers,
                params=params,
                timeout=10,
            )
            r.raise_for_status()
            return r.text
        except Exception as e:
            print(f"Error fetching activities: {e}")
            return None

    # -------------------------
    # Parse activities
    # -------------------------
    def parse_activities(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        activities = []

        cards = soup.find_all("div", class_="contenedorContenidoPartidas")

        for card in cards:
            try:
                day_span = card.find("span", id=lambda x: x and "LabelDiaSemana" in x)
                date_span = card.find("span", id=lambda x: x and "LabelFechaInicio" in x)
                time_span = card.find("span", id=lambda x: x and "LabelHoraInicio" in x)
                title_span = card.find("span", id=lambda x: x and "LabelTipoPartida" in x)

                link_tag = card.find("a", class_="boton")

                if not all([day_span, date_span, time_span, title_span]):
                    continue

                title = title_span.get_text(strip=True)
                link = ""
                if link_tag:
                    link = link_tag.get("href", "")
                    if link.startswith("Activity.aspx"):
                        link = f"https://stratfordpadelclub.matchpoint.com.es/Activities/{link}"

                activity = {
                    "day_name": day_span.get_text(strip=True),
                    "date": date_span.get_text(strip=True),
                    "time": time_span.get_text(strip=True),
                    "title": title,
                    "link": link,
                }

                activities.append(activity)

            except Exception:
                continue

        return activities

    # -------------------------
    # Time filtering
    # -------------------------
    def filter_by_time(self, activities: List[Dict]) -> List[Dict]:
        results = []

        for act in activities:
            day = act["day_name"].lower()
            hour = int(act["time"].split(":")[0])

            cfg = self.config["time_filters"].get(day)
            if not cfg or not cfg["enabled"]:
                continue

            if cfg["start_hour"] <= hour <= cfg["end_hour"]:
                results.append(act)

        return results

    # -------------------------
    # Keyword filtering
    # -------------------------
    def filter_by_keywords(self, activities: List[Dict]) -> List[Dict]:
        if not self.config["keywords"]:
            return activities

        keywords = [k.lower() for k in self.config["keywords"]]

        return [a for a in activities if any(k in a["title"].lower() for k in keywords)]

    # -------------------------
    # Main entry
    # -------------------------
    def search(self) -> List[Dict]:
        html = self.fetch_activities_page()
        if not html:
            return []

        activities = self.parse_activities(html)
        activities = self.filter_by_time(activities)
        activities = self.filter_by_keywords(activities)

        return activities
