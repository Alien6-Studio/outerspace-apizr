"""Feature order shared by the saved model and ordinary prediction code."""


def _feature_row(
    amount: float,
    transaction_velocity: int,
    foreign_transaction: bool,
    account_age_days: int,
) -> list[float]:
    return [
        amount,
        float(transaction_velocity),
        float(foreign_transaction),
        float(account_age_days),
    ]
