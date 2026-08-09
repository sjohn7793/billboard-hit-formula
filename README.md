# Billboard Hit Formula

A long-term data project analyzing every U.S. Billboard Hot 100 #1 single (August 1958–present) for measurable musical and lyrical patterns: key, mode, tempo, chord progressions, song structure, and lyrical characteristics.

## Goal, framed honestly

This will not produce a literal "formula" that predicts a #1 hit. Pop music success depends on factors we can't quantify (promotion, culture, timing, artist fame). What this project *can* do is find real, measurable statistical patterns — e.g. "major-key dominance has declined since the 1990s" or "#1s have shorter intros than same-era Top 40 non-#1s" — and report them with appropriate confidence and sample sizes.

To say anything about what makes a #1 *different* from just "a hit," we compare against a control group: Hot 100 songs that charted Top 40 but never reached #1. Without that comparison we can only describe #1s, not explain them.

## Phases

1. **Foundation dataset** — every Hot 100 #1 since Aug 1958 (title, artist, date(s) at #1, weeks at #1, genre tags). Primary source: Wikipedia's maintained "List of Billboard Hot 100 number ones" pages, spot-checked against Billboard.
2. **Musical features** — key, mode, tempo (BPM), time signature, chord progression, song structure. Coverage will be uneven (better for recent decades) and gaps will be reported, not papered over. Candidate sources: Hooktheory TheorTab (crowd-annotated chords/melody), audio-feature APIs where accessible.
3. **Lyrical features (derived only)** — word count, unique-word ratio, rhyme density, repetition/chorus ratio, sentiment, readability. Raw lyric text is copyrighted: it is fetched, scored, and **discarded**, never persisted. Only aggregate numeric features are stored.
4. **Statistical analysis** — trends over time, #1 vs. non-#1 comparison, genre-conditioned patterns.
5. **Living pipeline** — a scheduled job that appends each new #1 (Billboard updates Tuesdays) to the dataset going forward.

## Data policy

- No full copyrighted lyric text or copyrighted audio files are stored in this repo, at any phase.
- Any API keys go in a local `.env` file (git-ignored), never committed.
- Every derived dataset file should note its source and fetch date.

## Data sources & attribution

- **Chart history**: [Wikipedia](https://en.wikipedia.org/wiki/Category:Lists_of_Billboard_Hot_100_number-one_songs) — per-decade "List of Billboard Hot 100 number-one singles" pages.
- **Recording identity**: [MusicBrainz](https://musicbrainz.org/) — free public API, used to resolve each song to a canonical recording ID.
- **Key / tempo (primary)**: [AcousticBrainz](https://acousticbrainz.org/) bulk dataset dump — real audio-analysis-derived features (via Essentia), frozen since 2022. Covers ~25% of our matched songs.
- **Key / tempo (supplementary)**: [GetSongBPM](https://getsongbpm.com/api) — fills gaps AcousticBrainz doesn't cover. Crowd-reported, not audio-derived, so treated as lower-confidence and always flagged by source in the data.
- **Lyrics (derived stats only)**: [Genius](https://genius.com) song pages, scraped directly. **This is a deliberate, informed exception to normal practice**: Genius's official API doesn't serve lyric text at all, and the only free legal alternative (Musixmatch) caps free-tier access at ~30% previews — not enough for reliable word count, rhyme, or repetition stats. The project owner explicitly chose to scrape Genius for personal, non-commercial research use, understanding this violates Genius's Terms of Service even though raw text is never stored. Raw lyric text lives in a local variable only for the milliseconds it takes to compute stats on it (`src/phase3_lyrics_stats.py`), then is discarded — never written to disk, logged, or included in any output. Because Genius hosts non-song content (book excerpts, movie scripts, fan translations, parodies, karaoke covers) under the same schema as songs, every match is validated against a title-similarity threshold before being accepted — an earlier unvalidated version wrongly matched ~13% of songs to unrelated content, caught by a word-count outlier of 148,648 for what should have been a ~300-word song.

## Status

- [x] Phase 1: Foundation dataset — 1,201 #1s, 1958–present
- [x] Phase 2: Musical features (key, scale, tempo) — 857/1,194 unique songs covered (72%): 272 from AcousticBrainz (audio-derived, trusted primary), 585 from GetSongBPM (crowd-reported, backfill only). Every row records its `key_source`. Chord progressions and song structure remain deferred — no clean bulk/legal source found (see Phase 2 research notes in project history).
- [x] Phase 3: Lyrical features — 1,075/1,194 songs (90%) with word count, unique-word ratio, repetition, readability, per-line sentiment, and adjacent-line rhyme density. Known limitation: lexicon-based sentiment can't detect thematic irony (e.g. "shake off the haters" scores net-negative despite the song's upbeat theme, because it contains the word "hate" repeated) — treat sentiment scores as a measure of word-level charge, not overall song mood.
- [ ] Phase 4: Statistical analysis
- [ ] Phase 5: Living pipeline

## Structure

```
data/raw/         # untouched source pulls (with fetch-date metadata)
data/processed/   # cleaned, analysis-ready datasets
src/              # scripts, one per pipeline stage
notebooks/        # exploratory analysis
```
