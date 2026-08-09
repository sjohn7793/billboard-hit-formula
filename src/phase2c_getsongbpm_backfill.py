"""
Phase 2c: Backfill key/tempo gaps with GetSongBPM.

AcousticBrainz (musical_features.csv, from phase2b) is the trusted primary
source: real audio-analysis-derived data, but only ~25% song coverage.
GetSongBPM is crowd-reported (site visitors, not audio analysis) with much
better title/artist search coverage, used here ONLY to fill rows
AcousticBrainz didn't cover -- never to overwrite an AcousticBrainz value.

Every row in the output says which source its key/tempo came from, so nothing
downstream can accidentally treat crowd-reported and audio-derived data as
equally reliable.

Note: api.getsongbpm.com is behind a Cloudflare bot challenge and returns
403 to plain HTTP requests; the actual working host is api.getsong.co.

Output: data/processed/musical_features_full.csv (one row per unique
Hot 100 #1 song; superset of musical_features.csv)
"""

import os
import time
import urllib.parse

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GETSONGBPM_API_KEY")
API_BASE = "https://api.getsong.co/search/"
USER_AGENT = "billboard-hit-formula-research/0.1 (sauljohnson93@hotmail.com)"
REQUEST_INTERVAL_SECONDS = 1.2  # well under the documented 3000 req/hour cap


def parse_key_of(key_of: str):
    """GetSongBPM combines key+scale like 'G' (major) or 'Bm' (minor),
    using the Unicode sharp sign (♯) where AcousticBrainz uses a plain
    '#' -- normalize so the two sources are directly comparable."""
    if not key_of:
        return None, None
    key_of = key_of.replace("♯", "#").replace("♭", "b")
    if key_of.endswith("m"):
        return key_of[:-1], "minor"
    return key_of, "major"


def lookup_song(artist: str, song: str, session: requests.Session):
    lookup = f"song:{song} artist:{artist}"
    params = {"api_key": API_KEY, "type": "both", "lookup": lookup}
    resp = session.get(API_BASE, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("search")
    if not results or not isinstance(results, list):
        return None
    top = results[0]
    key, scale = parse_key_of(top.get("key_of"))
    return {
        "key": key,
        "scale": scale,
        "bpm_median": float(top["tempo"]) if top.get("tempo") else None,
        "time_sig": top.get("time_sig"),
        "danceability_getsongbpm": top.get("danceability"),
        "acousticness_getsongbpm": top.get("acousticness"),
        "getsongbpm_matched_title": top.get("title"),
        "getsongbpm_matched_artist": (top.get("artist") or {}).get("name"),
    }


def main():
    if not API_KEY:
        raise SystemExit("GETSONGBPM_API_KEY not set in .env")

    chart = pd.read_csv("data/processed/billboard_number_ones.csv")
    unique_songs = chart[["artist", "song"]].drop_duplicates().reset_index(drop=True)

    mb_matches = pd.read_csv("data/processed/musicbrainz_matches.csv")[["artist", "song", "mbid"]]
    ab_features = pd.read_csv("data/processed/musical_features.csv")

    full = unique_songs.merge(mb_matches, on=["artist", "song"], how="left")
    full = full.merge(
        ab_features[["mbid", "key", "scale", "bpm_median"]].dropna(subset=["mbid"]),
        on="mbid", how="left",
    )
    full["key_source"] = full["key"].apply(lambda k: "acousticbrainz" if pd.notna(k) else None)
    full["time_sig"] = None
    full["danceability_getsongbpm"] = None
    full["acousticness_getsongbpm"] = None
    full["getsongbpm_matched_title"] = None
    full["getsongbpm_matched_artist"] = None

    needs_backfill = full[full["key"].isna()].index.tolist()
    print(f"{len(full)} unique songs total; {len(needs_backfill)} missing key/tempo, querying GetSongBPM...")

    session = requests.Session()
    n_filled = 0
    for n, idx in enumerate(needs_backfill, 1):
        row = full.loc[idx]
        try:
            result = lookup_song(row["artist"], row["song"], session)
        except requests.RequestException as e:
            result = None
            print(f"  [{n}/{len(needs_backfill)}] ERROR for {row['artist']} - {row['song']}: {e}")

        if result:
            for k, v in result.items():
                full.loc[idx, k] = v
            full.loc[idx, "key_source"] = "getsongbpm"
            n_filled += 1

        if n % 50 == 0:
            print(f"  [{n}/{len(needs_backfill)}] processed, {n_filled} filled so far")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    out_path = "data/processed/musical_features_full.csv"
    full.to_csv(out_path, index=False)

    n_have_key = full["key"].notna().sum()
    print(f"\nBackfilled: {n_filled}/{len(needs_backfill)}")
    print(f"Overall key/tempo coverage: {n_have_key}/{len(full)} ({n_have_key/len(full):.0%})")
    print(f"  from AcousticBrainz: {(full['key_source']=='acousticbrainz').sum()}")
    print(f"  from GetSongBPM: {(full['key_source']=='getsongbpm').sum()}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
