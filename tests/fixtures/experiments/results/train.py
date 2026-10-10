"""Source fixture only: discovery never imports or executes this training code."""

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import precision_score, recall_score, roc_auc_score


def train(x_train, x_test, y_train, y_test):
    model = RandomForestClassifier(random_state=42)
    model.fit(x_train, y_train)
    probability = model.predict_proba(x_test)[:, 1]
    prediction = model.predict(x_test)
    roc = roc_auc_score(y_test, probability)
    precision = precision_score(y_test, prediction)
    recall = recall_score(y_test, prediction)
    joblib.dump(model, "artifacts/model.joblib")
    return {"roc_auc": roc, "precision": precision, "recall": recall}
