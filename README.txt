PAINTMASTER PRO
===============
Tekent een afbeelding met echte muisbewegingen na in Microsoft Paint.
De afbeelding wordt NOOIT geplakt: ze wordt omgezet naar lijnen (contouren, kleurvlakken, arceringen)
die met de muis in Paint worden getekend.

EXE BOUWEN (eenmalig)
1. Installeer Python 3.10+ van python.org (vink "Add Python to PATH" aan).
2. Dubbelklik build.bat. Resultaat: dist\PaintMasterPro.exe (Python is daarna niet meer nodig).
Zonder bouwen starten: pip install -r requirements.txt  en dan  python main.py

GEBRUIK
1. Open PaintMaster Pro, kies of sleep een afbeelding (PNG/JPG/JPEG/BMP/WEBP). Optioneel bijsnijden bij Instellingen.
2. Kies tekenmodus, snelheid en detailniveau. Klik "Analyseer / preview": rechts zie je het verwachte resultaat.
3. Open Paint (knop "Paint openen") en kies het Paint-venster in de lijst. Zet in Paint het gereedschap op Potlood
   of Penseel en kies je gewenste dikte (zet dezelfde dikte bij "Lijndikte" in Instellingen). Zoom 100%.
4. KALIBREREN (eenmalig per Paint-venster/positie): klik "Kalibreren" en volg de 5 stappen met F8:
   linksboven en rechtsonder van het witte tekenvlak, eerste kleurvakje (zwart, linksboven in het palet),
   laatste kleurvakje (rechtsonder in het palet, 2 rijen x 10), en het gereedschap-knopje.
   Hierdoor werkt het op elke schermresolutie en Windows-schaling zonder vaste coordinaten.
5. Klik Start. Verplaats of sluit Paint niet tijdens het tekenen.

BESTURING
Start / Pauze (F6) / Hervat (F7) / Stop / Noodstop (ESC). Sneltoetsen zijn instelbaar.
Na pauze of stop gaat het tekenen verder vanaf de laatst voltooide lijnstap (niet opnieuw vanaf het begin).
Projecten worden automatisch opgeslagen (Geschiedenis > Project openen) en kunnen zonder opnieuw analyseren worden hervat.
Gegevens staan in %APPDATA%\PaintMasterPro (instellingen, projecten, historie, log.txt).

BEPERKINGEN (eerlijk)
- Kleuren: Paint's standaardpalet (20 kleuren) wordt gebruikt; afbeeldingen worden daar naartoe gekwantiseerd.
  Volgorde van het palet is de standaard van Windows 10/11 Paint (zwart, grijs, donkerrood, rood, ...).
- Paint-onderdelen worden via jouw kalibratie aangeklikt. Verkeerd gereedschap kan het programma niet uitlezen;
  het gereedschap wordt wel bij start, kleurwissel en hervatten opnieuw aangeklikt.
- Schaduwniveau werkt in Artist Mode (arcering). Verplaatst/minimaliseert/sluit je Paint of klik je ergens anders,
  dan pauzeert het programma met een melding.
