#!/usr/bin/env python3
"""
VAK Pardubice – po přihlášení otevře stránku 'Naměřené stavy' (Smart Metering)
a uloží její HTML pro analýzu.

Princip: ASP.NET WebForm. Klik v menu = postback s
  __EVENTTARGET = ctl00$ctl00$MainMenu1$btnProfileData
  __EVENTARGUMENT = ''
+ aktuální __VIEWSTATE atd. ze stránky po loginu.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

import requests
from bs4 import BeautifulSoup

from vak_login import (
    BASE_URL, LOGIN_URL, USER_AGENT,
    FIELD_USER, FIELD_PASS, FIELD_BTN, BTN_VALUE,
    _hidden_inputs, _is_logged_in,
)

POSTBACK_TARGETS = {
    "namerene_stavy": "ctl00$ctl00$MainMenu1$btnProfileData",
    "historie_spotreby": "ctl00$ctl00$MainMenu1$btnProfileGraph",
    "samoodecet": "ctl00$ctl00$MainMenu1$LoginView1$LBAF018",
}

log = logging.getLogger("vak.measured")


def _login(session: requests.Session, user: str, password: str, timeout: int = 30) -> str:
    log.info("GET %s", LOGIN_URL)
    r = session.get(LOGIN_URL, timeout=timeout)
    r.raise_for_status()
    hidden = _hidden_inputs(r.text)
    payload = dict(hidden)
    payload[FIELD_USER] = user
    payload[FIELD_PASS] = password
    payload[FIELD_BTN] = BTN_VALUE
    payload.setdefault("__EVENTTARGET", "")
    payload.setdefault("__EVENTARGUMENT", "")
    log.info("POST login")
    r2 = session.post(
        LOGIN_URL,
        data=payload,
        headers={"Referer": LOGIN_URL, "Origin": BASE_URL,
                 "Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout, allow_redirects=True,
    )
    r2.raise_for_status()
    if not _is_logged_in(r2.text):
        raise RuntimeError("Login se nezdařil.")
    log.info("Login OK, URL: %s", r2.url)
    return r2.text


def _form_action(html: str, current_url: str = LOGIN_URL) -> str:
    from urllib.parse import urljoin
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="aspnetForm") or soup.find("form")
    action = (form.get("action") if form else None) or current_url
    if action.startswith("./"):
        action = action[2:]
    return urljoin(current_url, action)


def postback(session: requests.Session, current_html: str, current_url: str,
             event_target: str, event_argument: str = "",
             timeout: int = 30) -> requests.Response:
    """Provede ASP.NET __doPostBack na aktuální stránce."""
    hidden = _hidden_inputs(current_html)
    if "__VIEWSTATE" not in hidden:
        raise RuntimeError("Na aktuální stránce chybí __VIEWSTATE – nejde postback.")
    payload = dict(hidden)
    payload["__EVENTTARGET"] = event_target
    payload["__EVENTARGUMENT"] = event_argument
    action_url = _form_action(current_html, current_url)
    log.info("POSTBACK target=%s -> %s", event_target, action_url)
    r = session.post(
        action_url,
        data=payload,
        headers={"Referer": current_url, "Origin": BASE_URL,
                 "Content-Type": "application/x-www-form-urlencoded",
                 "X-MicrosoftAjax": "Delta=true",
                 "X-Requested-With": "XMLHttpRequest"},
        timeout=timeout, allow_redirects=True,
    )
    r.raise_for_status()
    return r


def text_summary(html: str, max_lines: int = 80) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[:max_lines])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--user", default=os.environ.get("VAK_USER"))
    p.add_argument("--password", default=os.environ.get("VAK_PASS"))
    p.add_argument("--target", default="namerene_stavy",
                   choices=list(POSTBACK_TARGETS.keys()))
    p.add_argument("--period", choices=["W", "M", "Y"], default=None,
                   help="Po otevření přepnout období (W=týden, M=měsíc, Y=rok).")
    p.add_argument("--dump", default="measured.html")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not args.user or not args.password:
        log.error("Chybí VAK_USER / VAK_PASS.")
        return 1

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "cs,en;q=0.8",
    })

    after_login_html = _login(session, args.user, args.password)
    current_url = LOGIN_URL

    target = POSTBACK_TARGETS[args.target]
    r = postback(session, after_login_html, current_url, target)
    log.info("HTTP %s, URL: %s, %d B", r.status_code, r.url, len(r.text))

    # Některé ASP.NET menu položky vyvolají GET redirect na podstránku.
    # Pokud odpověď obsahuje jen Ajax delta, načteme finální URL ještě GETem.
    final_html = r.text
    if "|pageRedirect|" in final_html:
        # formát:  ...|pageRedirect||%2fUserdata%2fProfileData.aspx|...
        from urllib.parse import unquote
        parts = final_html.split("|pageRedirect||", 1)
        if len(parts) == 2:
            redirect = unquote(parts[1].split("|", 1)[0])
            redirect_url = BASE_URL + redirect if redirect.startswith("/") else redirect
            log.info("Ajax redirect -> %s", redirect_url)
            r = session.get(redirect_url, timeout=30)
            r.raise_for_status()
            final_html = r.text
            current_url = redirect_url

    with open(args.dump, "w", encoding="utf-8") as f:
        f.write(final_html)
    log.info("Uloženo do %s (%d B)", args.dump, len(final_html))

    if args.period:
        period_field = ("ctl00$ctl00$ctl00$ContentPlaceHolder1Common$"
                        "ContentPlaceHolder1$UserDataContentPlaceHolder$"
                        "GraphFilter1$edGraphLength")
        log.info("Přepínám období -> %s", args.period)
        hidden = _hidden_inputs(final_html)
        payload = dict(hidden)
        payload[period_field] = args.period
        payload["__EVENTTARGET"] = period_field
        payload["__EVENTARGUMENT"] = ""
        action_url = _form_action(final_html, current_url)
        r2 = session.post(
            action_url, data=payload,
            headers={"Referer": current_url, "Origin": BASE_URL,
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=30, allow_redirects=True,
        )
        r2.raise_for_status()
        final_html = r2.text
        log.info("HTTP %s, URL: %s, %d B", r2.status_code, r2.url, len(final_html))
        out2 = args.dump.replace(".html", f"_{args.period}.html")
        with open(out2, "w", encoding="utf-8") as f:
            f.write(final_html)
        log.info("Uloženo do %s", out2)

    print("\n----- TEXT (prvních 80 řádků) -----")
    print(text_summary(final_html))
    return 0


if __name__ == "__main__":
    sys.exit(main())
