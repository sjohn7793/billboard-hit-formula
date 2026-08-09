"""
Phase 2a, retry pass: re-attempt MusicBrainz matches that failed the first
time due to transient 503s / timeouts (not genuine no-matches -- checking
the first pass showed every row that got *any* result scored >=80, so gaps
are server flakiness, not bad matching).

Retries each unmatched row up to 3x with exponential backoff, at a slower
base rate than the first pass. Updates data/processed/musicbrainz_matches.csv
in place.
"""

import time

import pandas as pd
import requests

from phase2a_musicbrainz_match import search_recording, MB_SEARCH_URL  # noqa: F401

REQUEST_INTERVAL_SECONDS = 3.5
MAX_ATTEMPTS = 4


def search_with_retry(artist, song, session):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return search_recording(artist, song, session)
        except requests.RequestException as e:
            if attempt == MAX_ATTEMPTS:
                print(f"    giving up on {artist} - {song}: {e}")
                return None
            backoff = REQUEST_INTERVAL_SECONDS * (2 ** attempt)
            time.sleep(backoff)
    return None


def main():
    path = "data/processed/musicbrainz_matches.csv"
    matches = pd.read_csv(path)
    to_retry = matches[matches["mbid"].isna()].index.tolist()
    print(f"Retrying {len(to_retry)} unmatched rows...")

    session = requests.Session()
    fixed = 0
    for n, idx in enumerate(to_retry, 1):
        row = matches.loc[idx]
        result = search_with_retry(row["artist"], row["song"], session)
        if result:
            for k, v in result.items():
                matches.loc[idx, k] = v
            matches.loc[idx, "needs_review"] = result["score"] is None or result["score"] < 80
            fixed += 1
        if n % 25 == 0:
            print(f"  [{n}/{len(to_retry)}] retried, {fixed} newly matched so far")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    matches.to_csv(path, index=False)
    n_matched = matches["mbid"].notna().sum()
    n_review = matches["needs_review"].sum()
    print(f"\nNewly matched this pass: {fixed}/{len(to_retry)}")
    print(f"Overall matched: {n_matched}/{len(matches)}")
    print(f"Still needing review: {n_review}")
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
