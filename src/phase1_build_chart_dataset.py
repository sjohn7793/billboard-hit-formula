"""
Phase 1: Build the foundation dataset of every U.S. Billboard Hot 100 #1
single from August 1958 to the present.

Source: Wikipedia's maintained "List of Billboard Hot 100 number-one
singles" pages, one per decade. These are actively edited and generally
kept in sync with Billboard, but are not an official Billboard export --
treat this as a strong starting point, not ground truth. Spot-checking
against billboard.com is recommended before publishing any findings.

Output: data/processed/billboard_number_ones.csv
"""

import re
import time
from datetime import date, datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup

USER_AGENT = "billboard-hit-formula-research/0.1 (personal research project)"

# One page per decade. Each has a single consistent chronological table:
# #, Reached number one, Artist(s), Single, Record label, Weeks, Ref
DECADE_PAGES = [
    ("1958-1969", "List_of_Billboard_Hot_100_number-one_singles_from_1958_to_1969"),
    ("1970s", "List_of_Billboard_Hot_100_number-one_singles_of_the_1970s"),
    ("1980s", "List_of_Billboard_Hot_100_number-one_singles_of_the_1980s"),
    ("1990s", "List_of_Billboard_Hot_100_number-one_singles_of_the_1990s"),
    ("2000s", "List_of_Billboard_Hot_100_number-one_singles_of_the_2000s"),
    ("2010s", "List_of_Billboard_Hot_100_number-one_singles_of_the_2010s"),
    ("2020s", "List_of_Billboard_Hot_100_number-one_singles_of_the_2020s"),
]

WIKI_BASE = "https://en.wikipedia.org/wiki/"


def clean_text(cell) -> str:
    # Drop footnote refs and small annotations (e.g. Grammy Hall of Fame
    # induction year in a <small> tag) before extracting text -- they are
    # not part of the song/artist/label value itself.
    for tag in cell.select("sup.reference, small"):
        tag.decompose()
    text = cell.get_text(" ", strip=True)
    text = re.sub(r"\[\w+\]", "", text)  # strip footnote markers like [6]
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("♪", "").replace("†", "")  # Grammy Hall of Fame / other markers
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(' "').strip()


def parse_date(raw: str):
    raw = re.sub(r"\s+", " ", raw).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None  # left for manual review rather than guessed


def fetch_decade(label: str, slug: str) -> pd.DataFrame:
    url = WIKI_BASE + slug
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    def find_col(header_cells, *keywords):
        """Index of the first header containing all keywords, else None.
        Headers vary slightly by decade page (e.g. 'Weeks at No. 1 [ A ]'
        vs 'Weeks at number one'), so match on substrings, not equality."""
        for i, h in enumerate(header_cells):
            if all(kw in h for kw in keywords):
                return i
        return None

    rows_out = []
    for table in soup.select("table.wikitable"):
        header_cells = [clean_text(th).lower() for th in table.select_one("tr").select("th")]
        if not any("reached" in h or "issue date" in h for h in header_cells):
            continue  # not the chronology table (skip footnote/legend tables)

        idx_date = find_col(header_cells, "reached") or find_col(header_cells, "issue date")
        idx_artist = find_col(header_cells, "artist")
        idx_song = find_col(header_cells, "single") or find_col(header_cells, "song")
        idx_weeks = find_col(header_cells, "weeks")
        idx_label = find_col(header_cells, "label")

        for tr in table.select("tr")[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 4:
                continue
            texts = [clean_text(c) for c in cells]

            def get(idx, default=""):
                if idx is None or idx >= len(texts):
                    return default
                return texts[idx]

            date_raw = get(idx_date, texts[1] if len(texts) > 1 else "")
            artist = get(idx_artist, texts[2] if len(texts) > 2 else "")
            song = get(idx_song, texts[3] if len(texts) > 3 else "")
            weeks = get(idx_weeks, "")
            label_field = get(idx_label, "")

            iso_date = parse_date(date_raw)
            song = song.strip(' "')
            if not song or not artist:
                continue

            rows_out.append(
                {
                    "date_reached_number_one": iso_date,
                    "date_raw": date_raw,
                    "artist": artist,
                    "song": song,
                    "record_label": label_field,
                    "weeks_at_number_one": weeks,
                    "decade_source_page": slug,
                }
            )
    return pd.DataFrame(rows_out)


def main():
    frames = []
    for label, slug in DECADE_PAGES:
        print(f"Fetching {label} ({slug}) ...")
        df = fetch_decade(label, slug)
        print(f"  -> {len(df)} rows")
        frames.append(df)
        time.sleep(1)  # be polite to Wikipedia

    full = pd.concat(frames, ignore_index=True)
    full = full.sort_values("date_reached_number_one", na_position="last").reset_index(drop=True)
    full.insert(0, "id", range(1, len(full) + 1))

    out_raw = "data/raw/billboard_number_ones_raw.csv"
    out_processed = "data/processed/billboard_number_ones.csv"
    full.to_csv(out_raw, index=False)
    full.to_csv(out_processed, index=False)

    n_missing_date = full["date_reached_number_one"].isna().sum()
    print(f"\nTotal rows: {len(full)}")
    print(f"Rows with unparsed dates (need manual review): {n_missing_date}")
    print(f"Fetched on {date.today().isoformat()}")
    print(f"Wrote {out_raw} and {out_processed}")


if __name__ == "__main__":
    main()
