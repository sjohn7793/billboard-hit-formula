"""
Phase 3: Derived lyrical statistics.

IMPORTANT - copyright handling: Genius's official API does not serve lyric
text at all, and there is no free, ToS-compliant bulk source for full lyric
text (checked: Musixmatch's free tier only gives ~30% previews, useless for
word-count/rhyme/repetition stats). This script scrapes lyric pages off
Genius directly, which violates Genius's Terms of Service even though the
text is never stored -- this was a deliberate, informed choice by the
project owner, not a default. See README "Data sources & attribution".

To keep that choice as narrow as possible: raw lyric text is held ONLY in
a local variable for the few milliseconds it takes to compute stats on it,
then discarded. It is never written to disk, logged, or included in any
CSV, cache file, or error message. Only the numeric/derived features below
are persisted.

Output: data/processed/lyrics_stats.csv
"""

import difflib
import re
import time

import nltk
import pandas as pd
import requests
import textstat
from bs4 import BeautifulSoup
from nltk.corpus import cmudict
from nltk.sentiment import SentimentIntensityAnalyzer

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
SEARCH_URL = "https://genius.com/api/search/multi"
REQUEST_INTERVAL_SECONDS = 1.5

# Genius hosts far more than song lyrics under the same "song" schema --
# book excerpts, movie scripts, fan translations/romanizations, parodies,
# reviews, karaoke/cover pages all show up as _type == "song" with
# lyrics_state == "complete". A title-similarity gate is what actually
# filters those out; type/lyrics_state alone let ~13% of matches through
# wrong on the first version of this script (verified by manual review).
TITLE_SIM_THRESHOLD = 0.6

_sia = SentimentIntensityAnalyzer()
_cmu = cmudict.dict()

SECTION_TAG_RE = re.compile(r"\[[A-Za-z][^\]]{0,40}\]")
WORD_RE = re.compile(r"[a-zA-Z']+")


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(s).lower())


def _title_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def find_genius_url(artist: str, song: str, session: requests.Session):
    resp = session.get(
        SEARCH_URL, params={"q": f"{song} {artist}"},
        headers={"User-Agent": USER_AGENT}, timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    candidates = []
    for section in data.get("response", {}).get("sections", []):
        for hit in section.get("hits", []):
            result = hit.get("result", {})
            if result.get("_type") == "song" and result.get("lyrics_state") == "complete":
                candidates.append(result)

    for result in candidates:
        sim = _title_similarity(song, result.get("title", ""))
        if sim >= TITLE_SIM_THRESHOLD:
            return result.get("url"), result.get("title"), result.get("primary_artist_names")
    return None, None, None


def fetch_lyrics_text(url: str, session: requests.Session):
    """Returns raw lyric text -- caller must not persist it anywhere."""
    resp = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    containers = soup.select('div[data-lyrics-container="true"]')
    if not containers:
        return None
    full = "\n".join(c.get_text("\n", strip=True) for c in containers)
    m = SECTION_TAG_RE.search(full)
    return full[m.start():] if m else full


def rhyme_key(word: str):
    prons = _cmu.get(word.lower())
    if not prons:
        return None
    # last two phonemes of the first pronunciation, stress digits stripped
    phonemes = [re.sub(r"\d", "", p) for p in prons[0]]
    return tuple(phonemes[-2:]) if len(phonemes) >= 2 else tuple(phonemes)


def compute_stats(text: str) -> dict:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip() and not SECTION_TAG_RE.fullmatch(ln.strip())]
    words = WORD_RE.findall(text.lower())

    n_words = len(words)
    n_unique_words = len(set(words))
    n_lines = len(lines)
    n_unique_lines = len(set(lines))
    n_sections = len(SECTION_TAG_RE.findall(text))

    line_end_words = [WORD_RE.findall(ln)[-1] for ln in lines if WORD_RE.findall(ln)]
    rhyme_pairs, rhyming = 0, 0
    for a, b in zip(line_end_words, line_end_words[1:]):
        ka, kb = rhyme_key(a), rhyme_key(b)
        if ka and kb:
            rhyme_pairs += 1
            if ka == kb:
                rhyming += 1

    # VADER sums valence across the whole input and normalizes by a fixed
    # constant, so a long document saturates toward +-1 as soon as it
    # contains a handful of charged words -- meaningless for comparing
    # songs of different lengths. Score each line independently instead
    # and average, which behaves like VADER was designed to (short texts).
    line_sentiments = [_sia.polarity_scores(ln) for ln in lines] if lines else []
    avg_compound = (
        round(sum(s["compound"] for s in line_sentiments) / len(line_sentiments), 4)
        if line_sentiments else None
    )
    avg_pos = round(sum(s["pos"] for s in line_sentiments) / len(line_sentiments), 4) if line_sentiments else None
    avg_neg = round(sum(s["neg"] for s in line_sentiments) / len(line_sentiments), 4) if line_sentiments else None

    # Flesch reading ease assumes real sentences delimited by punctuation;
    # lyric lines have none, so treat each line as one sentence.
    pseudo_sentences = ". ".join(lines)
    flesch = round(textstat.flesch_reading_ease(pseudo_sentences), 2) if len(lines) > 1 else None

    return {
        "word_count": n_words,
        "unique_word_ratio": round(n_unique_words / n_words, 4) if n_words else None,
        "line_count": n_lines,
        "unique_line_ratio": round(n_unique_lines / n_lines, 4) if n_lines else None,
        "section_count": n_sections,
        "avg_word_length": round(sum(len(w) for w in words) / n_words, 2) if n_words else None,
        "flesch_reading_ease": flesch,
        "sentiment_compound_avg": avg_compound,
        "sentiment_positive_avg": avg_pos,
        "sentiment_negative_avg": avg_neg,
        "adjacent_line_rhyme_density": round(rhyming / rhyme_pairs, 4) if rhyme_pairs else None,
    }


def main():
    chart = pd.read_csv("data/processed/billboard_number_ones.csv")
    unique_songs = chart[["artist", "song"]].drop_duplicates().reset_index(drop=True)
    print(f"{len(unique_songs)} unique songs to process")

    session = requests.Session()
    rows = []
    for i, row in unique_songs.iterrows():
        artist, song = row["artist"], row["song"]
        record = {"artist": artist, "song": song, "found": False}
        try:
            url, matched_title, matched_artist = find_genius_url(artist, song, session)
            if url:
                text = fetch_lyrics_text(url, session)
                if text:
                    record.update(compute_stats(text))
                    record["found"] = True
                    record["genius_matched_title"] = matched_title
                    record["genius_matched_artist"] = matched_artist
                    text = None  # explicitly drop reference; never persisted
        except requests.RequestException as e:
            print(f"  [{i+1}/{len(unique_songs)}] ERROR for {artist} - {song}: {e}")

        rows.append(record)
        if (i + 1) % 50 == 0:
            n_found = sum(r["found"] for r in rows)
            print(f"  [{i+1}/{len(unique_songs)}] processed, {n_found} found so far")
        time.sleep(REQUEST_INTERVAL_SECONDS)

    out = pd.DataFrame(rows)
    out_path = "data/processed/lyrics_stats.csv"
    out.to_csv(out_path, index=False)

    n_found = out["found"].sum()
    print(f"\nFound lyrics for: {n_found}/{len(out)} ({n_found/len(out):.0%})")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
