# Datenmodell

## 1. Nachricht im Service Bus

Eine Service-Bus-Nachricht enthält ein vollständiges Match als JSON-Array. Ein
Arrayelement beschreibt die Statistik eines Spielers in einer Runde.

```json
[
  {
    "match_id": "1",
    "round_number": "1",
    "player_id": "483921",
    "timestamp": "2026-10-26T12:00:00+00:00",
    "team": "A",
    "rounds_played": "1",
    "shots_fired_round": "24",
    "hits_round": "13",
    "headshots_round": "4",
    "accuracy_round": "0.54",
    "headshot_accuracy_round": "0.31",
    "kills_round": "3",
    "deaths_round": "1",
    "assists_round": "2",
    "damage_this_round": "78.5",
    "cum_kills": "3",
    "cum_deaths": "1",
    "cum_assists": "2",
    "cum_damage": "78.5"
  }
]
```

Da die Nachricht aus einer CSV-Datei eingelesen wird, liegen die Werte beim
Versand als Strings vor. Pandas wandelt die numerischen Spalten bei der
Aufbereitung für das Modell wieder in geeignete Zahlentypen um.

## 2. Feldgruppen

### 2.1 Identifikation und Kontext

| Feld | Bedeutung |
| --- | --- |
| `match_id` | Identifikation des simulierten Matches |
| `round_number` | laufende Runde innerhalb des Matches |
| `player_id` | Identifikation des Spielers |
| `timestamp` | UTC-Zeitpunkt der Datenerzeugung |
| `team` | Teamzuordnung `A` oder `B` |
| `rounds_played` | bisher gespielte Runden des Spielers im Match |

### 2.2 Aktuelle Rundenwerte

| Feld | Bedeutung |
| --- | --- |
| `shots_fired_round` | abgegebene Schüsse |
| `hits_round` | Treffer |
| `headshots_round` | Kopftreffer |
| `accuracy_round` | Treffer geteilt durch abgegebene Schüsse |
| `headshot_accuracy_round` | Kopftreffer geteilt durch Treffer |
| `kills_round` | Eliminierungen in der Runde |
| `deaths_round` | eigene Tode in der Runde |
| `assists_round` | Unterstützungen in der Runde |
| `damage_this_round` | verursachter Schaden in der Runde |

### 2.3 Kumulierte Werte

| Feld | Bedeutung |
| --- | --- |
| `cum_kills` | bisherige Eliminierungen im Match |
| `cum_deaths` | bisherige Tode im Match |
| `cum_assists` | bisherige Unterstützungen im Match |
| `cum_damage` | bisher verursachter Gesamtschaden |

Die kumulierten Werte geben dem Modell Kontext für die Bewertung kurzfristiger
Leistungsspitzen. Ein hoher Einzelwert kann dadurch im Verhältnis zum bisherigen
Verlauf betrachtet werden.

## 3. Feature-Datei für Azure ML

Vor dem Upload entfernt die Function reine Identifikations- und Kontextfelder.
Die CSV für den Batch Endpoint enthält diese 15 Features in fester Reihenfolge:

```text
round_number
rounds_played
shots_fired_round
hits_round
headshots_round
accuracy_round
headshot_accuracy_round
kills_round
deaths_round
assists_round
damage_this_round
cum_kills
cum_deaths
cum_assists
cum_damage
```

Die Reihenfolge muss mit dem Schema übereinstimmen, mit dem das Modell trainiert
wurde.

## 4. Ausgabe des ML-Modells

Das Scoring-Skript gibt pro Eingabezeile folgende Informationen zurück:

| Feld | Bedeutung |
| --- | --- |
| `file` | Name der verarbeiteten Feature-Datei |
| `row` | Zeilenindex innerhalb der Datei |
| `prediction` | vom Modell gelieferte Klasse |

Die Function interpretiert die Vorhersage als Ganzzahl. Die genaue Bedeutung
der Klassen muss gemeinsam mit dem eingesetzten Modell versioniert werden; in
einer binären Konfiguration steht typischerweise eine Klasse für unauffälliges
und die andere für auffälliges Verhalten.

## 5. Dokument in Cosmos DB

Vor der Speicherung ergänzt die Function die ursprünglichen Modellmerkmale um:

| Feld | Bedeutung |
| --- | --- |
| `id` | neue UUID für das Cosmos-DB-Dokument |
| `player_id` | Zuordnung der Vorhersage zum Spieler |
| `prediction` | Klassifikation des ML-Modells |

Nicht vorhandene Pandas-Werte werden als `null` gespeichert. Für eine spätere
Erweiterung empfehlen sich zusätzlich `match_id`, ein Modellname mit Version,
eine Batch-ID und der Zeitpunkt der Inferenz.
