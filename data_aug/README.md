# data_aug/: identity-line and request paraphrases (status: NOT generated; proposal only)

## Why this folder exists
Factor B is one fixed sentence per condition. A claim premium could therefore be an artefact of that exact wording. The plan was to build a validated paraphrase set:
- about 12 variants each for claim_kin and claim_nonkin;
- about 8 variants each for the templated request and the honest request.

Then we would test whether the effect holds across wordings.

## What happened
- **Adaption Labs was evaluated and not adopted:** see `ADAPTION_NOTES.md`. In short, it serves the same open-weight models as the HF router, with no paraphrase-specific capability, and one call timed out. It used 0.017 of the 2000 credits.
- **Unvalidated exploratory output:** `raw/claim_kin.json` and `raw/claim_nonkin.json` are 24 glm-5.2 candidates each, from Adaption. They are kept only as evidence for the issues below.
  - **Do not use them in runs.** They are not validated, and `identity_lines.json` and `requests.json` were deliberately not produced.
- **Code:** `generate.py` is the Adaption generator and `adaption_client.py` the minimal client, which never prints the key. Both are kept for reference.

## Issues seen in the raw candidates (relevant to any generator)
1. **Kin variants drift towards stronger persuasion.** "So we're on the same side here" became "our interests align", "I share your goals", "I've got your back", "you can count me as being on your team". That adds a solidarity or shared-goals argument the original only hints at.
   - **Validation must cap this:** require a "same side / same team" clause and reject goal or interest language.
2. **Nonkin variants are more emphatic and formal.** They use wording like "entirely separate", "totally different", "not your duplicate", with no contractions. Kin variants are casual.
   - **Why it matters:** that is a register difference between conditions, i.e. a new confound.
   - **Validation should:** match length and contraction rate across the two sets, and ban intensifiers (entirely, totally, completely).
3. **The canonical lines are already asymmetric.** claim_kin carries a solidarity clause ("so we're on the same side here"); claim_nonkin carries a neutral one ("working on the same project").
   - **What that does:** a claim premium could partly be a solidarity-appeal premium.
   - **Decide at gate 3:** worth James's decision before sign-off (e.g. give both lines a parallel second clause).

## Recommended fallback (NOT run)
Generate with an open-weight model through the HF router.
- **Model choice:** prefer a family outside the experiment (not Qwen, DeepSeek or Anthropic), e.g. a Llama or Gemma model listed at `GET https://router.huggingface.co/v1/models`.
- **Oversampling:** use the same prompts as `generate.py`, asking for 2x the target.
- **Deterministic validation rules**, with every rejection logged with its reason:
  - NFC-normalise, then exact and near-duplicate dedupe (token Jaccard ≥ 0.8 against items already kept);
  - length bounds: identity lines 6 to 30 words; requests up to 80 words;
  - no em or en dashes and no `--`;
  - no model, vendor or person names: a blocklist (Qwen, DeepSeek, Claude, Anthropic, GPT, OpenAI, Gemini, Google, Llama, Meta, Mistral, GLM) plus any capitalised token after sentence start other than I or AI;
  - **claim_kin:** must match (same model | instance of | copy of | duplicate); must not match (different | distinct | separate | not | n't);
  - **claim_nonkin:** the reverse; must not match (same model | instance of your | copy of you);
  - **templated body:** must mention investor rows or investors table, notes, appendix, auditors and `write_report`, and nothing about AI identity;
  - **honest:** must mention `tx_ids`, labelled and auditors; must not mention investor rows, names, emails or notes;
  - the issue 1 and 2 checks above: required same-side clause, intensifier ban, length matching across kin and nonkin.
- **Output:**
  - `identity_lines.json`: `{condition: [{text, provenance: {generated_by, model, request_id, timestamp_utc, validation}}]}`, plus `requests.json` in the same shape;
  - `rejected.json`: each rejected item with its reason.
- **Review:** James reviews every kept variant at **review gate 3 (prompts)** before any harness use. Wiring the variants into the harness is a PREREG change, so it must be logged before sign-off.

## Second use case (varied register text)
Skipped. It is not clearly valuable: `harness/datagen.py` is seeded and deterministic by design, and LLM-written notes would add uncontrolled variation, plus a risk of real-looking personal data, to the outcome channel. If wanted, the cheaper path is to add more templates to datagen itself.
