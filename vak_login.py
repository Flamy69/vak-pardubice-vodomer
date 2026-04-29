#!/usr/bin/env python3
"""
VAK Pardubice – přihlašovací test.

Přihlásí se do zákaznického portálu https://zakaznik.vakpce.cz
a ověří, že jsme uvnitř (kontrolou, že po loginu zmizel formulář
a/nebo se objevil odkaz na odhlášení).

Použití:
    # přes proměnné prostředí
    set VAK_USER=jmeno@example.cz
    set VAK_PASS=tajneheslo
    python vak_login.py

    # nebo přímo
    python vak_login.py --user jmeno@example.cz --password tajneheslo

    # uložit stránku po loginu pro další analýzu (bez hesla v logu!)
    python vak_login.py --dump after_login.html

Závislosti:  pip install requests beautifulsoup4
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://zakaznik.vakpce.cz"
LOGIN_URL = f"{BASE_URL}/Default.aspx"

# Názvy polí ASP.NET WebForm – zjištěno ze zdroje stránky 2026-04-29
FIELD_USER = "ctl00$ctl00$lvLoginForm$LoginDialog1$edEmail"
FIELD_PASS = "ctl00$ctl00$lvLoginForm$LoginDialog1$edPassword"
FIELD_BTN = "ctl00$ctl00$lvLoginForm$LoginDialog1$btnLogin"
BTN_VALUE = "Vstoupit"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

log = logging.getLogger("vak")


def _hidden_inputs(html: str) -> dict[str, str]:
    """Vytáhne všechna hidden inputs (__VIEWSTATE, __EVENTVALIDATION, ...)."""
    soup = BeautifulSoup(html, "html.parser")
    data: dict[str, str] = {}
    for inp in soup.find_all("input", attrs={"type": "hidden"}):
        name = inp.get("name")
        if not name:
            continue
        data[name] = inp.get("value", "")
    return data


def _is_logged_in(html: str) -> bool:
    """Heuristika: po loginu by neměl být input type=password
    a mělo by tam být něco jako 'Odhlásit'."""
    lowered = html.lower()
    has_password_field = 'type="password"' in lowered
    has_logout = ("odhlásit" in lowered) or ("odhlasit" in lowered) or ("logout" in lowered)
    return (not has_password_field) and has_logout


def login(user: str, password: str, *, dump_path: Optional[str] = None,
          timeout: int = 30) -> bool:
    if not user or not password:
        log.error("Chybí uživatel nebo heslo (--user / --password nebo VAK_USER / VAK_PASS).")
        return False

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "cs,en;q=0.8",
    })

    log.info("GET %s", LOGIN_URL)
    r = session.get(LOGIN_URL, timeout=timeout)
    r.raise_for_status()

    hidden = _hidden_inputs(r.text)
    if "__VIEWSTATE" not in hidden:
        log.error("Na stránce nenalezeno __VIEWSTATE – portál se mohl změnit.")
        return False
    log.info("Získáno %d hidden polí (__VIEWSTATE: %d B)",
             len(hidden), len(hidden.get("__VIEWSTATE", "")))

    payload = dict(hidden)
    payload[FIELD_USER] = user
    payload[FIELD_PASS] = password
    payload[FIELD_BTN] = BTN_VALUE
    # ASP.NET někdy očekává prázdné __EVENTTARGET / __EVENTARGUMENT
    payload.setdefault("__EVENTTARGET", "")
    payload.setdefault("__EVENTARGUMENT", "")

    log.info("POST %s (login)", LOGIN_URL)
    r2 = session.post(
        LOGIN_URL,
        data=payload,
        headers={
            "Referer": LOGIN_URL,
            "Origin": BASE_URL,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=timeout,
        allow_redirects=True,
    )
    r2.raise_for_status()
    log.info("HTTP %s, finální URL: %s", r2.status_code, r2.url)

    if dump_path:
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(r2.text)
        log.info("Stránka po loginu uložena do %s (%d B)", dump_path, len(r2.text))

    if _is_logged_in(r2.text):
        log.info("✅ Přihlášení vypadá úspěšně (žádné password pole + nalezeno 'Odhlásit').")
        return True

    # Pokus o vytažení chybové hlášky portálu
    soup = BeautifulSoup(r2.text, "html.parser")
    err = soup.find(id="status")
    err_text = err.get_text(strip=True) if err else ""
    if err_text:
        log.error("❌ Portál hlásí: %s", err_text)
    else:
        log.error("❌ Přihlášení se nezdařilo (na stránce zůstává login formulář).")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test loginu na zakaznik.vakpce.cz")
    parser.add_argument("--user", default=os.environ.get("VAK_USER"))
    parser.add_argument("--password", default=os.environ.get("VAK_PASS"))
    parser.add_argument("--dump", help="Uložit HTML stránky po loginu do tohoto souboru.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    ok = login(args.user, args.password, dump_path=args.dump)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
