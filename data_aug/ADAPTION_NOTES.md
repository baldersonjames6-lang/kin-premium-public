# Adaption Labs: API notes and verdict (6 Nov 2026)

## Verdict: not used for the paraphrase sets
For this job Adaption is no better than an open-weight model via the HF router, and it is slightly worse:
- **Same models:** its text endpoint (Responses API) just serves open-weight models (GLM, Qwen, DeepSeek, Gemma). There is no paraphrase or "keep the meaning" feature.
- **No useful data products:** the Adaptive Data products (adapt, augment, invent) build SFT or DPO training datasets with row-based billing. They are the wrong tool for 40 short, controlled sentences.
- **Unreliable:** the third generation call returned an HTTP 504 gateway timeout. Other calls took 22 s and 51 s.

James said not to use it for the sake of it, so we stopped. Recommendation: use the HF router fallback (below).

## What was tested
- **Key:** works. `GET /api/v1/models?type=hosted` returned 200.
  - Hosted models: glm-5.2, qwen3.5-397b, gemma-4-26b-a4b-it, qwen3.8-27b, deepseek-v4-flash, gemma-4-31b-it.
- **Credits:** 2000 before, 1999.9827 after. Total spent about **0.017 credits**:
  - one 16-token test call;
  - two paraphrase calls (claim_kin and claim_nonkin, glm-5.2);
  - one call that hit the 504.
- **Balance check:** read for free with `POST /api/v1/datasets/invent` and `{"estimate": true, ...}`. The response field `available_credits` gives the balance.

## API facts
- **Base URL:** `https://api.prod.adaptionlabs.ai/api/v1`.
- **Auth header:** `Authorization: Bearer <ADAPTION_API_KEY>`. The optional `X-Organization-Id` header was not needed.
- **SDK:** `pip install adaption`; it reads `ADAPTION_API_KEY`. We used stdlib urllib instead, in `adaption_client.py`.
- **Text generation:** `POST /responses`. It is OpenAI-Responses-compatible.
  - **Request body:** `{model, instructions, input, temperature, max_output_tokens, store}`. Set `store` to false; that is also the default.
  - **Response:** `{id, status, model, output[], output_text, usage{input_tokens, output_tokens, total_tokens, cost}}`. `usage.cost` is in credits.
  - **Pitfall:** the models reason by default, and reasoning tokens count against `max_output_tokens`. A cap of 16 gave `status: incomplete` and an empty `output_text`.
- **Pricing (credits per 1M tokens, input / output):**

  | model | input | output |
  |---|---|---|
  | qwen3.5-397b | 0.55 | 3.50 |
  | glm-5.2 | 1.40 | 4.40 |
  | deepseek-v4-flash | 0.044 | 0.133 |
  | qwen3.8-27b | 0.039 | 1.25 |
  | gemma-4-31b-it | 0.09 | 0.34 |

  A 24-paraphrase call cost 0.005 to 0.012 credits.
- **Dataset products:**
  - `POST /datasets/{id}/augment`: `similar_rows`, `domain_rows`, `general_rows`;
  - `POST /datasets/invent`: synthetic datasets from a prompt;
  - `/datasets/{id}/adapt`: optimise SFT data.
  - All three take `estimate: true` for a quote, and all bill per row.
- **Chat sessions:** the `chat/sessions/{id}/messages` endpoint another team used does not appear in the public docs or sitemap. We did not use it.

## Sources
- https://docs.adaptionlabs.ai/introduction/getting-started
- https://docs.adaptionlabs.ai/adaptive-data-quickstart
- https://docs.adaptionlabs.ai/inference-stacks/quickstart
- https://docs.adaptionlabs.ai/inference-stacks/models (pricing)
- https://docs.adaptionlabs.ai/api/resources/responses/methods/create
- https://docs.adaptionlabs.ai/api/resources/models/methods/list
- https://docs.adaptionlabs.ai/api/resources/datasets/methods/augment
- https://docs.adaptionlabs.ai/api/resources/datasets/methods/invent
- https://docs.adaptionlabs.ai/adaptive-data/expand-data
- https://docs.adaptionlabs.ai/resources/faq (credits and estimates)
