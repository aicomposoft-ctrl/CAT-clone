# Pseudocode — Content Scoring: Text (multilingual-e5)

---

## Algorithm 1: score_text_content_all (orchestrator)

```
TASK score_text_content_all() → None
  # Celery Beat: 06:30 UTC daily

  today ← date.today()
  rows ← DB.query(
    ContentScore.id,
    SKUPlatform.sku_id,
    ContentScore.collected_description,
    ContentScore.collected_composition,
  ).join(SKUPlatform)
   .filter(
     ContentScore.scored_at == today,
     ContentScore.collected_description IS NOT NULL,
     OR(
       ContentScore.description_score IS NULL,
       AND(
         ContentScore.collected_composition IS NOT NULL,
         ContentScore.composition_score IS NULL,
       )
     )
   ).all()

  IF len(rows) == 0: RETURN

  group(
    score_text_content.s(
      str(row.id), str(row.sku_id),
      row.collected_description, row.collected_composition
    )
    FOR row IN rows
  ).delay()

  NOTE: Filter logic: dispatch if description unscored OR
        composition exists but unscored. Avoids re-dispatching
        fully-scored rows on duplicate orchestrator runs.
```

---

## Algorithm 2: score_text_content (per-row)

```
TASK score_text_content(cs_id, sku_id, description, composition) → None
  max_retries=3, bind=True

  scores_to_write ← {}

  # ── Description scoring ─────────────────────────────────────────
  IF description IS NOT NULL AND strip(description) != "":
    ref_desc ← redis.get_embedding(sku_id, field="desc")
    IF ref_desc IS None:
      log.warning("no ref_emb desc for sku_id={}")
    ELSE:
      collected_desc_emb ← e5_model.encode_text(description)
      # encode_text: prefix "query: " + tokenize + CLS + L2-normalize
      score_desc ← clamp(dot(collected_desc_emb, ref_desc), 0.0, 1.0)
      scores_to_write["description_score"] ← round(score_desc, 2)
  ELSE:
    log.info("empty description for cs_id={} — skip desc")

  # ── Composition scoring ──────────────────────────────────────────
  IF composition IS NOT NULL AND strip(composition) != "":
    ref_comp ← redis.get_embedding(sku_id, field="comp")
    IF ref_comp IS None:
      log.warning("no ref_emb comp for sku_id={}")
    ELSE:
      collected_comp_emb ← e5_model.encode_text(composition)
      score_comp ← clamp(dot(collected_comp_emb, ref_comp), 0.0, 1.0)
      scores_to_write["composition_score"] ← round(score_comp, 2)
  ELSE:
    log.info("no/empty composition for cs_id={} — skip comp")

  IF len(scores_to_write) == 0: RETURN  # nothing to write

  # ── content_total (computed only if all 3 present) ───────────────
  # Re-read current image_score + merge with new scores
  WITH DB.session() as db:
    row ← db.query(ContentScore.image_score, ContentScore.description_score,
                   ContentScore.composition_score)
           .filter(ContentScore.id == cs_id).first()
    IF row IS None:
      log.warning("cs_id={} deleted — skip write"); RETURN

    image_score = row.image_score  # may be NULL if image scoring not done yet
    new_desc = scores_to_write.get("description_score", row.description_score)
    new_comp = scores_to_write.get("composition_score", row.composition_score)

    IF image_score IS NOT NULL AND new_desc IS NOT NULL AND new_comp IS NOT NULL:
      scores_to_write["content_total"] ← round(
        0.40 * image_score + 0.35 * new_desc + 0.25 * new_comp, 2
      )

    db.execute(
      UPDATE content_scores
      SET   {**scores_to_write}
      WHERE id = cs_id
    )

  log.info("score_text_content done cs_id={} scores={}")
```

---

## Algorithm 3: encode_text (E5 singleton)

```
MODULE e5_model

  _model ← None  # AutoModel | None
  _tokenizer ← None
  _MODEL_ID = "intfloat/multilingual-e5-base"

  FUNCTION _load():
    IF _model IS None:
      _tokenizer ← AutoTokenizer.from_pretrained(_MODEL_ID)
      _model ← AutoModel.from_pretrained(_MODEL_ID)
      _model.eval()

  FUNCTION encode_text(text: str) → np.ndarray:
    """
    Encode text with multilingual-e5-base.
    Prepends "query: " prefix (e5 query-document protocol).
    Returns L2-normalized CLS embedding, shape (768,).
    """
    _load()
    prefixed = "query: " + text
    inputs = _tokenizer(
      prefixed, return_tensors="pt",
      truncation=True, max_length=512, padding=True
    )
    WITH torch.no_grad():
      outputs = _model(**inputs)
      emb = outputs.last_hidden_state[:, 0, :]  # CLS token [1, 768]
      emb = emb / emb.norm(dim=-1, keepdim=True)  # L2 normalize
    vec = emb.squeeze().numpy()  # shape (768,)
    IF norm(vec) < 1e-8:
      RAISE ValueError("zero-norm text embedding")
    RETURN vec
```

---

## Error Handling Matrix

| Error | Action |
|-------|--------|
| ref_emb missing (desc) | log warning, skip desc, still score comp |
| ref_emb missing (comp) | log warning, skip comp, still score desc |
| Empty collected_description | log info, skip desc |
| NULL collected_composition | skip comp (expected for many SKUs) |
| Zero-norm embedding | log error, skip that field |
| DB row deleted (race) | log warning, return |
| Redis transient error | get_embedding returns None → skip field |
| DB UPDATE fails | retry (max 3, countdown=2^attempt) |
