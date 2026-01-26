from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://stratfordpadelclub.matchpoint.com.es"
LOGIN_URL = f"{BASE_URL}/Login.aspx"
SCHEDULE_URL = f"{BASE_URL}/Intranet/Schedule.aspx"
MATCHES_URL = f"{BASE_URL}/Intranet/Matches.aspx"


# =========================
# Data model
# =========================
@dataclass(frozen=True)
class UpcomingItem:
    match_id: str
    description: str
    date: str
    time_start: str
    time_end: str
    court: str
    url: str


# =========================
# Client
# =========================
class StratfordPadelMatchFetcher:
    def __init__(self, username: str, password: str, verbose: bool = False) -> None:
        self.username = username
        self.password = password
        self.verbose = verbose

        self._log("🔐 Initialising MatchPoint client")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120 Safari/537.36"
                )
            }
        )

        self._login()
        self._log("✅ Session ready")

    # =========================
    # Logging
    # =========================
    def _log(self, message: str) -> None:
        if self.verbose:
            print(message)

    # =========================
    # Authentication
    # =========================
    def _login(self) -> None:
        self._log("➡️ Loading login page")
        login_page = self.session.get(LOGIN_URL)
        login_page.raise_for_status()
        soup = BeautifulSoup(login_page.text, "html.parser")

        def val(name: str) -> str:
            el = soup.find("input", {"name": name})
            return el.get("value", "") if el else ""

        payload = {
            "__VIEWSTATE": val("__VIEWSTATE"),
            "__EVENTVALIDATION": val("__EVENTVALIDATION"),
            "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
            "ctl00$ContentPlaceHolderContenido$Login1$UserName": self.username,
            "ctl00$ContentPlaceHolderContenido$Login1$Password": self.password,
            "ctl00$ContentPlaceHolderContenido$Login1$LoginButton": "Sign in",
        }

        self._log("➡️ Submitting login form")
        resp = self.session.post(
            f"{LOGIN_URL}?return_url=%7e%2fIntranet%2fSchedule.aspx",
            data=payload,
            allow_redirects=True,
        )
        resp.raise_for_status()

        if "Schedule.aspx" not in resp.url:
            raise RuntimeError("Login failed")

        self._log("✅ Logged in successfully")

    # =========================
    # Public API
    # =========================
    def get_upcoming_items(self) -> List[UpcomingItem]:
        self._log("📡 Fetching upcoming items")

        activities = self._fetch_next_activities()
        self._log(f"📅 Activities found: {len(activities)}")

        matches = self._fetch_signed_up_matches()
        self._log(f"🎾 Matches found: {len(matches)}")

        combined = self._combine_and_dedupe(activities, matches)
        self._log(f"🧹 After dedupe: {len(combined)} items")

        return combined

    # =========================
    # Fetchers
    # =========================
    def _fetch_next_activities(self) -> List[UpcomingItem]:
        self._log("➡️ Fetching schedule page")
        soup = self._get_soup(SCHEDULE_URL)

        table = soup.find(
            "table",
            id="ctl00_ctl00_ContentPlaceHolderContenido_ContentPlaceHolderContenido_GridViewListado",
        )

        items: List[UpcomingItem] = []

        if not table:
            self._log("⚠️ Activities table not found")
            return items

        for row in table.find_all("tr"):
            link = row.find("a", class_="TextoLinkBlanco")
            if not link:
                continue

            date = (link.get("fechainicio", "").split() or [""])[0]
            time_start = self._extract_time(link.get("horainicio", ""))
            time_end = self._extract_time(link.get("horafin", ""))

            href = link.get("href", "")

            items.append(
                UpcomingItem(
                    match_id=href,
                    description=link.get("descripcion", ""),
                    date=date,
                    time_start=time_start,
                    time_end=time_end,
                    court=link.get("recurso", ""),
                    url=f"{BASE_URL}/Intranet/{href}",
                )
            )

        self._log(f"✅ Parsed {len(items)} activities")
        return items

    def _fetch_signed_up_matches(self) -> List[UpcomingItem]:
        self._log("➡️ Fetching matches page")
        soup = self._get_soup(MATCHES_URL)

        pages = self._get_page_numbers(soup)
        self._log(f"📄 Match pages detected: {pages}")

        items: List[UpcomingItem] = []

        for page in pages:
            self._log(f"➡️ Parsing matches page {page}")
            page_soup = soup if page == 1 else self._get_soup(f"{MATCHES_URL}?ap={page}")
            page_items = self._extract_matches_from_page(page_soup)
            self._log(f"➡️ {len(page_items)} Found in Page {page}")
            items.extend(page_items)

        return items

    # =========================
    # Parsing helpers
    # =========================
    def _extract_matches_from_page(self, soup: BeautifulSoup) -> List[UpcomingItem]:
        items: List[UpcomingItem] = []

        title = soup.find(
            "span",
            id="ctl00_ctl00_ContentPlaceHolderContenido_ContentPlaceHolderContenido_LabelPartidasApuntado",
        )
        if not title:
            return items

        detail = title.find_parent("div", class_="contenedorTitulo").find_next_sibling(
            "div", class_="Detalle"
        )

        for block in detail.find_all("div", class_="contenedorContenidoPartidas"):

            def txt(id_part: str) -> str:
                el = block.find("span", id=lambda x: x and id_part in x)
                return el.get_text(strip=True) if el else ""

            hidden = block.find_next("input", id=lambda x: x and "HiddenFieldId" in x)
            match_id = hidden.get("value", "") if hidden else ""

            items.append(
                UpcomingItem(
                    match_id=match_id,
                    description="",
                    date=txt("LabelFecha"),
                    time_start=txt("LabelHoraInicio"),
                    time_end=txt("LabelHoraFin"),
                    court=txt("LabelRecurso"),
                    url=f"{BASE_URL}/Matches/Share.aspx?id={match_id}",
                )
            )

        return items

    # =========================
    # Utilities
    # =========================
    def _combine_and_dedupe(self, a: List[UpcomingItem], b: List[UpcomingItem]) -> List[UpcomingItem]:
        self._log(f"🔀 Combining {len(a)} activities + {len(b)} matches")

        seen: set[Tuple[str, str]] = set()
        result: List[UpcomingItem] = []

        for item in a + b:
            key = (item.date, item.time_start)
            if key not in seen and all(key):
                seen.add(key)
                result.append(item)

        self._log(f"🧹 Removed {len(a) + len(b) - len(result)} duplicates")
        return result

    def _get_page_numbers(self, soup: BeautifulSoup) -> List[int]:
        pager = soup.find(
            "span",
            id="ctl00_ctl00_ContentPlaceHolderContenido_ContentPlaceHolderContenido_DataPagerPartidasApuntado",
        )
        pages = {1}

        if not pager:
            return [1]

        for a in pager.find_all("a", href=True):
            match = re.search(r"ap=(\d+)", a["href"])
            if match:
                pages.add(int(match.group(1)))

        return sorted(pages)

    def _get_soup(self, url: str) -> BeautifulSoup:
        self._log(f"🌐 GET {url}")
        resp = self.session.get(url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    @staticmethod
    def _extract_time(value: str) -> str:
        parts = value.split()
        if len(parts) > 1:
            return ":".join(parts[1].split(":")[:2])
        return ""


# =========================
# Entrypoint
# =========================
def main() -> None:
    client = StratfordPadelMatchFetcher(
        username="test",
        password="test",
        verbose=True,  # 🔊 toggle logs here
    )

    upcoming = client.get_upcoming_items()

    for item in upcoming:
        print(item)


if __name__ == "__main__":
    main()
