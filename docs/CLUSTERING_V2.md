# Clustering: Algorithm, Thresholds, and v2 Embeddings

## v1: Jaccard Similarity (current)

### Algorithm

1. **Tokenize** Hebrew titles: extract tokens matching `[^\u05D0-\u05EAa-zA-Z0-9]+` as delimiter
2. **Filter** 73 common Hebrew stopwords (ה, ל, ב, מ, ו, ש, את, של, הוא, היא, …)
3. **Lowercase** Latin characters only; Hebrew tokens are left as-is
4. **Compute Jaccard**: `|A ∩ B| / |A ∪ B|` on token sets
5. **Threshold**: similarity **strictly greater than 0.25** — items above this join the same story
6. **Time window**: only compare items within the last **24 hours**

### Implementation

```
cluster/tokens.py   — tokenize(), jaccard_similarity()
cluster/cluster.py  — cluster_new_items(db, items) → ClusterCounters
```

### Performance

- ~500 items/second on Ryzen 7 PRO 3700
- No GPU required, no external dependencies

### Tuning

| Parameter | Default | Notes |
|-----------|---------|-------|
| JACCARD_THRESHOLD | 0.25 | Lower = more aggressive merging |
| CLUSTER_WINDOW_HOURS | 24 | Items older than this start new stories |

Changing the threshold requires re-running clustering on existing items
(`UPDATE stories SET state='draft'; DELETE FROM story_items;` then restart).

---

## v2: Embeddings + Cosine Similarity (PATCH-09)

### Motivation

Jaccard fails when:
- Two articles cover the same event but use different Hebrew phrasing
- Transliterations differ (Russian vs English proper nouns in headlines)
- Short headlines with few shared tokens despite same topic

### Algorithm

1. Generate embedding for each item title using Ollama embedding model
2. Compute cosine similarity between new item and all story centroids (last 24h)
3. If cosine ≥ 0.75: merge into existing story
4. Else: fall back to Jaccard (threshold 0.25)

### Embedding Model

Default: `nomic-embed-text` (768 dimensions, pulled via `ollama pull nomic-embed-text`)

### Implementation (PATCH-09)

```
cluster/embeddings.py   — EmbeddingClient.embed(), cosine_similarity()
cluster/cluster_v2.py   — hybrid: cosine → Jaccard fallback
cluster/eval.py         — evaluate_clustering() → precision/recall/F1
db schema               — item_embeddings table (already in schema)
```

### Eval Harness

Labeled pairs in `tests/fixtures/cluster_eval_pairs.json`:
```json
[
  {"item_a": "key1", "item_b": "key2", "same_story": true},
  ...
]
```

Metrics: precision, recall, F1 computed against human labels.

### Comparison

| Metric | Jaccard (v1) | Embeddings (v2) |
|--------|-------------|-----------------|
| Speed | ~500 items/s | ~50 items/s (GPU) |
| Memory | O(1) | O(n × dim) |
| Cross-phrasing | Poor | Good |
| GPU required | No | Optional (faster) |
| Dependencies | None | numpy, Ollama |

---

## Stopwords (73 total)

Full list in `cluster/tokens.py`. Selected examples:

```
ה, ל, ב, מ, ו, ש, כ, מי, מה, אבל, כי, עם, על, זה, זאת,
כל, אם, לא, יש, אין, כן, רק, עוד, כבר, גם, גם, אבל,
הוא, היא, הם, הן, אנחנו, אתם, אני, אתה, את, זו, זה
```
