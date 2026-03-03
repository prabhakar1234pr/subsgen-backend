"""
agents/music_supervisor.py

Agent 4 — MusicSupervisor
Uses Llama 3.3 70B (Groq) to craft a smart search query,
then hits the Internet Archive search API (no key needed)
filtered strictly to CC0 / public domain audio.

Flow:
  1. LLM refines Brain's music_search_query into best keywords
  2. Internet Archive search API → returns matching CC0 audio items
  3. LLM picks best track from results based on mood/energy
  4. Direct MP3 download from archive.org (no key, no auth)
"""

import json
import logging
import os
import uuid
from pathlib import Path

import httpx
from groq import Groq
from agents.key_manager import next_key, has_keys

logger = logging.getLogger(__name__)
LLM_MODEL = "llama-3.3-70b-versatile"

# ─────────────────────────────────────────────────────────────────────
# Internet Archive Search API — completely free, no key required
# Docs: https://archive.org/advancedsearch.php
# ─────────────────────────────────────────────────────────────────────
IA_SEARCH_URL  = "https://archive.org/advancedsearch.php"
IA_DETAILS_URL = "https://archive.org/metadata/{identifier}"
IA_DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

# Only these licenses are safe to burn into a video (no attribution needed)
SAFE_LICENSE_KEYWORDS = ["publicdomain", "zero/1.0", "cc0"]

# Mood → search keywords that work well on Internet Archive
MOOD_KEYWORDS = {
    "motivational":  "motivational background instrumental",
    "chill":         "chill lofi relaxing instrumental",
    "energy":        "upbeat energetic hype instrumental",
    "uplifting":     "uplifting happy positive instrumental",
    "cinematic":     "cinematic dramatic epic instrumental",
    "educational":   "calm background study instrumental",
    "entertaining":  "fun playful background instrumental",
    "emotional":     "emotional moving touching instrumental",
}


# ─────────────────────────────────────────────────────────────────────
# Step 1 — LLM refines the search query
# ─────────────────────────────────────────────────────────────────────

REFINE_PROMPT = """You are a music supervisor building an Instagram Reel.

The video director wants this music vibe:
  Search query:  "{music_search_query}"
  Overall mood:  {overall_mood}
  Energy level:  {overall_energy}
  Content type:  {content_type}
  Reel hook:     "{caption_hook}"

Your job: produce the best 3-5 word search query for the Internet Archive audio library.
The library has CC0/public domain instrumental background music.
Think: what keywords best describe the SOUND you want, not the content topic.

Examples of good queries:
  "upbeat motivational background instrumental"
  "calm lofi study music"
  "epic cinematic background"
  "happy energetic upbeat"

Respond ONLY with JSON — no explanation, no markdown:
{{"search_query": "your 3-5 word query", "reason": "one sentence"}}"""


def _refine_query(edit_plan: dict) -> str:
    """Use LLM to produce the best Internet Archive search query."""
    fallback_mood = edit_plan.get("overall_mood", "motivational")
    fallback = MOOD_KEYWORDS.get(fallback_mood, "background instrumental music")

    if not has_keys():
        return fallback

    caption = edit_plan.get("caption", {})
    clips   = edit_plan.get("clips", [{}])
    prompt  = REFINE_PROMPT.format(
        music_search_query = edit_plan.get("music_search_query", fallback),
        overall_mood       = edit_plan.get("overall_mood", "motivational"),
        overall_energy     = edit_plan.get("overall_energy", "medium"),
        content_type       = clips[0].get("content_type", "talking_head") if clips else "talking_head",
        caption_hook       = caption.get("hook", ""),
    )

    try:
        client   = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user",   "content": prompt},
            ],
            max_tokens  = 100,
            temperature = 0.2,
        )
        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        query  = result.get("search_query", fallback)
        logger.info(f"[MusicSupervisor] Refined query: '{query}' — {result.get('reason', '')}")
        return query
    except Exception as e:
        logger.warning(f"[MusicSupervisor] Query refinement failed: {e} — using fallback '{fallback}'")
        return fallback


# ─────────────────────────────────────────────────────────────────────
# Step 2 — Search Internet Archive
# ─────────────────────────────────────────────────────────────────────

