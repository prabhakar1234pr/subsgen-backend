"""
agents/flows/reel_flow.py

CrewAI Flow — ReelFlow
Orchestrates the AI reel pipeline: transcribe → analyze → holistic review → edit plan → music.
Returns ReelBlueprint compatible with the existing reel_pipeline router.
"""

import logging
import tempfile
from pathlib import Path

from crewai.flow.flow import Flow, listen, start

from agents.transcriber import transcribe_clip
from agents.video_analyst import analyze_clip
from agents.brain import create_edit_plan
from agents.music_supervisor import find_and_download_music
from agents.holistic_reviewer import create_holistic_review

from agents.flows.state import ReelFlowState

logger = logging.getLogger(__name__)


class ReelFlow(Flow[ReelFlowState]):
    """CrewAI Flow for the AI reel pipeline."""

    @start()
    def ingest_clips(self) -> ReelFlowState:
        """Entry point — clip_paths already set on state before kickoff."""
        n = len(self.state.clip_paths)
        logger.info(f"╔══ ReelFlow starting: {n} clip(s) ══╗")
        return self.state

    @listen(ingest_clips)
    def transcribe_all(self, _state: ReelFlowState) -> ReelFlowState:
        """Transcribe every clip with Groq Whisper Large v3."""
        clip_paths = self.state.clip_paths
        n = len(clip_paths)
        logger.info(f"[1/6] Transcriber — Groq Whisper Large v3")
        transcripts = []
        for i, clip in enumerate(clip_paths):
            logger.info(f"  Transcribing clip {i+1}/{n}: {clip.name}")
            t = transcribe_clip(clip, clip_index=i)
            transcripts.append(t)
            logger.info(f"  → '{t['full_text'][:80]}...' ({len(t.get('words', []))} words)")
        self.state.transcripts = transcripts
        return self.state

    @listen(transcribe_all)
    def analyze_all(self, _state: ReelFlowState) -> ReelFlowState:
        """Visual analysis per clip with Llama 4 Scout VLM."""
        clip_paths = self.state.clip_paths
        transcripts = self.state.transcripts
        n = len(clip_paths)
        logger.info(f"[2/6] VideoAnalyst — Llama 4 Scout VLM")
        analyses = []
        for i, clip in enumerate(clip_paths):
            logger.info(f"  Analyzing clip {i+1}/{n} visually...")
            a = analyze_clip(clip, transcript=transcripts[i], clip_index=i)
            analyses.append(a)
            logger.info(f"  → quality={a.get('visual_quality')}, hook={a.get('visual_hook_strength')}/10")
        self.state.analyses = analyses
        return self.state

    @listen(analyze_all)
    def holistic_review(self, _state: ReelFlowState) -> ReelFlowState:
        """Holistic reviewer — human-like view of all clips (Phase 1 stub)."""
        logger.info(f"[3/6] HolisticReviewer — Phase 1 stub")
        review = create_holistic_review(self.state.transcripts, self.state.analyses)
        self.state.holistic_review = review
        return self.state

    @listen(holistic_review)
    def edit_director(self, _state: ReelFlowState) -> ReelFlowState:
        """EditDirector (Brain) — narrative + edit plan + caption."""
        logger.info(f"[4/6] EditDirector — Llama 3.3 70B")
        edit_plan = create_edit_plan(
            self.state.transcripts,
            self.state.analyses,
            holistic_review=self.state.holistic_review,
        )
        self.state.edit_plan = edit_plan
        kept = [c for c in edit_plan.get("clips", []) if c.get("keep", True)]
        logger.info(f"  → Keeping {len(kept)}/{len(self.state.clip_paths)} clips")
        logger.info(f"  → Style: {edit_plan.get('subtitle_style')}")
        return self.state

    @listen(edit_director)
    def music_supervisor(self, _state: ReelFlowState) -> ReelFlowState:
        """MusicSupervisor — find and download music from Internet Archive."""
        logger.info(f"[5/6] MusicSupervisor — Internet Archive")
        tmp_dir = Path(tempfile.gettempdir())
        music_path = find_and_download_music(self.state.edit_plan, tmp_dir)
        self.state.music_path = music_path
        logger.info(f"  → Music: {'downloaded ✓' if music_path else 'not available'}")
        return self.state

    @listen(music_supervisor)
    def build_blueprint(self, _state: ReelFlowState) -> dict:
        """Build ReelBlueprint from state — same shape as crew.run_ai_pipeline."""
        clip_paths = self.state.clip_paths
        transcripts = self.state.transcripts
        edit_plan = self.state.edit_plan
        music_path = self.state.music_path

        kept_clips = [c for c in edit_plan.get("clips", []) if c.get("keep", True)]
        kept_clips.sort(key=lambda c: c.get("narrative_order", c["clip_index"]))

        ordered_clips = []
        for clip_plan in kept_clips:
            idx = clip_plan["clip_index"]
            clip_path = clip_paths[idx]
            default_dur = transcripts[idx].get("duration_sec") or 0.0
            trim_start = float(clip_plan.get("trim_start_sec") or 0.0)
            trim_end = float(clip_plan.get("trim_end_sec") or default_dur)
            trans_out = clip_plan.get("transition_out") or "fade"
            trans_dur = float(clip_plan.get("transition_duration_sec") or 0.35)
            ordered_clips.append((clip_path, trim_start, trim_end, trans_out, trans_dur))

        all_words = []
        time_cursor = 0.0
        for item in ordered_clips:
            clip_path, trim_start, trim_end = item[0], item[1], item[2]
            idx = next((i for i, p in enumerate(clip_paths) if p == clip_path), 0)
            t = transcripts[idx]
            for w in t.get("words", []):
                if trim_start <= w["start"] <= trim_end:
                    offset_start = time_cursor + (w["start"] - trim_start)
                    offset_end = time_cursor + (min(w["end"], trim_end) - trim_start)
                    all_words.append({
                        "word": w["word"],
                        "start": round(offset_start, 3),
                        "end": round(offset_end, 3),
                    })
            clip_duration = trim_end - trim_start
            time_cursor += clip_duration

        logger.info(f"╚══ ReelFlow complete — {len(all_words)} subtitle words, {len(ordered_clips)} clips ══╝")

        return {
            "ordered_clips": ordered_clips,
            "edit_plan": edit_plan,
            "transcripts": transcripts,
            "analyses": self.state.analyses,
            "music_path": music_path,
            "subtitle_style": edit_plan.get("subtitle_style", "hormozi"),
            "caption": edit_plan.get("caption", {}),
            "all_words": all_words,
        }


def run_reel_flow(clip_paths: list[Path]) -> dict:
    """
    Run the ReelFlow and return the ReelBlueprint.
    Drop-in replacement for run_ai_pipeline.
    """
    flow = ReelFlow()
    flow.state.clip_paths = clip_paths
    return flow.kickoff()
