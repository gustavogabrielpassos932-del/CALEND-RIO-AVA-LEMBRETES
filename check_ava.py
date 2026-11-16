import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DISCIPLINAS = {
    "110890047-04A20262": "Ciências Sociais Aplicadas ao Direito",
    "110900047-04A20262": "Direito Civil: Contratos",
    "110910047-04A20262": "Direito Penal: Crimes em Espécie",
    "110920047-04A20262": "Teoria Geral do Processo",
}

BRT = ZoneInfo("America/Sao_Paulo")


def fetch_ics(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_events(raw_ics: str):
    unfolded = re.sub(r"\r?\n[ \t]", "", raw_ics)
    blocks = unfolded.split("BEGIN:VEVENT")[1:]
    events = []
    for block in blocks:
        summary_m = re.search(r"SUMMARY:(.*)", block)
        cat_m = re.search(r"CATEGORIES:(.*)", block)
        dt_m = re.search(r"DTSTART(?:;[^:]*)?:(\d{8}T\d{6}Z?)", block)
        if not dt_m:
            continue

        summary = summary_m.group(1).strip() if summary_m else ""
        cat = cat_m.group(1).strip() if cat_m else ""
        dt_raw = dt_m.group(1).strip()

        dt = datetime.strptime(dt_raw.rstrip("Z"), "%Y%m%dT%H%M%S")
        if dt_raw.endswith("Z"):
            dt_local = dt.replace(tzinfo=timezone.utc).astimezone(BRT)
        else:
            dt_local = dt.replace(tzinfo=BRT)

        disciplina = DISCIPLINAS.get(cat, cat or "Disciplina")
        events.append((dt_local, disciplina, summary))

    events.sort(key=lambda x: x[0])
    return events


def send_ntfy(topic: str, title: str, message: str):
    url = f"https://ntfy.sh/{topic}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Title": title,
            "Priority": "default",
            "Tags": "books,alarm_clock",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.status


def main():
    ics_url = os.environ.get("AVA_ICS_URL", "").strip()
    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not ics_url or not ntfy_topic:
        print("Erro: defina AVA_ICS_URL e NTFY_TOPIC nas variaveis de ambiente.", file=sys.stderr)
        sys.exit(1)

    raw_ics = fetch_ics(ics_url)
    if "BEGIN:VCALENDAR" not in raw_ics:
        send_ntfy(ntfy_topic, "AVA UniEVANGELICA - Erro", f"Resposta inesperada do AVA: {raw_ics[:120]}")
        sys.exit(1)

    now = datetime.now(BRT)
    today = now.date()
    limit_7d = today + timedelta(days=7)

    events = [e for e in parse_events(raw_ics) if e[0].date() >= today]
    hoje = [e for e in events if e[0].date() == today]
    proximos7 = [e for e in events if today < e[0].date() <= limit_7d]

    lines = []
    if hoje:
        lines.append(f"VENCE HOJE ({today.strftime('%d/%m')}):")
        for dt, disc, summary in hoje:
            lines.append(f"- {dt.strftime('%H:%M')} | {disc}: {summary}")
    else:
        lines.append(f"Nada vence hoje ({today.strftime('%d/%m')}).")

    if proximos7:
        lines.append("")
        lines.append("Proximos 7 dias:")
        for dt, disc, summary in proximos7:
            lines.append(f"- {dt.strftime('%d/%m %H:%M')} | {disc}: {summary}")

    body = "\n".join(lines)
    print(body)
    status = send_ntfy(ntfy_topic, f"Prazos AVA - UniEVANGELICA ({now.strftime('%H:%M')})", body)
    print(f"Push enviado (HTTP {status}).")


if __name__ == "__main__":
    main()