def _search_internet_archive(query: str, max_results: int = 20) -> list[dict]:
    """
    Search Internet Archive for CC0/public domain audio items.
    Returns list of item dicts with identifier, title, licenseurl.
    No API key required.
    """
    # Build the Lucene query:
    #   mediatype:audio  → only audio items
    #   licenseurl containing publicdomain → CC0 only
    #   subject/title contains our keywords
    ia_query = (
        f'({query}) '
        f'AND mediatype:(audio) '
        f'AND licenseurl:(*publicdomain*)'
    )

    params = {
        "q":        ia_query,
        "fl[]":     ["identifier", "title", "subject", "licenseurl", "description"],
        "rows":     max_results,
        "page":     1,
        "output":   "json",
        "sort[]":   "downloads desc",   # most downloaded first = most popular
    }

    try:
        logger.info(f"[MusicSupervisor] Searching Internet Archive: '{query}'")
        with httpx.Client(timeout=15.0) as client:
            response = client.get(IA_SEARCH_URL, params=params)
            response.raise_for_status()
            data  = response.json()
            items = data.get("response", {}).get("docs", [])
            logger.info(f"[MusicSupervisor] Found {len(items)} CC0 audio items")
            return items
    except Exception as e:
        logger.error(f"[MusicSupervisor] Internet Archive search failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────
# Step 3 — Get MP3 files from a chosen item
# ─────────────────────────────────────────────────────────────────────

def _get_mp3_files(identifier: str) -> list[dict]:
    """
    Fetch metadata for an IA item and return list of MP3 file dicts.
    Each dict has: {name, size, format}
    """
    url = IA_DETAILS_URL.format(identifier=identifier)
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
            metadata = response.json()

        files = metadata.get("files", {})
        mp3s  = []

        for filename, info in files.items():
            fmt = info.get("format", "").lower()
            if "mp3" in fmt or filename.lower().endswith(".mp3"):
                # Strip leading slash from filename if present
                clean_name = filename.lstrip("/")
                size = int(info.get("size", 0))
                # Prefer files between 1MB and 15MB (not too short, not too large)
                if 500_000 < size < 15_000_000:
                    mp3s.append({
                        "name":       clean_name,
                        "size":       size,
                        "identifier": identifier,
                        "url":        IA_DOWNLOAD_URL.format(
                                          identifier=identifier,
                                          filename=clean_name
                                      ),
                    })

        logger.info(f"[MusicSupervisor] Item '{identifier}': {len(mp3s)} usable MP3s")
        return mp3s

    except Exception as e:
        logger.warning(f"[MusicSupervisor] Could not get files for '{identifier}': {e}")
        return []


# ─────────────────────────────────────────────────────────────────────
# Step 4 — LLM picks best item from search results
# ─────────────────────────────────────────────────────────────────────

def _pick_best_item(items: list[dict], edit_plan: dict) -> dict | None:
    """Use LLM to pick the best matching item from search results."""
    if not items:
        return None
    if len(items) == 1 or not has_keys():
        return items[0]

    summaries = [
        {
            "index":   i,
            "title":   item.get("title", "Unknown"),
            "subject": str(item.get("subject", ""))[:100],
        }
        for i, item in enumerate(items[:10])
    ]

    caption = edit_plan.get("caption", {})
    try:
        client   = Groq(api_key=next_key())
        response = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user",   "content":
                    f"Pick the best background music for an Instagram Reel.\n"
                    f"Mood: {edit_plan.get('overall_mood')} | "
                    f"Energy: {edit_plan.get('overall_energy')} | "
                    f"Hook: \"{caption.get('hook', '')}\"\n\n"
                    f"Options:\n{json.dumps(summaries, indent=2)}\n\n"
                    f"Respond ONLY: {{\"chosen_index\": 0, \"reason\": \"one sentence\"}}"
                }
            ],
            max_tokens  = 80,
            temperature = 0.1,
        )
        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        idx    = max(0, min(int(result.get("chosen_index", 0)), len(items) - 1))
        logger.info(
            f"[MusicSupervisor] LLM picked item #{idx}: "
            f"'{items[idx].get('title')}' — {result.get('reason', '')}"
        )
        return items[idx]
    except Exception as e:
        logger.warning(f"[MusicSupervisor] Item picking failed: {e} — using first result")
        return items[0]


# ─────────────────────────────────────────────────────────────────────
# Step 5 — Download the MP3
# ─────────────────────────────────────────────────────────────────────

def _download_mp3(mp3: dict, output_dir: Path) -> Path | None:
    """Download a single MP3 from Internet Archive."""
    out = output_dir / f"music_{uuid.uuid4()}.mp3"
    try:
        logger.info(f"[MusicSupervisor] Downloading: {mp3['url']}")
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(mp3["url"])
            response.raise_for_status()
            out.write_bytes(response.content)
        size_kb = out.stat().st_size / 1024
        logger.info(f"[MusicSupervisor] Downloaded {size_kb:.0f}KB → {out.name}")
        return out
    except Exception as e:
        logger.error(f"[MusicSupervisor] Download failed: {e}")
        if out.exists():
            out.unlink()
        return None


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def find_and_download_music(edit_plan: dict, output_dir: Path) -> Path | None:
    """
    Full music supervisor flow:
      1. LLM refines search query
      2. Search Internet Archive (CC0 only, no API key)
      3. LLM picks best item
      4. Get MP3 file list from item
      5. Download best MP3

    Returns path to downloaded MP3, or None if nothing found.
    """
    logger.info("[MusicSupervisor] Starting music search (Internet Archive, CC0 only)...")

    # Step 1 — refine query
    query = _refine_query(edit_plan)

    # Step 2 — search
    items = _search_internet_archive(query)

    # Fallback: try mood-based keyword if no results
    if not items:
        fallback_mood    = edit_plan.get("overall_mood", "motivational")
        fallback_query   = MOOD_KEYWORDS.get(fallback_mood, "background instrumental")
        logger.info(f"[MusicSupervisor] No results — retrying with fallback: '{fallback_query}'")
        items = _search_internet_archive(fallback_query)

    # Last resort: generic query
    if not items:
        logger.info("[MusicSupervisor] Still no results — trying generic query")
        items = _search_internet_archive("royalty free background music instrumental")

    if not items:
        logger.warning("[MusicSupervisor] No CC0 music found — reel will have no background music")
        return None

    # Step 3 — LLM picks best item
    chosen_item = _pick_best_item(items, edit_plan)
    if not chosen_item:
        return None

    # Step 4 — get MP3 files from that item
    identifier = chosen_item.get("identifier", "")
    mp3s = _get_mp3_files(identifier)

    # If chosen item has no usable MP3s, try next items
    for fallback_item in items[1:5]:
        if mp3s:
            break
        logger.info(f"[MusicSupervisor] No MP3s in '{identifier}', trying next item...")
        identifier = fallback_item.get("identifier", "")
        mp3s       = _get_mp3_files(identifier)

    if not mp3s:
        logger.warning("[MusicSupervisor] No downloadable MP3s found in any item")
        return None

    # Pick the MP3 closest to 3MB (good length for a reel background)
    target_size = 3_000_000
    best_mp3    = min(mp3s, key=lambda f: abs(f["size"] - target_size))

    # Step 5 — download
    return _download_mp3(best_mp3, output_dir)
