"""Write DSE uncertainty artifacts under {step_dir}/uncertainty/. No secrets."""
import json
import os

_SECRET_KEYS = {"api_key", "token", "authorization", "apikey", "access_token"}


def _strip_secrets(obj):
    if isinstance(obj, dict):
        return {
            k: _strip_secrets(v)
            for k, v in obj.items()
            if k.lower() not in _SECRET_KEYS
        }
    if isinstance(obj, list):
        return [_strip_secrets(v) for v in obj]
    return obj


def write_uncertainty_artifacts(step_dir: str, run_manifest: dict,
                                per_widget: list) -> str:
    unc_dir = os.path.join(step_dir, "uncertainty")
    os.makedirs(unc_dir, exist_ok=True)
    safe_manifest = _strip_secrets(run_manifest)
    safe_widgets = _strip_secrets(per_widget)
    with open(os.path.join(unc_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(safe_manifest, f, indent=2, ensure_ascii=False)
    with open(os.path.join(unc_dir, "widgets.json"), "w", encoding="utf-8") as f:
        json.dump(safe_widgets, f, indent=2, ensure_ascii=False)
    return unc_dir
