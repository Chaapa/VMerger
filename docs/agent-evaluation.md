# VMerger: agent quality metrics and dashboard

Date: October 23, 2026. Status: measurement specification and chart demonstration; no live agent evaluations have been performed. Related documents: [quality and operations](quality-and-operations.md), [agents](agents-and-effects.md), [architecture](architecture.md). The alpha's measured operational observations are documented separately in [implemented scope](implementation.md).

## 1. Evaluation units and counting rules

Evaluate individual tools/proposals, complete agent runs, and the final film after the full workflow. Improvements to one role must also be checked on the completed film.

A case contains immutable sources, a request, available resources and annotations. A project may contain related cases and edits. Fix suite version, train/dev/holdout split, hardware profile, resources and model/prompt/tools when comparing versions. A source `corpus_id` and all its edits belong to one split: similar excerpts from a trip must not cross dev/holdout boundaries.

Start with 30 independent projects, at least three edit types per project and three trials per case. Repeated trials are not independent projects. For role-specific evaluation, freeze upstream inputs, then run a separate end-to-end evaluation.

Every observation records metric ID/version, case ID, trial, numerator, denominator, unit, evaluation source and evidence links. Require `n_projects`, `n_cases`, `n_runs`, `n_eligible`, `n_observed` and `n_missing`. Define eligibility before execution; do not discard inconvenient results afterward.

- No eligible objects means `not_applicable` with a reason, not 100%. No rating/result means `missing` or `failed`, not an unexplained zero score.
- Timeouts, tool failures, budget exhaustion and missing films remain in the end-to-end denominator.
- Artistic metrics use rateable outputs with separate evaluation coverage. A good average among survivors must not hide missing films.
- Human, deterministic and LLM evaluations are separate series. LLM judgment is not the oracle for hard requirements.
- Default macro aggregation averages trials, then cases within each project, then independent projects. Longer films do not gain weight merely by containing more frames.
- Also show micro ratios of summed numerators/denominators for diagnosis, labeled explicitly.
- Show critical violations as absolute counts so they cannot disappear in an average.
- Time and cost include all attempts. Unknown cost is not zero.

All numerical thresholds below are initial product criteria to validate on labeled data. Artistic metrics support comparisons; they do not objectively guarantee a beautiful film.

## 2. Common metrics

| ID / unit | Formula or check | Source / initial criterion |
|---|---|---|
| end_to_end_success, % | 100 × accepted eligible runs producing a verified film, satisfying all hard requirements before deadline / all accepted eligible runs | Jobs, renders, validators; ≥99%, with failure count |
| first_plan_valid, % | 100 × runs whose first proposed plan passes schema/semantic validation / runs requiring a plan; no proposal by deadline fails | First submit_edit_plan/proposal and validator version; ≥95% |
| hard_violation_count, count | Final outputs with at least one violated hard rule; also count violated rules by type | Independent validator and annotated requirements; exactly 0 |
| tool_success, % | 100 × successful completed calls / all completed or expired calls; separate invalid_arguments, provider_error, access_denied | agent_steps; ≥98%, by role/cause |
| evaluation_coverage, % | 100 × usable measurements / predefined eligible measurements | Case/observation registry; 100% for required release checks |

Hard violations count delivered final outputs. Invalid/unsafe operations blocked by validators are separate observations affecting first-plan/tool success. No final result means end-to-end failure; absence of a violating result is not success.

Hard rules include project access, valid version/lease, required moments, excluded material, preserved edits, permitted resources and playable output. Each rule needs an oracle: code, annotations or actual file verification.

Charts show per-version proportions, numerator/denominator and 95% intervals. Violations use separate bars by type/version. Cost or subjective quality cannot compensate for a critical violation.

## 3. Director / scriptwriter

