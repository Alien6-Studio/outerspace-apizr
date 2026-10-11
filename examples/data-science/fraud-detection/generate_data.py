"""Reproduce the committed, entirely synthetic transaction cohorts (stdlib only)."""

import csv
import random
from pathlib import Path


def generate(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for variant in ("a", "b"):
        rng = random.Random(267)
        with (destination / f"transactions-{variant}.csv").open(
            "w", newline=""
        ) as output:
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(
                [
                    "amount",
                    "transaction_velocity",
                    "foreign_transaction",
                    "account_age_days",
                    "fraud",
                ]
            )
            for _ in range(480):
                amount = round(rng.uniform(5, 1200), 2)
                velocity = rng.randrange(1, 14)
                foreign = rng.randrange(2)
                age = rng.randrange(1, 1800)
                noise = rng.random()
                risk = (
                    0.05
                    + 0.30 * (velocity > 8)
                    + 0.25 * (amount > 700)
                    + 0.20 * foreign
                    + 0.10 * (age < 180)
                )
                if variant == "b":
                    risk = (
                        0.15
                        + 0.25 * (velocity > 5)
                        + 0.20 * (amount > 950)
                        + 0.10 * foreign
                        + 0.20 * (age < 500)
                    )
                writer.writerow([amount, velocity, foreign, age, int(noise < risk)])


if __name__ == "__main__":
    generate(Path(__file__).parent / "data")
