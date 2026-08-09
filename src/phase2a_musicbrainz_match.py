"""
Phase 2a: Resolve every Billboard Hot 100 #1 to a MusicBrainz recording.

This is the join key we need before AcousticBrainz features (Phase 2b) or
any other MBID-keyed dataset can be attached. MusicBrainz's search API is
free, keyless, but rate-limited to ~1 request/second -- for ~1,170 unique
songs this takes roughly 20 minutes.

Matching is fuzzy (title/artist string search), so every match is stored
with its MusicBrainz confidence score and NOTHING downstream should treat
a match as certain without checking that score. Ambiguous/low-confidence
matches are flagged for manual review rather than silently kept or dropped.

Output: data/processed/musicbrainz_matches.csv
"""

import time
import unicodedata

import pandas as pd
import requests

USER_AGENT = "billboard-hit-formula-research/0.1 (sauljohnson93@hotmail.com)"
MB_SEARCH_URL = "https://musicbrainz.org/ws/2/recording"
REQUEST_INTERVAL_SECONDS = 1.1  # stay safely under MusicBrainz's ~1 req/s limit

LOW_CONFIDENCE_THRESHOLD = 80  # MusicBrainz score is 0-100


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def search_recording(artist: str, song: str, session: requests.Session):
    query = f'artist:"{normalize(artist)}" AND recording:"{normalize(song)}"'
    params = {"query": query, "fmt": "json", "limit": 3}
    resp = session.get(MB_SEARCH_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    recordings = data.get("recordings", [])
    if not recordings:
        return None
    top = recordings[0]
    return {
        "mbid": top.get("id"),
        "score": top.get("score"),
        "matched_title": top.get("title"),
        "matched_artist": (top.get("artist-credit") or [{}])[0].get("name"),
        "n_candidates": len(recordings),
    }


def main():
    chart = pd.read_csv("data/processed/billboard_number_ones.csv")
    unique_songs = chart[["artist", "song"]].drop_duplicates().reset_index(drop=True)
    print(f"{len(unique_songs)} unique (artist, song) pairs to resolve")

    session = requests.Session()
    results = []
    for i, row in unique_songs.iterrows():
        try:
            match = search_recording(row["artist"], row["song"], session)
        except requests.RequestException as e:
            match = None
            print(f"  [{i+1}/{len(unique_songs)}] ERROR for {row['artist']} - {row['song']}: {e}")

        record = {"artist": row["artist"], "song": row["song"]}
        if match:
            record.update(match)
        else:
            record.update({"mbid": None, "score": None, "matched_title": None,
                            "matched_artist": None, "n_candidates": 0})
        results.append(record)

        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{len(unique_songs)}] resolved so far...")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    matches = pd.DataFrame(results)
    matches["needs_review"] = (
        matches["mbid"].isna() | (matches["score"].fillna(0) < LOW_CONFIDENCE_THRESHOLD)
    )

    out_path = "data/processed/musicbrainz_matches.csv"
    matches.to_csv(out_path, index=False)

    n_matched = matches["mbid"].notna().sum()
    n_review = matches["needs_review"].sum()
    print(f"\nMatched: {n_matched}/{len(matches)}")
    print(f"Flagged for manual review (no match or score < {LOW_CONFIDENCE_THRESHOLD}): {n_review}")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
