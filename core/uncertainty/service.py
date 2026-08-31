"""ObserverUncertaintyService — single shared DSE pipeline.

Used identically by the production ObserverAgent and the standalone runner.
measure() samples the LLM then delegates to measure_from_samples(); tests and
--self-test call measure_from_samples() directly with injected samples.
"""
from core.uncertainty.artifacts import write_uncertainty_artifacts
from core.uncertainty.explainer import explain_step_uncertainty
from core.uncertainty.clusterer import WidgetContext
from core.uncertainty.dse import raw_dse
from core.uncertainty.semantic_parser import parse_semantic_map

_TEMP_REJECT_MARKERS = (
    "temperature",
)


class TemperatureRejectedError(RuntimeError):
    pass


def _looks_like_temperature_rejection(err: Exception) -> bool:
    s = str(err).lower()
    return "temperature" in s and (
        "unsupport" in s or "not supported" in s or "invalid" in s
        or "does not support" in s or "unknown" in s
    )


class ObserverUncertaintyService:
    def __init__(self, llm, clusterer, cfg, prompt_hash: str):
        self.llm = llm
        self.clusterer = clusterer
        self.cfg = cfg
        self.prompt_hash = prompt_hash

    def sample(self, messages: list):
        raw_outputs = []
        failures = []
        for i in range(self.cfg.samples):
            try:
                resp = self.llm.invoke(messages, temperature=self.cfg.temperature)
                raw_outputs.append(getattr(resp, "content", resp) or "")
            except Exception as e:  # noqa: BLE001
                if _looks_like_temperature_rejection(e):
                    provider = getattr(self.llm, "provider", "unknown")
                    raise TemperatureRejectedError(
                        f"Provider '{provider}' rejected per-call temperature="
                        f"{self.cfg.temperature}: {e}"
                    ) from e
                failures.append({"sample_index": i, "error": str(e)})
        return raw_outputs, failures

    def measure(self, messages, widgets, screen_desc, step_dir):
        raw_outputs, failures = self.sample(messages)
        return self.measure_from_samples(
            raw_outputs, widgets, screen_desc, step_dir, sampling_failures=failures
        )

    def measure_from_samples(self, raw_outputs, widgets, screen_desc, step_dir,
                             sampling_failures=None):
        sampling_failures = sampling_failures or []
        parsed = [parse_semantic_map(o) for o in raw_outputs]

        max_widgets = getattr(self.cfg, "max_widgets", None)
        widgets_measured_count = len(widgets)
        widgets_skipped_count = 0
        if max_widgets is not None and len(widgets) > max_widgets:
            widgets_measured_count = max_widgets
            widgets_skipped_count = len(widgets) - max_widgets

        per_widget = []
        target_wid = getattr(self.cfg, "target_widget_id", None)
        threshold = getattr(self.cfg, "threshold", None)

        for idx, w in enumerate(widgets):
            wid = w.get("id")

            # If target-only mode is active, skip all non-target widgets to save computation
            if target_wid is not None and wid != target_wid:
                continue

            if max_widgets is not None and idx >= max_widgets and target_wid is None:
                per_widget.append({
                    "element_id": wid,
                    "measurement_status": "skipped_widget_cap",
                })
                continue
            responses = []
            parse_failures = 0
            for pmap in parsed:
                if wid in pmap:
                    responses.append(pmap[wid])
                else:
                    parse_failures += 1

            ctx = WidgetContext(
                element_id=wid,
                text=w.get("text", "") or "",
                role=w.get("xml_role", "") or w.get("role", "") or "",
                screen_desc=screen_desc,
            )
            cluster_result = self.clusterer.cluster(responses, ctx)
            counts = cluster_result.counts
            effective_m = sum(counts)
            # raw_dse (nats, unbounded) is the paper-faithful result — matches
            # Farquhar et al. 2024's discrete semantic entropy formula exactly, with
            # no added normalization (removed 2026-07-24 to stay paper-exact).
            r = raw_dse(counts)
            status = "insufficient_samples" if effective_m <= 1 else "ok"

            is_above_threshold = (r > threshold) if (threshold is not None and r is not None) else None

            per_widget.append({
                "element_id": wid,
                "text": ctx.text,
                "role": ctx.role,
                "responses": responses,
                "clusters": cluster_result.clusters,
                "cluster_probabilities": [c / effective_m for c in counts] if effective_m else [],
                "pairwise_entailment": [pd.__dict__ for pd in cluster_result.pairwise],
                "raw_dse": r,
                "sample_count": self.cfg.samples,
                "effective_sample_count": effective_m,
                "parse_failures": parse_failures,
                "temperature": self.cfg.temperature,
                "temperature_status": "provisional_not_evaluated",
                "temperature_application": "requested_not_verified",
                "threshold": threshold,
                "calibration_status": "calibrated" if threshold is not None else "not_calibrated",
                "is_above_threshold": is_above_threshold,
                "measurement_status": status,
            })

        explanation = explain_step_uncertainty(self.llm, per_widget, screen_desc)

        manifest = {
            "enabled": self.cfg.enabled,
            "prompt_hash": self.prompt_hash,
            "provider": self.cfg.provider,
            "model": self.cfg.model,
            "judge_model": self.cfg.judge_model,
            "configured_samples": self.cfg.samples,
            "temperature": self.cfg.temperature,
            "temperature_status": "provisional_not_evaluated",
            "temperature_application": "requested_not_verified",
            "threshold": threshold,
            "calibration_status": "calibrated" if threshold is not None else "not_calibrated",
            "target_widget_id": target_wid,
            "raw_samples": raw_outputs,
            "sampling_failures": sampling_failures,
            "max_widgets": max_widgets,
            "widgets_measured": widgets_measured_count,
            "widgets_skipped": widgets_skipped_count,
            "explanation": explanation,
            "widgets": per_widget,
        }
        unc_dir = write_uncertainty_artifacts(step_dir, manifest, per_widget)
        manifest["uncertainty_dir"] = unc_dir
        return manifest
