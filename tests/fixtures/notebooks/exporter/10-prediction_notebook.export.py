#!/usr/bin/env python
# coding: utf-8

# In[ ]:


from sklearn.datasets import load_iris
from sklearn.linear_model import LogisticRegression


# In[ ]:


iris = load_iris()
X, y = iris.data, iris.target
model = LogisticRegression().fit(X, y)


# In[ ]:


def predict_species(data):
    return iris.target_names[model.predict([data])[0]]


# In[ ]:


predict_species([5.1, 3.5, 1.4, 0.2])

