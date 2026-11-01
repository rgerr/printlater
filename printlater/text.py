"""User-facing text in English and Dutch."""

T = {
    "en": {
        "menu": "Print later...",
        "title": "Print later",
        "date": "Date", "time": "Time", "today": "Today", "tomorrow": "Tomorrow",
        "meaning": "The time is when",
        "m_warmup": "the printer starts (heating, homing)",
        "m_printing": "the first layer starts",
        "bed": "The build plate must be empty at that time.",
        "plan": "Plan", "cancel": "Cancel", "close": "Close",
        "info": "{plates} plate(s), about {dur}, {grams} g {mat}",
        "busy": "The printer is busy ({state}). Send the delayed file once it is free.",
        "power": "Switching the printer on...",
        "made": "Delayed file created and opened in Bambu Studio.",
        "send_now": "Now press Print plate, then Send.\nThe start time is calculated for sending within about {lead} s.",
        "waiting": "Waiting for the printer to accept the job...",
        "accepted": "Accepted at {run}.\nPrinter starts at {start}{dev}.",
        "dev": " ({sign}{m} min {s} s compared with the plan)",
        "no_confirm": "No confirmation from Home Assistant. If you sent the job, the printer starts about {start}.",
        "ha_fail": "Home Assistant not reachable: {err}\nContinuing without it.",
        "err": "Not planned",
    },
    "nl": {
        "menu": "Print inplannen...",
        "title": "Print inplannen",
        "date": "Datum", "time": "Tijd", "today": "Vandaag", "tomorrow": "Morgen",
        "meaning": "Dit tijdstip is wanneer",
        "m_warmup": "de printer begint (opwarmen, homing)",
        "m_printing": "de eerste laag begint",
        "bed": "Het printbed moet op dat moment leeg zijn.",
        "plan": "Inplannen", "cancel": "Annuleren", "close": "Sluiten",
        "info": "{plates} plaat/platen, ca. {dur}, {grams} g {mat}",
        "busy": "De printer is bezig ({state}). Verstuur het bestand als hij vrij is.",
        "power": "Printer wordt aangezet...",
        "made": "Bestand met wachtstart gemaakt en geopend in Bambu Studio.",
        "send_now": "Klik nu Printplaat en daarna Versturen.\nDe starttijd is berekend op versturen binnen ongeveer {lead} s.",
        "waiting": "Wachten tot de printer de opdracht aanneemt...",
        "accepted": "Aangenomen om {run}.\nPrinter begint om {start}{dev}.",
        "dev": " ({sign}{m} min {s} s t.o.v. de planning)",
        "no_confirm": "Geen bevestiging van Home Assistant. Als je hebt verstuurd, begint de printer rond {start}.",
        "ha_fail": "Home Assistant niet bereikbaar: {err}\nIk ga verder zonder.",
        "err": "Niet ingepland",
    },
}


def tr(lang: str, key: str, **kw) -> str:
    return T.get(lang, T["en"])[key].format(**kw)
