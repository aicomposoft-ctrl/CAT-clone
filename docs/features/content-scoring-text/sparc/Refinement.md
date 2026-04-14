# Refinement — Content Scoring: Text (multilingual-e5)

---

## Edge Cases

| Scenario | Expected Behaviour |
|----------|--------------------|
| composition IS NULL for SKU | Skip comp scoring; still score desc; content_total only if all 3 non-NULL |
| Empty description after strip() | Skip desc scoring; log info |
| ref_emb:desc missing, ref_emb:comp present | Score comp only; desc_score stays NULL |
| image_score still NULL at 06:30 UTC | content_total stays NULL; text scores still written |
| Duplicate orchestrator run (idempotent) | Filter excludes already-scored rows; 0 tasks dispatched |
| Very long description (>512 tokens) | Truncated by tokenizer at max_length=512 |
| Unicode/emoji in text | e5-base handles multilingual natively |
| description = whitespace only | strip() → empty → skip |
| ref_emb shape (512,) accidentally stored as desc key | get_embedding shape check → returns None → skip |

---

## Test List (unit)

| # | Test | Scope |
|---|------|-------|
| 1 | Happy path: both desc and comp scored, content_total computed | score_text_content |
| 2 | description_score written correctly (cosine sim value) | score_text_content |
| 3 | composition_score written correctly | score_text_content |
| 4 | content_total = 0.40*img + 0.35*desc + 0.25*comp | score_text_content |
| 5 | content_total only written if all 3 scores non-NULL | score_text_content |
| 6 | content_total NOT written if image_score IS NULL | score_text_content |
| 7 | composition IS NULL → skip comp, desc still scored | score_text_content |
| 8 | Empty description → skip desc, no DB write for desc_score | score_text_content |
| 9 | ref_emb:desc missing → skip desc, comp still scored | score_text_content |
| 10 | ref_emb:comp missing → skip comp, desc still scored | score_text_content |
| 11 | Both ref_embs missing → nothing written, no crash | score_text_content |
| 12 | Stale cs_id (deleted row) → log warning, no crash | score_text_content |
| 13 | Cross-tenant isolation: SKU-A reads only its Redis keys | score_text_content |
| 14 | Score clamped to [0.0, 1.0] | score_text_content |
| 15 | Score rounded to 2 decimal places | score_text_content |
| 16 | Orchestrator dispatches N tasks for N unscored rows | score_text_content_all |
| 17 | Orchestrator: fully-scored rows excluded from query | score_text_content_all |
| 18 | Orchestrator: 0 rows → no group dispatched (idempotent) | score_text_content_all |
| 19 | E5 singleton: model loaded only once per process | e5_model |
| 20 | encode_text prepends "query: " prefix | e5_model |
| 21 | encode_text returns shape (768,) | e5_model |
| 22 | encode_text returns L2-normalized vector (norm ≈ 1.0) | e5_model |
| 23 | Zero-norm embedding → ValueError, task skips that field | e5_model |
| 24 | Redis wrong-shape embedding (512,) → None returned | redis_client |
| 25 | Pickle wrong type → None returned | redis_client |