| ID / unit | Check | Initial target | Chart |
|---|---|---|---|
| salient_event_coverage, % | 100 × Σ(w_i × covered_i) / Σw_i over relevant salient events | ≥90% | Per-version points/intervals and event detail |
| unrequested_repetition, % | 100 × duration of unrequested repeated moments / video-track duration | ≤5% | Project distribution and version mean |
| supported_claims, % | 100 × supported verifiable statements in titles/script / all verifiable statements | 100% for factual captions; investigate unsupported claims | Proportion and absolute unsupported count |
| story_approval, % | 100 × cases with final human coherence rating ≥4/5 / rated cases | ≥80%, with no confirmed regression | Rating distribution and approval rate |

Annotators define event ID, weight (1 ordinary, 2 important, 3 central), acceptable alternative source intervals and minimum retained fraction before execution. `covered_i = 1` if at least one alternative appears with sufficient coverage, defaulting to 80% of the annotated meaningful interval. Multiple cameras capturing one event represent one event. “Keep this whole” is a separate hard constraint requiring complete retention within timestamp precision.

For multiple films, annotations assign events to intended stories; every film need not include every event. If structure is unconstrained, also measure coverage across the collection.

Repetition uses annotated `canonical_moment_id` and source-interval overlap, mapped to output duration after speed changes. Remove explicitly permitted repeats from eligibility beforehand. A transition between neighboring shots is not itself repetition. Model-detected visual duplicates are supporting evidence; the control oracle is human-labeled.

Verify places, dates, names and event claims against available evidence. No verifiable claims means `not_applicable`; the system need not add captions to improve this metric.

## 4. Music agent

| ID / unit | Check | Initial target | Chart |
|---|---|---|---|
| music_fit_approval, % | 100 × cases with human music-fit rating ≥4 / rated eligible cases | ≥80% | Approval with intervals and rating distribution |
| speech_mix_pass, % | 100 × speech windows where processed speech exceeds music by at least δ dB / speech windows with overlaid music | ≥95%, initial δ = 6 dB | Level-difference distribution, δ line and pass rate |
| speech_intelligibility_approval, % | 100 × cases where human listeners understand speech without extra effort / cases with speech over music | ≥95% | Proportion and problematic timestamps |
| resource_provenance_coverage, % | 100 × used music/sound resources with verified source, terms and confirmation / used resources | 100% | Missing-confirmation count and coverage |
| requested_beat_alignment, % | 100 × beat-targeted cuts where min_abs(cut_t − beat_t) ≤ ε / all beat-targeted cuts | ≥70% for applicable styles only; initial ε = 80 ms | Distance-to-accent histogram and ε line |

For speech mix, use separate speech/music stems after gain/ducking. Compare RMS on a common timeline in annotated 400 ms speech windows. Required but missing speech fails. A zero music signal means no masking, not division by zero. Without overlaid music, the metric is not applicable. The 6 dB margin is an adjustable engineering heuristic; human intelligibility validates its usefulness.

Evaluate beat alignment only when requested. Map beats from the selected music excerpt through trimming, speed and offset; manually verify control-set accents. Speech and required scenes take precedence, with such boundaries excluded from applicability before scoring.

No music is acceptable when consistent with the request. If music was required, its absence is a task failure, not `not_applicable`. Provenance checks confirmation and policy-permitted use; it does not automate a legal judgment.

## 5. Editing agent

| ID / unit | Check | Initial target | Chart |
|---|---|---|---|
| bad_boundary_rate, defective boundaries per 100 | 100 × boundaries with at least one confirmed defect / checked boundaries | ≤2; zero critical defects | Project mean/interval and cause bars |
| broken_speech_boundaries, % | 100 × unintended word/phrase truncations / checked boundaries involving speech | Zero truncated words; phrase endings rated separately | Defect count/timestamps by version |
| effect_parameter_validity, % | 100 × effect instances valid for preset version, parameters, resources and duration / applied instances | 100% | Errors by preset/version |
| style_approval, % | 100 × cases with human style-match rating ≥4 / rated cases | ≥80% | Rating distribution and approval by style |
| title_readability_approval, % | 100 × titles without font, clipping, reading-time or contrast problems / checked titles | ≥95%; zero missing glyphs or clipped required text | Proportion and issue types with frames |
| preserved_edit_constraints, % | 100 × satisfied atomic edit requirements / applicable requirements | 100% for hard constraints | Command-type × version matrix |

