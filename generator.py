import argparse
import csv
import json
import os
import random
import time
from datetime import datetime, timezone

from azure.servicebus import ServiceBusClient, ServiceBusMessage


FIELDS = [
    "match_id",
    "round_number",
    "player_id",
    "timestamp",
    "team",
    "rounds_played",
    "shots_fired_round",
    "hits_round",
    "headshots_round",
    "accuracy_round",
    "headshot_accuracy_round",
    "kills_round",
    "deaths_round",
    "assists_round",
    "damage_this_round",
    "cum_kills",
    "cum_deaths",
    "cum_assists",
    "cum_damage",
]


def generate_csv(
    csv_path: str,
    matches: int,
    rounds_min: int,
    rounds_max: int,
    players_per_match: int,
) -> None:
    total_rows = 0

    with open(csv_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()

        for match_id in range(1, matches + 1):
            rounds = random.randint(rounds_min, rounds_max)
            player_ids = [
                random.randint(100000, 999999) for _ in range(players_per_match)
            ]
            cumulative = {
                player_id: {
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "damage": 0.0,
                    "rounds_played": 0,
                }
                for player_id in player_ids
            }

            for round_number in range(1, rounds + 1):
                for player_id in player_ids:
                    shots = random.randint(1, 50)
                    hits = random.randint(0, shots)
                    headshots = random.randint(0, hits)
                    kills = random.randint(0, 5)
                    deaths = random.randint(0, 1)
                    assists = random.randint(0, 3)
                    damage = round(random.uniform(0, 100), 2)
                    stats = cumulative[player_id]
                    stats["kills"] += kills
                    stats["deaths"] += deaths
                    stats["assists"] += assists
                    stats["damage"] += damage
                    stats["rounds_played"] += 1

                    writer.writerow(
                        {
                            "match_id": match_id,
                            "round_number": round_number,
                            "player_id": player_id,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "team": random.choice(["A", "B"]),
                            "rounds_played": stats["rounds_played"],
                            "shots_fired_round": shots,
                            "hits_round": hits,
                            "headshots_round": headshots,
                            "accuracy_round": round(hits / shots, 2),
                            "headshot_accuracy_round": round(
                                headshots / hits if hits else 0,
                                2,
                            ),
                            "kills_round": kills,
                            "deaths_round": deaths,
                            "assists_round": assists,
                            "damage_this_round": damage,
                            "cum_kills": stats["kills"],
                            "cum_deaths": stats["deaths"],
                            "cum_assists": stats["assists"],
                            "cum_damage": round(stats["damage"], 2),
                        }
                    )
                    total_rows += 1

    print(f"CSV '{csv_path}' mit {total_rows} Zeilen erzeugt.")


def load_matches(csv_path: str) -> list[list[dict[str, str]]]:
    matches: dict[str, list[dict[str, str]]] = {}

    with open(csv_path, mode="r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            matches.setdefault(row["match_id"], []).append(row)

    return list(matches.values())


def send_matches(
    matches: list[list[dict[str, str]]],
    connection_string: str,
    queue_name: str,
    rate_per_second: int,
    duration_seconds: int,
) -> None:
    message_count = rate_per_second * duration_seconds
    pause = 1.0 / rate_per_second

    with ServiceBusClient.from_connection_string(connection_string) as client:
        with client.get_queue_sender(queue_name=queue_name) as sender:
            for index in range(message_count):
                match = matches[index % len(matches)]
                sender.send_messages(ServiceBusMessage(json.dumps(match)))
                time.sleep(pause)

    print(f"{message_count} Matchnachrichten versendet.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simuliert Matchdaten und sendet sie an Azure Service Bus."
    )
    parser.add_argument("--csv-path", default="generated_matches.csv")
    parser.add_argument("--matches", type=int, default=120)
    parser.add_argument("--rounds-min", type=int, default=10)
    parser.add_argument("--rounds-max", type=int, default=30)
    parser.add_argument("--players", type=int, default=10)
    parser.add_argument("--rate", type=int, default=6)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument(
        "--connection-string",
        default=os.getenv("SERVICEBUS_CONNECTION_STRING"),
    )
    parser.add_argument("--queue-name", required=True)
    args = parser.parse_args()

    if not args.connection_string:
        raise SystemExit("SERVICEBUS_CONNECTION_STRING ist nicht gesetzt.")
    if args.rate <= 0 or args.duration <= 0:
        raise SystemExit("Rate und Dauer müssen größer als 0 sein.")
    if args.rounds_min > args.rounds_max:
        raise SystemExit("rounds-min darf rounds-max nicht überschreiten.")

    generate_csv(
        args.csv_path,
        args.matches,
        args.rounds_min,
        args.rounds_max,
        args.players,
    )
    matches = load_matches(args.csv_path)
    send_matches(
        matches,
        args.connection_string,
        args.queue_name,
        args.rate,
        args.duration,
    )


if __name__ == "__main__":
    main()
