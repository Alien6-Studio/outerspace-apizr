import numpy as np, matplotlib.pyplot as plt


def plot_data(data):
    if data is not None:
        plt.plot(data)
        plt.show()


data = np.random.randn(100)
plot_data(data)
