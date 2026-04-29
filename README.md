# vak-pardubice-vodomer

> 🚧 **Work in progress** – přihlášení a navigace na portále funguje,
> čekáme na první naměřené hodnoty z čerstvě nainstalovaného smart meteru,
> abychom mohli napsat parser a integraci do HA.

Nástroje pro automatické stahování stavu vodoměru ze zákaznického portálu
**VAK Pardubice** (<https://zakaznik.vakpce.cz>) a jeho zápis jako senzor
do **Home Assistanta** běžícího na Raspberry Pi (HA OS).

> **Tento projekt není oficiální nástroj společnosti Vodovody a kanalizace
> Pardubice, a.s. ani žádného z jejích partnerů.** Jde o nezávislou komunitní
> integraci pro osobní použití. Název „VAK Pardubice“ je použit pouze
> popisně k identifikaci portálu, ze kterého si uživatel s vlastními
> přihlašovacími údaji čte vlastní data.

Cílem je mít v HA entitu `sensor.vak_vodomer` (m³, `state_class: total_increasing`),
ze které lze poskládat denní/měsíční spotřebu přes `utility_meter` helper a
zařadit ji do Energy / Water dashboardu.

## Stav projektu

| Část | Stav |
|------|------|
| Login na portál (ASP.NET WebForms) | ✅ funguje – [vak_login.py](vak_login.py) |
| Navigace na *Naměřené stavy* / *Historie spotřeby* / *Samoodečet* | ✅ funguje – [vak_measured.py](vak_measured.py) |
| Přepínání období (týden / měsíc / rok) | ✅ funguje |
| Parser hodnoty vodoměru z HTML | ⏳ čeká na první data od smart meteru |
| Zápis do HA přes REST API (`/api/states/...`) | ⏳ TODO |
| `shell_command` + automation (1×/h) | ⏳ TODO |
| `utility_meter` + Energy dashboard (Water) | ⏳ TODO |

## Repo struktura

| Soubor | Účel |
|--------|------|
| [vak_login.py](vak_login.py) | Test přihlášení na portál (debug/diagnostika). |
| [vak_measured.py](vak_measured.py) | Login + navigace v menu, dump HTML stránky pro analýzu. |
| [.gitignore](.gitignore) | Ignoruje HTML dumpy s osobními údaji a `secrets.yaml`. |
| `README.md` | Tento dokument. |

## Použití (lokální vývoj, Windows / PowerShell)

Závislosti:

```powershell
pip install requests beautifulsoup4
```

Spuštění (přihlašovací údaje **přes proměnné prostředí**, ne v souboru):

```powershell
$env:VAK_USER = "tvuj@email.cz"
$env:VAK_PASS = "tvojeheslo"

python vak_login.py -v --dump after_login.html
python vak_measured.py -v --target namerene_stavy --period Y --dump measured.html

Remove-Item Env:VAK_USER, Env:VAK_PASS
```

`--target` lze přepnout na `historie_spotreby` nebo `samoodecet`.
`--period` přijímá `W` (týden), `M` (měsíc), `Y` (rok).

> ⚠️ **HTML dumpy** (`after_login.html`, `measured*.html`, `history*.html`)
> obsahují tvé jméno, adresu, číslo OM a smlouvy – jsou v `.gitignore`,
> **necommituj je**.

## Architektura cílového nasazení v HA

```
HA automation (time_pattern /60 min)
        │
        ▼
shell_command: python3 /config/python_scripts/vak_meter.py
        │
        ├─► GET  https://zakaznik.vakpce.cz/Default.aspx        (získat __VIEWSTATE, __EVENTVALIDATION)
        ├─► POST login form                                      (cookies = session)
        ├─► postback "Naměřené stavy" → /Userdata/ProfileData.aspx
        ├─► parse hodnoty (m³) + datum odečtu
        │
        ▼
POST http://homeassistant.local:8123/api/states/sensor.vak_vodomer
     Authorization: Bearer <Long-Lived Access Token>
     {
       "state": <m3>,
       "attributes": {
         "unit_of_measurement": "m³",
         "device_class": "water",
         "state_class": "total_increasing",
         "friendly_name": "VAK vodoměr",
         "last_reading_date": "<datum z portálu>",
         "source": "zakaznik.vakpce.cz"
       }
     }
```

### Plánované soubory v `/config/` na HA

| Soubor                                | Účel                                                 |
|---------------------------------------|------------------------------------------------------|
| `python_scripts/vak_meter.py`         | login + scrape + POST do HA REST API                 |
| `secrets.yaml` (přidat klíče)         | `vak_user`, `vak_pass`, `ha_token`                   |
| `configuration.yaml`                  | `shell_command:`, `automation:`, `utility_meter:`    |

### Plánované entity

- `sensor.vak_vodomer` – aktuální stav m³ (`state_class: total_increasing`)
- `sensor.vak_vodomer_denni` – `utility_meter` cycle: daily
- `sensor.vak_vodomer_mesicni` – `utility_meter` cycle: monthly
- (volitelně) zařazení do **Settings → Dashboards → Energy → Water consumption**

## Co je ověřeno (2026-04-29)

- **Login**: HTTP 302 → 200, v session zmizí `password` pole, objeví se „Odhlásit“.
- **Menu „Naměřené stavy“**: `https://zakaznik.vakpce.cz/Userdata/ProfileData.aspx`
- **Menu „Historie spotřeby“**: `https://zakaznik.vakpce.cz/Userdata/ProfileGraph.aspx`
- **Granularita smart meteru**: *Po hodinách / Po dnech / Po týdnech* – sedí
  k požadavku 1×/h dotaz z HA.
- **Aktuální data**: portál hlásí *„Zvolené období neobsahuje žádná naměřená
  data“* i pro „Poslední rok“ (smart meter je nový, server ještě nic neeviduje).

## Klíčová ASP.NET pole (potvrzená ze zdroje)

| Pole | `name` |
|------|--------|
| Login – e-mail | `ctl00$ctl00$lvLoginForm$LoginDialog1$edEmail` |
| Login – heslo | `ctl00$ctl00$lvLoginForm$LoginDialog1$edPassword` |
| Login – tlačítko | `ctl00$ctl00$lvLoginForm$LoginDialog1$btnLogin` (`value=Vstoupit`) |
| Menu → Naměřené stavy | `__EVENTTARGET=ctl00$ctl00$MainMenu1$btnProfileData` |
| Menu → Historie spotřeby | `__EVENTTARGET=ctl00$ctl00$MainMenu1$btnProfileGraph` |
| Menu → Samoodečet | `__EVENTTARGET=ctl00$ctl00$MainMenu1$LoginView1$LBAF018` |
| Výběr období | `…$GraphFilter1$edGraphLength` (`W` / `M` / `Y`) |
| Výběr měřidla | `…$GraphFilter1$edMeteringPoint` |

## Další kroky

1. Počkat na první naměřené hodnoty na portálu.
2. Spustit `vak_measured.py` a uložit reálné HTML s daty.
3. Napsat parser nad reálnou strukturou DOM.
4. Doplnit zápis do HA REST API (`/api/states/sensor.vak_vodomer`).
5. Vygenerovat **Long-Lived Access Token** v HA (Profil → Security).
6. Nahrát skript do `/config/python_scripts/`, doplnit `shell_command`,
   `automation` (time_pattern 1×/h), `utility_meter`.
7. Zařadit senzor do Energy dashboardu (Water).

## Roadmap

Cílem je dotáhnout projekt do podoby **HACS custom integrace**, kde si
uživatel přidá integraci přes *Settings → Devices & Services → Add integration
→ „VAK Pardubice“* a v dialogu zadá jen e-mail + heslo. Skript v `/config/`
ani `secrets.yaml` pak nebude potřeba.

Postupné fáze:

| Fáze | Obsah | Stav |
|------|-------|------|
| 1 | Reverse-engineering portálu (login, navigace, postbacky) | ✅ hotovo |
| 2 | Parser hodnoty vodoměru z HTML | ⏳ čeká na první data |
| 3 | **MVP**: `shell_command` + Python skript + REST API HA → `sensor.vak_vodomer` | ⏳ |
| 4 | Refaktor HTTP klienta do samostatného modulu (`vak_pce_client/`), async (`aiohttp`) | ⏳ |
| 5 | **Custom component** v `custom_components/vak_pce/` (Config Flow s UI pro login, DataUpdateCoordinator, reauth, diagnostics) | ⏳ |
| 6 | Publikace přes **HACS** (vlastní repository) | ⏳ |
| 7 | (volitelně) PR do `home-assistant/core` jako oficiální integrace | ⏳ |

### Proč ne hned custom component

- Bez funkčního parseru by integrace byla jen prázdná kostra.
- HA core je celé asyncio – `requests` musí být přepsán na `aiohttp`. Má smysl
  to udělat jednou nad funkčním kódem, ne dvakrát.
- Custom component má významný boilerplate (`manifest.json`, `__init__.py`,
  `config_flow.py`, `coordinator.py`, `sensor.py`, `const.py`, `strings.json`,
  `translations/cs.json`, `hacs.json`). Bez funkčního klienta zbytečná zátěž.

### Co přinese fáze 5 (custom component) navíc oproti fázi 3 (skript)

- **Setup přes UI** – žádné editování YAML / `secrets.yaml`.
- Údaje uložené šifrovaně v `.storage/core.config_entries`.
- **Reauth flow** – při změně hesla HA samo vyzve uživatele.
- **DataUpdateCoordinator** – HA řeší interval, retry, timeouty, obnovu session.
- **Auto-discovery** víc odběrných míst, alarmů, atd.
- **Diagnostics** – stažení logu z UI, snadnější ladění bug reportů.
- **Distribuce přes HACS** – jeden klik instalace.

## Bezpečnostní pravidla

- Přihlašovací údaje **nikdy** v repu – `secrets.yaml` je v `.gitignore`,
  v Pythonu se čte z proměnných prostředí.
- `shell_command` v HA dostane údaje přes env proměnné (např. ze
  `secrets.yaml` injektnuté do příkazu).
- Skript musí mít **timeout** na HTTP a **retry s backoffem**.
- Při neúspěchu **neaktualizovat senzor** – jinak by `total_increasing`
  viděl skoky/poklesy.
- Rozumný `User-Agent` (ne default `python-requests/...`).

## Disclaimer

Tento projekt **není** oficiální nástroj společnosti Vodovody a kanalizace
Pardubice, a.s. ani žádného z jejích partnerů, dodavatelů či zástupců.
Jde o nezávislou komunitní integraci pro osobní použití.

- Integrace přistupuje na portál `zakaznik.vakpce.cz` jménem **přihlášeného
  uživatele s jeho vlastními platnými údaji** a čte výhradně data, ke kterým
  má tento uživatel přístup přes web.
- Frekvence dotazů je nastavena na **1× za hodinu**, aby nezatěžovala portál.
- Použití je **na vlastní zodpovědnost**. Provozovatel portálu může účet
  zablokovat za porušení svých podmínek užívání. Před nasazením doporučujeme
  si je projít.
- Název „VAK Pardubice“ a související označení jsou použity pouze popisně
  (nominative fair use). Logo, grafika ani jiné chráněné prvky provozovatele
  nejsou v projektu použity.

## Licence

Projekt je uvolněn pod licencí **MIT** – viz [LICENSE](LICENSE).

Stručně: smíš ho používat, upravovat i šířit (i komerčně), pokud zachováš
copyright + text licence. Bez záruky.

> Proč MIT: v ekosystému Home Assistanta je to nejčastější licence
> (HA core je Apache-2.0, většina komunitních integrací MIT). Je krátká,
> kompatibilní s prakticky čímkoli a nebrání případnému přijetí do
> `home-assistant/core` v budoucnu.
