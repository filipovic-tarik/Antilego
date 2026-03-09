import requests
import pandas as pd
import json


url = "https://gamma-api.polymarket.com/markets"
params = {"limit": 200}

response = requests.get(url, params=params, timeout=30)
print(response.status_code)
data = response.json()

type(data), len(data)


records = []

for m in data:
    records.append({
        "id": m.get("id"),
        "question": m.get("question"),
        "endDate": m.get("endDate"),
        "category": m.get("category"),
        "active": m.get("active"),
        "closed": m.get("closed"),
        "volume": m.get("volumeNum"),
        "liquidity": m.get("liquidityNum"),
        "outcomes": m.get("outcomes"),
        "prices": m.get("outcomePrices")
    })

df = pd.DataFrame(records)
df.head(20)


open_df = df[(df["active"] == True) & (df["closed"] == False)]
df[["active", "closed"]].value_counts()


df[["question", "endDate", "active", "closed", "volume"]].tail(20)


url = "https://gamma-api.polymarket.com/markets"
params = {
    "limit": 200,
    "closed": "false"
}

response = requests.get(url, params=params, timeout=30)
print(response.status_code)

data = response.json()
len(data), data[0]


records = []

for m in data:
    records.append({
        "id": m.get("id"),
        "question": m.get("question"),
        "endDate": m.get("endDate"),
        "category": m.get("category"),
        "active": m.get("active"),
        "closed": m.get("closed"),
        "volume": m.get("volumeNum"),
        "liquidity": m.get("liquidityNum"),
        "outcomes": m.get("outcomes"),
        "prices": m.get("outcomePrices")
    })

df = pd.DataFrame(records)
df[["question", "endDate", "active", "closed", "volume"]].head(30)






