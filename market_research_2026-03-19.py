from duckduckgo_search import DDGS
import json
from datetime import datetime

queries = [
    {"type": "news", "q": "Nifty Sensex closing latest India stock market March 18 OR yesterday close FII DII", "timelimit": "d", "max": 20},
    {"type": "text", "q": "Nifty 50 Sensex close price FII DII net flows India VIX yesterday", "timelimit": "d", "max": 15},
    {"type": "news", "q": "overnight global cues US futures Asia markets open crude oil rupee USDINR latest", "timelimit": "d", "max": 20},
    {"type": "text", "q": "Nifty Bank Nifty technical analysis support resistance levels PCR OI F&O cues today", "timelimit": "d", "max": 15},
    {"type": "news", "q": "India earnings calendar IPO corporate actions ex-dividend March 19 2026 OR upcoming", "timelimit": "w", "max": 15},
    {"type": "text", "q": "India VIX latest value change F&O open interest PCR", "timelimit": "d", "max": 10},
    {"type": "text", "q": "Nifty pre open indication Sensex premarket India latest", "timelimit": "d", "max": 10},
    {"type": "news", "q": "sector performance banking IT auto pharma energy yesterday India markets", "timelimit": "d", "max": 15}
]

data = {}
for i, q in enumerate(queries):
    print(f"Query {i+1}: {q['q']}")
    with DDGS() as ddgs:
        if q['type'] == 'news':
            results = list(ddgs.news(q['q'], timelimit=q.get('timelimit'), max_results=q['max']))
        else:
            results = list(ddgs.text(q['q'], timelimit=q.get('timelimit'), max_results=q['max']))
    data[q['q'][:50] + '...'] = results
    print(f"Found {len(results)} results\\n")

timestamp = datetime.now().isoformat()
with open('/root/.openclaw/workspace/market_data_2026-03-19.json', 'w') as f:
    json.dump({"timestamp": timestamp, "queries": data}, f, indent=2)
print("Data saved to market_data_2026-03-19.json")
