"""
Phase 2b: Pull key, scale, and tempo (BPM) for every matched Hot 100 #1
out of the AcousticBrainz bulk dump.

AcousticBrainz's feature CSVs have ~29.4M rows each and aren't sorted or
indexed by MBID, so there's no way to "look up" our ~1,000 songs cheaply --
we stream through every row once and keep the ones whose mbid is in our
matched set. This takes a few minutes but only needs to run once per dump.

A single MBID can appear multiple times (multiple independent AcousticBrainz
submissions of the same recording, e.g. from different file rips). Where
that happens we keep every submission and report the mode (key) / median
(BPM) per song rather than silently picking "first seen" -- different rips
occasionally disagree, and averaging hides that instead of surfacing it.

Inputs:
  data/processed/musicbrainz_matches.csv (from phase2a)
  data/raw/acousticbrainz/tonal.tar, data/raw/acousticbrainz/rhythm.tar
Output:
  data/processed/musical_features.csv
"""

import csv
import statistics
import tarfile
from collections import defaultdict

import pandas as pd

TONAL_TAR = "data/raw/acousticbrainz/tonal.tar"
RHYTHM_TAR = "data/raw/acousticbrainz/rhythm.tar"


def get_csv_member_stream(tar_path: str):
    tf = tarfile.open(tar_path, "r:")
    member = next(m for m in tf.getmembers() if m.name.endswith(".csv"))
    raw = tf.extractfile(member)
    import io
    return tf, io.TextIOWrapper(raw, encoding="utf-8", errors="replace")


def collect_tonal(wanted_mbids: set) -> dict:
    tf, text = get_csv_member_stream(TONAL_TAR)
    reader = csv.DictReader(text)
    hits = defaultdict(list)
    n = 0
    for row in reader:
        n += 1
        if row["mbid"] in wanted_mbids:
            hits[row["mbid"]].append((row["key_key"], row["key_scale"]))
        if n % 5_000_000 == 0:
            print(f"  tonal: scanned {n:,} rows, matched {len(hits)} mbids so far")
    tf.close()
    print(f"  tonal: done, scanned {n:,} rows total, matched {len(hits)} unique mbids")
    return hits


def collect_rhythm(wanted_mbids: set) -> dict:
    tf, text = get_csv_member_stream(RHYTHM_TAR)
    reader = csv.DictReader(text)
    hits = defaultdict(list)
    n = 0
    for row in reader:
        n += 1
        if row["mbid"] in wanted_mbids:
            hits[row["mbid"]].append((float(row["bpm"]), float(row["danceability"])))
        if n % 5_000_000 == 0:
            print(f"  rhythm: scanned {n:,} rows, matched {len(hits)} mbids so far")
    tf.close()
    print(f"  rhythm: done, scanned {n:,} rows total, matched {len(hits)} unique mbids")
    return hits


def mode_or_none(values):
    if not values:
        return None, 0
    try:
        return statistics.mode(values), len(values)
    except statistics.StatisticsError:
        return values[0], len(values)  # tie: no clean mode, report first + let n_submissions flag it


def main():
    matches = pd.read_csv("data/processed/musicbrainz_matches.csv")
    matched = matches[matches["mbid"].notna()].copy()
    wanted_mbids = set(matched["mbid"])
    print(f"Looking up audio features for {len(wanted_mbids)} unique matched MBIDs...")

    print("Scanning tonal.tar (key/scale)...")
    tonal_hits = collect_tonal(wanted_mbids)
    print("Scanning rhythm.tar (BPM/danceability)...")
    rhythm_hits = collect_rhythm(wanted_mbids)

    rows = []
    for _, row in matched.iterrows():
        mbid = row["mbid"]
        keys = [k for k, s in tonal_hits.get(mbid, [])]
        scales = [s for k, s in tonal_hits.get(mbid, [])]
        bpms = [b for b, d in rhythm_hits.get(mbid, [])]
        dances = [d for b, d in rhythm_hits.get(mbid, [])]

        key_mode, n_key_submissions = mode_or_none(keys)
        scale_mode, _ = mode_or_none(scales)

        rows.append({
            "artist": row["artist"],
            "song": row["song"],
            "mbid": mbid,
            "musicbrainz_score": row["score"],
            "key": key_mode,
            "scale": scale_mode,
            "n_key_submissions": n_key_submissions,
            "bpm_median": statistics.median(bpms) if bpms else None,
            "n_bpm_submissions": len(bpms),
            "danceability_median": statistics.median(dances) if dances else None,
        })

    features = pd.DataFrame(rows)
    out_path = "data/processed/musical_features.csv"
    features.to_csv(out_path, index=False)

    n_with_key = features["key"].notna().sum()
    n_with_bpm = features["bpm_median"].notna().sum()
    print(f"\n{len(features)} matched songs processed")
    print(f"Have key/scale: {n_with_key} ({n_with_key/len(features):.0%})")
    print(f"Have BPM: {n_with_bpm} ({n_with_bpm/len(features):.0%})")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
