# Training and evaluation API audit

Audited on 2026-09-16 against upstream v26.07 and `develop`, with read-only GET/OPTIONS checks against the deployed ARC API. Module 3 is implemented for MCP 0.8.0 and is undergoing validation. This document distinguishes the API contract from the MCP's monitoring and validation behavior. Release evidence belongs in [IMPLEMENTATION-STATUS.md](../IMPLEMENTATION-STATUS.md).

## Audited request fields

| Action | Required fields | Optional fields |
|---|---|---|
| `POST documents/{id}/train/` | `parts`, `transcription` | `model`, `model_name`, `override` |
| `POST documents/{id}/segtrain/` | `parts` | `model`, `model_name`, `override` |

At least one of `model` or `model_name` is required. Segmentation requires at least two images. With an existing model, `override=false` clones it; `override=true` trains the existing model. `model_name` names a newly created or cloned model. Selected pages and the recognition transcription must belong to the document, and model job must match the training kind. These standard request fields already exist in the MCP's training input models.

Source: [`SegTrainSerializer`, API serializers, line 1039](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L1039), [`TrainSerializer`, line 1238](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L1238). The corresponding [develop declarations](https://gitlab.com/scripta/escriptorium/-/blob/develop/app/apps/api/serializers.py#L1039) were also inspected on the audit date.

## Submission response and task creation

Both document actions use `DocumentViewSet.get_process_response`, which validates the serializer and calls its `process()` method. It does not call `serializer.save()` and return a serialized model. Accepted work returns HTTP 200:

```json
{"status": "ok"}
```

This response contains **no model ID, task-group ID or task-report ID**. It proves acceptance, not training completion. Validation failures return HTTP 400; an already-processing exception also returns HTTP 400. A failure after a request reaches the server may have an uncertain outcome and must not trigger an automatic retry.

Source: [`get_process_response`, API views, line 633](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/views.py#L633).

`ProcessSerializerMixin.process()` creates a document-linked task group with creator and a process label. The training serializer then creates/clones/selects a model, records its document association, and submits the background task with `task_group_pk` and `model_pk`. Recognition also supplies `transcription_pk`; segmentation supplies `document_pk`. The submitted task methods are `core.tasks.train` and `core.tasks.segtrain`.

Source: [group creation, serializers line 958](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L958), [segmentation submission, line 1077](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L1077), [recognition submission, line 1277](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L1277).

## Limits on linking a submission to its results

The group response contains `pk`, `method`, `created_at`, `created_by`, aggregated `tasks`, and `page_count`. Its underlying process label is not returned, nor is a model ID/name. `method` is derived from a report and can initially be null. Task-report responses also omit model IDs and group IDs, although a `group` query parameter selects a group's reports.

Source: [task group/report serializers, line 569](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/serializers.py#L569), [task query filters, views line 1043](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/api/views.py#L1043).

Therefore a before/after group comparison can identify **candidates**, not prove which group a submission created. Concurrent submissions, delayed report creation and failed follow-up reads remain possible. A single candidate is still inferred. A model's name or a matching timestamp does not prove attribution either.

The existing `train_recognition` and `train_segmentation` tools accept optional `track`, defaulting to false. With `track=false`, they preserve the raw upstream submission response. With `track=true`, the MCP reads groups before and after a single submission and returns `accepted`, the unchanged `submission`, and `tracking` metadata. New groups with a matching method or an initially null method are candidates. Tracking status is `none`, `candidate`, `ambiguous` or `unavailable`; `attribution_confirmed` remains false even for one candidate. No model/group ID is invented.

Failure of an optional group read or response parsing returns unavailable tracking without changing an accepted submission into a failed write. The MCP never resubmits to repair monitoring. A submission error still propagates as an error; its outcome may be uncertain. The acceptance wrapper does not claim that training completed.

## Evaluation and configuration limits

The audited REST serializers provide no epoch, learning-rate, optimizer, batch-size, precision, device or validation-split fields, and no standalone evaluation action. Upstream training uses server settings for device, precision, loader workers and recognition batch size. It chooses validation data internally, approximately ten percent. Adding invented request keys would not configure those settings. Custom ARC training controls require a separate audit of the deployed customization.

Source: [segmentation configuration, core tasks line 350](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/tasks.py#L350), [recognition configuration, line 658](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/tasks.py#L658).

Live ARC OPTIONS confirms the training routes accept POST, but its advertised action fields are document metadata, not the training serializer. That OPTIONS payload is not reliable evidence of supported training parameters.

## Model and checkpoint reporting

The API exposes `training`, `accuracy_percent`, the current file, and historical versions. Upstream's feedback callback uses recognition accuracy or segmentation mean intersection-over-union as its generic validation score. Do not universally label it CER, WER or recognition accuracy. Historical versions can contain epoch, score, total and error fields, but absent values and zero totals must remain distinct from measured performance. The inspected v26.07 task code does not populate training total/error counts.

Source: [feedback callback, core tasks line 245](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/tasks.py#L245), [model schema, core models line 2186](https://gitlab.com/scripta/escriptorium/-/blob/v26.07/app/apps/core/models.py#L2186).

An advertised file does not prove it exists. During the read-only ARC audit, a checkpoint initially returned HTTP 206 for a one-byte range; ongoing training later removed that file while its version records remained. A newer checkpoint was then available. Several versions can reference the same storage path. Preserve revision records and distinguish advertised artifacts from successfully downloaded artifacts; [module 2 download behavior](MODEL-API.md) handles missing files without reporting completion.

## Implemented 0.8.0 validation and reporting

- Training names accept up to 256 characters. Duplicate page IDs are rejected. Omit unused `model`/`model_name` fields; explicit nulls are rejected. Recognition requires a transcription ID; segmentation requires two distinct page IDs. At least one starting model or output name is required.
- When a model is selected, the MCP reads it and checks its job type against the training action. With `override=true`, the selected model must have `rights == "owner"` and `training == false`, including requests also containing `model_name`. Missing ownership/idle evidence fails this guard. Preflight observations are not atomic locks.
- Page membership and recognition transcription membership are validated authoritatively by the server's submission serializer. The MCP does not perform an extra read for each page/layer or claim a transactional scope check.
- Optional monitored submission exposes candidate groups and uncertainty as described above. `track` is an MCP option and is never forwarded as a training parameter.
- `get_training_report` returns the model's name, job, training flag, raw `accuracy_percent`, current-file reference and checkpoint records. Missing and zero values remain distinct; no CER/WER or independent evaluation is calculated.
- Optional `document_id` and `group_id` add authenticated-user task summaries filtered to the model's training method. A group requires its document ID. A supplied document/group is labeled `caller_supplied`, not a proven model link; without a group, historical training reports remain included. `artifact_availability` remains `not_checked`; use `download_model` to verify bytes.
- Virtual-collection training remains in roadmap module 10. Its separate actions can return a model ID; that is not the document-training contract.

Protocol validation covers candidate ambiguity, optional monitoring failures, single submission, model kind/ownership/idle checks, request validation and raw metric/checkpoint reporting. Full regression, distribution and deployment status must be read from the release evidence rather than inferred from this contract document.
