#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import requests

response = requests.get("https://api.example.com/data")
response.json()

