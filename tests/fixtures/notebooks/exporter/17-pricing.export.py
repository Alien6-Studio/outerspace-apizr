#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import json
from pathlib import Path


def load_prices():
    return json.loads((Path(__file__).parent / "data" / "prices.json").read_text())


# In[ ]:


def quote(product: str, quantity: int = 1) -> float:
    return float(load_prices()[product] * quantity)

