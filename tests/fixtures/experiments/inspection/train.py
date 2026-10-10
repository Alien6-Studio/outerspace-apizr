"""Small illustrative fraud experiment; inspection must never execute this file."""

from typing import TypedDict

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, roc_auc_score

learning_rate = 0.05
max_depth = 8
n_estimators = 200
model_name = "fraud-rf"

training = pd.read_csv("data/train.csv")
validation = pd.read_parquet(DATA_PATH)
remote = pd.read_parquet("s3://examples/validation.parquet")
np.random.seed(42)
unseeded = np.random.default_rng()
model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
model.fit(training[["amount"]], training["fraud"])
predictions = model.predict(validation[["amount"]])
roc_auc_score(validation["fraud"], predictions)
precision_score(validation["fraud"], predictions)
joblib.dump(model, "artifacts/fraud.joblib")


class PredictionInput(TypedDict):
    amount: float


def predict(payload: PredictionInput) -> float:
    return float(model.predict([[payload["amount"]]])[0])


raise RuntimeError("inspection executed the source")
