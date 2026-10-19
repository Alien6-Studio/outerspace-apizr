import numpy as np
import pandas as pd
from sklearn.datasets import load_iris


class DataProcessor:
    def __init__(self, data):
        self.data = data

    def normalize(self):
        return (self.data - np.mean(self.data)) / np.std(self.data)


processor = DataProcessor(np.array([1, 2, 3, 4, 5]))
processor.normalize()
