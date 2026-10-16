#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np, matplotlib.pyplot as plt


def plot_data(data):
    if data is not None:
        plt.plot(data)
        plt.show()


# In[2]:


data = np.random.randn(100)
plot_data(data)

