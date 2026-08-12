"""Download the specific Rico screenshot images needed for the DSE
calibration sample.

MUST be run in a real environment with normal internet bandwidth — the
source archive is a single 6.0 GB gzip-compressed tar with no random-access
index (gzip is a sequential stream), so there is no way to fetch individual
images by URL; the whole archive must be streamed through once, keeping
only the ~400 members that match the calibration sample. This was proven
correct but NOT completed in the authoring sandbox (observed ~1.1 MB/s
there -> ~95 minutes for a full pass, and the sandbox's per-command time
limit is far shorter than that) — see
`Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`, Phase 1 status
note. On a normal broadband connection this should take a few minutes.

Usage:
    python core/calibration/fetch_rico_images.py \\
        --sample experiment/calibration/screen_annotation_sample_400.json \\
        --out-dir experiment/calibration/rico_images

Resumable: images already present in --out-dir are skipped, so a killed or
interrupted run can just be re-launched (it still has to re-stream the
archive from the start each time — gzip has no seek — but it will only
write files it doesn't already have, and will report progress as it goes).
"""
import argparse
import json
import os
import sys
import tarfile
import urllib.request

RICO_UNIQUE_UIS_URL = (
    "https://storage.googleapis.com/crowdstf-rico-uiuc-4540/"
    "rico_dataset_v0.1/unique_uis.tar.gz"
)


def load_target_ids(sample_path: str) -> set:
    with open(sample_path, encoding="utf-8") as f:
        data = json.load(f)
    return {str(s["screen_id"]) for s in data["samples"]}


def fetch(sample_path: str, out_dir: str, url: str = RICO_UNIQUE_UIS_URL) -> dict:
    target_ids = load_target_ids(sample_path)
    os.makedirs(out_dir, exist_ok=True)

    already_have = {
        fn[:-4] for fn in os.listdir(out_dir) if fn.endswith(".jpg")
    }
    remaining = target_ids - already_have
    print(f"[INFO] {len(target_ids)} target images, {len(already_have)} already "
          f"present, {len(remaining)} left to fetch.")
    if not remaining:
        print("[OK] nothing to do — all target images already present.")
        return {"extracted": 0, "already_had": len(already_have), "missing": []}

    print(f"[INFO] streaming {url} (6.0 GB, no random access — this reads "
          f"the whole archive even though we only keep ~{len(remaining)} "
          f"files). This can take a while on a slow connection.")

    req = urllib.request.urlopen(url)
    extracted = 0
    seen_targets = set()
    with tarfile.open(fileobj=req, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".jpg"):
                continue
            base = os.path.basename(member.name)
            screen_id = base[:-4]
            if screen_id not in remaining:
                continue
            seen_targets.add(screen_id)
            fobj = tar.extractfile(member)
            if fobj is None:
                continue
            dest = os.path.join(out_dir, f"{screen_id}.jpg")
            with open(dest, "wb") as out:
                out.write(fobj.read())
            extracted += 1
            if extracted % 25 == 0:
                print(f"[PROGRESS] {extracted}/{len(remaining)} fetched...")

    missing = sorted(remaining - seen_targets)
    print(f"[DONE] extracted {extracted} images. "
          f"{len(missing)} target IDs were not found in the archive "
          f"(unexpected — flag these if non-empty).")
    if missing:
        print(f"[WARN] missing IDs: {missing[:20]}"
              f"{'...' if len(missing) > 20 else ''}")
    return {"extracted": extracted, "already_had": len(already_have), "missing": missing}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sample", required=True,
                    help="Path to screen_annotation_sample_400.json (from sample_screen_annotation.py)")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--url", default=RICO_UNIQUE_UIS_URL)
    args = p.parse_args()

    result = fetch(args.sample, args.out_dir, args.url)
    return 0 if not result["missing"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