Inspect a window around each cut, initially ±0.5 seconds and expanded to include the full transition. Defects include unintended blank frames/jumps, incorrect overlap, visible speed errors and truncated speech. Record type and timestamp. A boundary with three defects counts once in the rate but retains all three causes. An intentional hard cut is not a defect.

Problems inside long clips belong in separate findings and whole-film technical checks. Zero boundary defects does not prove an otherwise flawless film. No boundaries means `not_applicable`.

Style approval measures excessive effects subjectively; “fewer effects is always better” is not a rule. Code verifies fonts and safe areas; people assess readability at actual playback speed.

## 6. Reviewer

Evaluate the reviewer on a separate set of clean films and copies containing known injected defects. Start with at least 40 defective variants and 40 clean controls spanning types/severity. Variants of one source project form one statistical cluster. Hide ground truth and injection metadata from the reviewer.

Match warnings one-to-one to ground-truth defects: same type, same clip/object and temporal IoU ≥0.3; point defects allow ≤0.5 seconds distance. Version these parameters with the scorer. Repeated warnings for one defect cannot create another true positive; measure duplicates separately. Independent humans adjudicate disputed novel findings before ground truth is finalized.

| ID | Formula | Initial target | Chart |
|---|---|---|---|
| reviewer_precision | TP / (TP + FP) | ≥0.90 | Precision × recall by version |
| reviewer_recall | TP / (TP + FN) | ≥0.90 | Same chart, split by defect type |
| critical_defect_recall | TP_critical / (TP_critical + FN_critical) | 1.00 on the control set | Absolute missed-critical count |
| clean_false_alarm_rate | Clean films with at least one false warning / all clean films | ≤0.05 | Proportion and false-alarm types |
| duplicate_warning_rate | Repeated reports of an already matched defect / all warnings | ≤0.05 | Rate by version |

TP is a detected real defect, FP an unsupported warning, FN a missed defect. With no warnings, precision is undefined; when defects exist, recall is zero. These definitions avoid rewarding a reviewer that flags everything or says nothing.

## 7. Speed, cost and stability

| ID / unit | Calculation | Criterion / chart |
|---|---|---|
| time_to_valid_preview, seconds | Accepted request → accessible verified preview, including queues/retries | p50/p95 on the same profile; investigate >20% regression |
| agent_active_seconds, seconds | Sum of a role's active stage time, excluding queue waits | By role/version; parallel stage sums are not wall time |
| ai_cost_per_input_minute, USD/min | All known call/retry cost / source minutes across accepted runs | Same-suite comparison; investigate >20% increase |
| ai_cost_per_success, USD/film | Entire suite cost, including failures / successfully delivered films | Quality × cost; undefined at zero successes, with spend still visible |
| correction_rounds | Complete creative revision cycles before result | p50/p95; architectural maximum 2 |
| budget_exhaustion, % | 100 × runs hitting a limit / accepted runs | Split by time/cost/steps; target ≤5% on control set |
| cost_measurement_coverage, % | 100 × calls with calculated cost / billable calls | 100% for cost comparisons; otherwise mark incomplete |

Record pricing, currency and calculation version. Do not add currencies without an explicit rate/date. Estimated and actual spend use separate fields. USD is an accounting unit, not a current provider price quote.

Readiness p95 uses successful runs and must show end-to-end success and timeout counts beside it. Failures are not fast responses. Also show deadline completion rate and flag unstable percentiles from small samples.

## 8. Human ratings and LLM-judge calibration

