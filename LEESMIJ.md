# PrintLater (Nederlands)

Start een Bambu Lab-print op een zelfgekozen tijd, bijvoorbeeld morgen om 07:30, terwijl
Bambu Handy en printen via de cloud blijven werken. Geen Developer Mode, geen firmware-aanpassing.

*Onofficieel hulpmiddel, niet verbonden aan Bambu Lab.*

## Gebruik

1. Bambu Studio: slicen → pijltje naast *Printplaat* → **Exporteer plate sliced bestand**.
2. Rechtsklik op het `.gcode.3mf` → **Print inplannen...** (Windows 11: eerst *Meer opties weergeven*).
3. Kies datum, tijd en wat de tijd betekent: *de printer begint* (standaard) of *de eerste laag begint*.
4. Bambu Studio opent de kopie met wachtstart. Klik binnen ongeveer een minuut **Printplaat → Versturen**.

De printer neemt de opdracht direct aan en wacht koud tot de starttijd. De pc mag daarna uit.
Annuleren kan in Handy, Bambu Studio of op de printer.

## Let op

- Het printbed moet op de starttijd leeg zijn.
- De printer staat aan tijdens het wachten; verwarming, ventilatoren en motoren staan uit.
- De kamerlamp is niet met G-code te bedienen: zet hem uit in Handy, of gebruik de
  Home Assistant-blueprint die dat automatisch doet.
- Stroomuitval tijdens het wachten annuleert de opdracht.

Installatie en details: zie README.md.
