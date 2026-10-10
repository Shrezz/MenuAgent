# Local receipt extraction and purchase review

Upload a PNG or JPEG under **Groceries & stock → Receipt review**, click **Read receipt with Ollama**, correct the table, then click **Confirm reviewed purchases**. Reading never updates stock. The separate sample receipt still writes only to preview stock.

## Model choice and setup

The MVP defaults to `gemma4:e2b`. This computer already has Ollama running with that vision model installed; no additional model download was needed. Gemma was exercised with a synthetic receipt containing explicit weights, a multiplied package size, counts, a price-only item and a cleaning product. The first prompt included the cleaning product; the revised prompt excluded it and retained unknown quantities. This is a smoke test, not an accuracy benchmark on real receipts.

Qwen3-VL 8B is an alternative to evaluate for OCR; 4B is a smaller option. Compare models on representative receipts before choosing a production default. Larger models depend on available memory and acceptable latency. No extra model is downloaded automatically.

Backend-only optional configuration:

```sh
export MENUAGENT_OLLAMA_URL=http://127.0.0.1:11434
export MENUAGENT_RECEIPT_MODEL=gemma4:e2b
```

The adapter accepts only loopback HTTP addresses, disables system proxies and redirects, checks the installed-model list and vision capability, and rejects cloud-tagged models or models reporting a remote backend. No API key is needed. Requests use Ollama `/api/chat`, base64 images, a JSON schema, temperature 0, disabled thinking and non-streaming output. The model call has a 120-second timeout with no automatic retry; connection checks have shorter timeouts. Extraction is synchronous behind a Streamlit spinner; a queued worker remains future work.

Primary references: [Ollama vision](https://docs.ollama.com/capabilities/vision), [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [Gemma 4 E2B](https://ollama.com/library/gemma4:e2b), [Qwen3-VL 8B](https://ollama.com/library/qwen3-vl:8b).

## Extraction and review contracts

- Inputs: PNG/JPEG, at most 8 MiB and 12 million pixels. Image decoding validates content and corrects EXIF orientation for the model; the original image is retained as provenance.
- Outputs: original visible text, optional store name, normalized item names, nullable quantities, supported units, suggested storage locations, receipt lines and review notes. No numeric confidence is invented.
- Prices must not become quantities. Explicit kg/litre quantities are converted to g/ml by the model and checked by the person. `each` represents counted items or packages, not an assumed weight. Blank quantities stay unknown.
- Model output is untrusted. Shape, field types, lengths, units and finite/non-negative quantities are validated in code. Receipt instructions are treated as data, with no tools available to execute them. Semantic correctness still needs human review.
- Repeated identical name/location/unit lines are combined for review. People can edit, remove or add rows. Confirming an empty list, zero quantity or Out purchase is rejected.

## Persistence and duplicate handling

Migration 004 adds household-scoped receipt records containing original image bytes, MIME type, SHA-256 image identity, model name, extraction, reviewed purchases and confirmation time. The application role can insert extraction records and update only confirmation fields. It cannot edit image/model/extraction provenance or delete receipts. Normal database backup and administrative retention procedures apply to these private images; no upload is written into the repository.

Re-uploading **identical bytes** retrieves the saved extraction and confirmation state, including after a browser restart. Re-reading an existing extraction does not call the model again. This prevents duplicate stock additions for the same image, including concurrent confirmations through household version checks. A different photo or crop of the same physical receipt has a different hash and is not detected as a duplicate; store/date/transaction identity matching remains future work. To retry a failed call use Read receipt again; to replace a saved but inaccurate extraction, correct the review table or upload a clearer image.

Confirmation checks the household edit version and atomically merges reviewed purchases into stock, marks the receipt confirmed and increments the version. A stale session must reload saved household data before retrying. Any failed write rolls back stock, confirmation and version together. Reading alone does not change the household version because it contributes no confirmed stock.

Known compatible quantities are added. Unknown existing or purchased quantities remain unknown. Stock marked Out starts from zero; Use soon status is retained when adding fresh purchases. Matching currently uses normalized name, location and exact unit; synonym reconciliation and package-to-gram conversions require later reviewed normalization. Receipt rows are not automatically matched to USDA nutrition records.

Tests mock model output for deterministic failure/UI checks and use a separate real PostgreSQL database for once-only confirmation, isolation, stale writes, rollback and immutable extraction provenance. A real local Gemma call was verified separately. Actual household records were not test fixtures. Automatic menu planning after receipt upload is still pending milestone 3.
