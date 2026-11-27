# PrintLater (Nederlands)

Start een Bambu Lab-print op een zelfgekozen tijd, bijvoorbeeld morgen om 07:30, terwijl
Bambu Handy en printen via de cloud blijven werken. Geen Developer Mode, geen firmware-aanpassing.

*Onofficieel hulpmiddel, niet verbonden aan Bambu Lab.*

## Installeren

Download `PrintLater-Setup-<versie>.exe` bij de
[nieuwste release](https://github.com/rgerr/printlater/releases/latest) en start het. Er zijn geen
beheerrechten nodig. De installer is niet ondertekend, dus Windows SmartScreen kan waarschuwen:
kies *Meer informatie* → *Toch uitvoeren*. Verwijderen gaat via Instellingen → Apps; je
instellingen blijven bewaard.

## Gebruik

1. Bambu Studio: slicen → pijltje naast *Printplaat* → **Exporteer plate sliced bestand**.
2. Rechtsklik op het `.gcode.3mf` → **Print inplannen...** (Windows 11: eerst *Meer opties weergeven*).
3. Kies datum, tijd en wat de tijd betekent: *de printer begint* (standaard), *de eerste laag begint*
   of *de print klaar is* (op basis van de schatting van Bambu, met 10 minuten marge).
4. Bambu Studio opent de kopie met wachtstart. Klik binnen ongeveer een minuut **Printplaat → Versturen**.

De printer neemt de opdracht direct aan en wacht koud tot de starttijd. De pc mag daarna uit.
Annuleren kan in Handy, Bambu Studio of op de printer.

## Vanuit een project en automatisch versturen

- Je kunt ook met rechts op een opgeslagen project (`.3mf`) klikken. PrintLater slicet de gekozen
  plaat dan zelf met Bambu Studio. Alleen wat is opgeslagen wordt gesliced. Een project voor een
  andere printer wordt geweigerd als `printer_model` in `config.toml` staat.
- Met het vinkje *Automatisch versturen* klikt PrintLater zelf op Printplaat en Versturen in Bambu
  Studio. Eerst zie je het bestand en het filament ter controle; Studio kiest zelf de AMS-sleuf.
  Lukt het niet, dan blijft het Studio-venster staan en verstuur je zelf. Dit is experimenteel.

## Let op

- Verstuur vanuit het juiste venster: PrintLater zet het Studio-venster met het bestand met
  wachtstart (titel eindigt op `_startHHMM`) vooraan. Was Studio al open, dan komt er een tweede
  venster bij.
- Het printbed moet op de starttijd leeg zijn.
- De printer staat aan tijdens het wachten; verwarming, ventilatoren en motoren staan uit.
- De kamerlamp is niet met G-code te bedienen: zet hem uit in Handy, of gebruik de
  Home Assistant-blueprint die dat automatisch doet.
- Stroomuitval tijdens het wachten annuleert de opdracht.
- De printer houdt maar één opdracht tegelijk vast. Is hij bezig, dan weigert PrintLater.

## Met Home Assistant

- Wat er gepland staat zie je in HA: naam, starttijd en status (gepland, wacht koud, gestart,
  mislukt).
- **Wachtrij:** met *In wachtrij* zet je een print in een takenlijst in HA. Is de printer klaar,
  dan krijg je een melding. Start > PrintLater > *Volgende uit de wachtrij inplannen* opent dan
  het venster voor de eerste print in de rij. Versturen doe je zelf in Bambu Studio.
- Is HA niet bereikbaar, dan plant PrintLater niet in, omdat het dan niet kan controleren of de
  printer vrij is. Met `continue_without_ha = true` plant hij toch.

Home Assistant, tijdsberekening en details: zie README.md.
