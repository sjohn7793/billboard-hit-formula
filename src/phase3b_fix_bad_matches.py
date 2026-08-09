"""
Phase 3b: Re-resolve songs whose first-pass Genius match was wrong.

The original phase3 run only validated _type=="song" and lyrics_state==
"complete", which let Genius-hosted non-lyrics content (book excerpts,
movie scripts, fan translations, parodies, karaoke covers) through as
"matches" -- verified by manually reviewing title-similarity outliers.
phase3_lyrics_stats.find_genius_url now requires TITLE_SIM_THRESHOLD
similarity against every search candidate, not just the top hit.

This re-runs ONLY the affected rows (bad matches + originally-unmatched)
against the fixed matcher, using the same discard-raw-text discipline as
phase3. Updates data/processed/lyrics_stats.csv in place.
"""

import time

import pandas as pd
import requests

from phase3_lyrics_stats import (
    _title_similarity,
    compute_stats,
    fetch_lyrics_text,
    find_genius_url,
)

REQUEST_INTERVAL_SECONDS = 1.5


def main():
    path = "data/processed/lyrics_stats.csv"
    df = pd.read_csv(path)

    found_mask = df["found"] == True  # noqa: E712
    df.loc[found_mask, "title_sim"] = df.loc[found_mask].apply(
        lambda r: _title_similarity(r["song"], r["genius_matched_title"]), axis=1
    )
    bad_match = found_mask & (df["title_sim"] < 0.6)
    to_redo = df[~found_mask | bad_match].index.tolist()
    print(f"Re-resolving {len(to_redo)} rows ({bad_match.sum()} bad matches, "
          f"{(~found_mask).sum()} originally unmatched)")

    stat_cols = [c for c in df.columns if c not in ("artist", "song", "found", "title_sim")]

    session = requests.Session()
    n_fixed = 0
    for n, idx in enumerate(to_redo, 1):
        row = df.loc[idx]
        # clear the old (possibly wrong) values first
        for c in stat_cols:
            df.loc[idx, c] = None
        df.loc[idx, "found"] = False

        try:
            url, matched_title, matched_artist = find_genius_url(row["artist"], row["song"], session)
            if url:
                text = fetch_lyrics_text(url, session)
                if text:
                    stats = compute_stats(text)
                    text = None  # never persisted
                    for k, v in stats.items():
                        df.loc[idx, k] = v
                    df.loc[idx, "found"] = True
                    df.loc[idx, "genius_matched_title"] = matched_title
                    df.loc[idx, "genius_matched_artist"] = matched_artist
                    n_fixed += 1
        except requests.RequestException as e:
            print(f"  [{n}/{len(to_redo)}] ERROR for {row['artist']} - {row['song']}: {e}")

        if n % 25 == 0:
            print(f"  [{n}/{len(to_redo)}] processed, {n_fixed} resolved so far")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    df.loc[found_mask & ~bad_match, "title_sim"] = df.loc[found_mask & ~bad_match, "title_sim"]
    df.drop(columns=["title_sim"], inplace=True)
    df.to_csv(path, index=False)

    n_found = df["found"].sum()
    print(f"\nNewly resolved: {n_fixed}/{len(to_redo)}")
    print(f"Overall found: {n_found}/{len(df)} ({n_found/len(df):.0%})")
    print(f"Updated {path}")


if __name__ == "__main__":
    main()