Apply this 1–5 rubric independently to coherence, music and style:

- 1: contradicts the request, with major problems.
- 2: partly matches, requiring substantial revision.
- 3: acceptable, with specific noticeable shortcomings.
- 4: matches the request, with only minor shortcomings.
- 5: fully matches, with no noticeable shortcomings.

Two people rate independently without model/version identity; randomize A/B order. Add a third rater when approval decisions (≥4 versus <4) differ or scores differ by more than one point. The final rating is the median. Preserve raw votes, consensus and a short observable explanation with timestamps. Do not hide disagreement inside one score.

Pairwise comparison records wins W, ties T and losses L. `Preference = (W + 0.5T) / (W + T + L)`. Display ties separately; 0.5 means parity. This is a preference measure, not a composite of unrelated metrics.

LLM judges receive the same rubric and inspectable material. On human-rated examples, build an approved/not-approved confusion matrix and calculate `balanced accuracy = (recall_approved + recall_not_approved) / 2`. Initial calibration target: ≥0.85; below it, model scores remain diagnostic. Recalibrate when the judge or prompt changes, and label human/model series separately. See [Google's judge evaluation guidance](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/evaluate-judge-model).

## 9. Uncertainty and version comparisons

Use 95% cluster-bootstrap intervals for soft metrics: resample independent source projects with replacement 2,000 times, retaining each project's related cases/trials. For candidate-minus-baseline differences, use the same sampled project pairs. Small-suite intervals are approximate. Fix seed, scorer version and percentile method.

Identical observations can produce zero-width bootstrap intervals. Mark them uninformative rather than claiming zero risk. Rare-failure decisions need a larger independent set and a preselected method for estimating a frequency bound.

Match case/trial IDs or predeclared pairs. Count added/missing cases separately; an intersection comparison is not the full suite. Changed suite composition creates a new series or requires rerunning both versions. Production-user charts change with uploaded material and do not establish a causal model improvement.

Release criteria:

1. No critical violations or missed known critical defects; all required checks observed.
2. Meet technical and end-to-end success targets without excluding failed cases.
3. The lower 95% bound of Δ(candidate − baseline) is at least −3 percentage points for event coverage and −5 points for human approval.
4. The upper bound for bad-boundary-rate Δ is at most +1 point, while also meeting its absolute target.
5. Preference's lower bound is at least 0.45. Excessively wide intervals mean insufficient data, not no regression.
6. More than 20% time/cost growth requires investigation and an explicit product-profile change if justified by quality.

Fix tolerances before the run and refine them using real data. Check each required metric separately; a composite average cannot compensate for failure. Trying multiple variants on the holdout requires a fresh independent confirmation set to avoid selecting noise. Zero observed violations means only none found in that finite sample; always display N and independent-project count.

## 10. Collection and storage

Flow: suite manifest → fixed run → plan/render → deterministic scorers → independent ratings → aggregates/intervals → baseline comparison → CI decision.

The full evaluator requires these PostgreSQL records:

| Table | Fields / purpose |
|---|---|
| eval_runs | run_id, suite/version/hash, split, configuration_hash, model/prompt/tool/scorer versions, baseline_run_id, hardware_profile, seed, timestamps, status, manifest_object_id |
| eval_results | run_id, case_id, corpus_id, trial, role, metric ID/version, evaluator_id, numerator, denominator, value, unit, status/reason, source (code/human/llm), evidence_object_id, target_version_id, timestamp |

Each result is one metric for one case/trial/evaluator. Uniqueness on run/case/trial/metric-version/evaluator prevents duplicate accounting. Raw human votes and consensus use different evaluator IDs; aggregation selects one result type. Not-applicable, missing and failure are explicit states, not zeros.

Sources, evidence excerpts, reports and annotations remain in private S3. Tables hold numeric observations and references. Test-project IDs do not authorize access to user projects. agent_steps and ai_calls provide measurement inputs; successful tool execution does not prove artistic quality.

The alpha's operational `eval_results` is smaller than this target evaluator schema. Full suite/run/evaluator storage requires migrations. Version manifests and formulas; rescoring creates a new run and preserves old results.

Grafana should use restricted read-only aggregate views. Prometheus retains operational counters/histograms with bounded role/stage/outcome/model-alias labels, not case/run IDs or arbitrary prompt versions. Combine histogram buckets across workers; never average worker-local p95 values. [Prometheus histogram aggregation](https://prometheus.io/docs/practices/histograms/).

## 11. Evaluation dashboard

Operators choose baseline/candidate, suite/version/split, role and material type. Evaluation source is always visible. Filters update N and data-sufficiency status. This is an administrative view; ordinary users see the film, progress and edit explanation.

| Panel | Axes / display | Required detail |
|---|---|---|
| Execution | Version × end-to-end success / first-plan validity in separate % charts | Success/total, projects/cases/trials, missing, confidence interval |
| Hard rules | Version × violating final outputs | Type, case, message, version and timestamp |
| Director | Version × event coverage % | Missing events/weights; separate approval/repetition panels |
| Music | Version × music-fit approval % | Votes, 1–5 distribution; separate intelligibility/provenance panels |
| Editing | Version × defects per 100 boundaries | Defective/checked counts, type, boundary preview |
| Reviewer | Precision % × recall %, one point per version | TP/FP/FN, critical misses, clean-film false alarms |
| Time | Version/date × readiness p95 seconds | p50, success/timeout counts, queued versus active time |
| Cost | Version × USD per input minute | Total/retries/coverage, separate cost-per-success chart |
| Comparison | Δcandidate−baseline × metrics on separate scales | 95% interval, tolerance, paired-project count and decision |
| Calibration | Human-versus-model confusion matrix | Count, balanced accuracy, class and judge version |

Separate absolute values, relative change and percentage-point differences. Label units; count bars start at zero. Explicitly show bounds on zoomed point plots. Cost, percentages and seconds do not share one scale.

Use bands/error bars for intervals. Missing intervals indicate a documented evaluation limitation, not zero uncertainty. Show unknowns as gaps with reasons. Clicking a point opens cases, evidence and disagreements without rerunning agents. Label threshold lines as design targets.

The earlier interactive conversation demo uses synthetic data, is disconnected from monitoring and is not a VMerger quality report. It has one case per project, three trials, 90 runs for each of five versions, a fixed seed and 2,000 project-bootstrap samples. It is smaller than the proposed suite with multiple edit types and clean reviewer controls. The full dashboard depends on the evaluator.

## 12. Test the metrics themselves

Scorers need manually derived expected results:

- Retain 8 of 10 equally weighted events → coverage 80%; zero eligible events → not applicable.
- Two defective boundaries among 40 → rate 5; three defects at one boundary still count as one defective boundary.
- TP=9, FP=3, FN=1 → precision 75%, recall 90%; duplicate warnings add no TP.
- W=6, T=2, L=2 → preference 70% over 10 pairs.
- Eight successes, one failure and one timeout among 10 accepted runs → success 80%, not 100% of delivered films.
- All attempts cost USD12 and eight films succeed → USD1.50 per success; unknown call cost lowers coverage and marks the sum incomplete.
- Speed/transition time maps correctly move speech boundaries and musical accents.
- Micro/macro aggregates on unequal film lengths match distinct predefined values.
- Duplicate writes, multiple raters, missing values, zero denominators and empty baselines cannot improve aggregates.
- Bootstrap preserves project clusters and version pairs; fixed seed and sorting make input row order irrelevant.
- Dashboard numerators/denominators match evaluator output; filters update N; axes/labels expose regressions.

Before automated evaluation is adopted, independently hand-score the same small set and compare it with the scorer. Evaluator bugs block release decisions just as application bugs do.
