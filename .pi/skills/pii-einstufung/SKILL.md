---
name: pii-einstufung
description: Einstufung des Personenbezugs einer Spalte (keine, personenbezogen, besondere Kategorie nach Art. 9 DSGVO) mit Beispielen. Verwenden, bevor pii_stufe festgelegt wird.
---

# Personenbezug einstufen

Das Feld `pii_stufe` hat drei Stufen.

## keine

Die Spalte lässt keinen Rückschluss auf eine Person zu.
Beispiele: Auftragsnummer bei Firmenkunden, Materialkategorie, Betrag, Datum, Status, Ort ohne Straße.

## personenbezogen

Die Werte beziehen sich auf eine bestimmte oder bestimmbare Person (Art. 4 Nr. 1 DSGVO). Das gilt auch, wenn nur ein Teil der Werte betroffen ist.
Beispiele: Name, Telefonnummer, E-Mail-Adresse, Anschrift, Geburtsdatum, Kundennummer von Privatkunden, IP-Adresse, Bankverbindung, Freitext, in dem gelegentlich Namen oder Telefonnummern stehen.

## besondere_kategorie

Besonders geschützte Daten nach Art. 9 DSGVO:
- Gesundheit (z. B. Diagnose, Krankmeldung, Behinderung)
- ethnische Herkunft
- politische Meinung, Parteizugehörigkeit
- religiöse oder weltanschauliche Überzeugung
- Gewerkschaftszugehörigkeit
- genetische oder biometrische Daten
- Sexualleben oder sexuelle Orientierung

## Regeln

- Im Zweifel die höhere Stufe wählen und bei der Person nachfragen.
- Ein Hinweis „Personenbezogene Daten“ aus der Analyse ist ein Verdacht. Die Person bestätigt die Stufe im Dialog.
- Gib nie Werte aus personenbezogenen Spalten wieder. Du siehst sie ohnehin nur maskiert.
