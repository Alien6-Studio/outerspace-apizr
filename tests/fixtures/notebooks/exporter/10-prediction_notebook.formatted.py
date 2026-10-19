from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression

iris = load_iris()
X, y = iris.data, iris.target
model = LogisticRegression().fit(X, y)


def predict_species(data):
    return iris.target_names[model.predict([data])[0]]


predict_species([5.1, 3.5, 1.4, 0.2])
