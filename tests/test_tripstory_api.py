from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class TripStoryApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.media_root = Path(self.temp_dir.name) / "media"
        self.session_store = Path(self.temp_dir.name) / "sessions.json"
        os.environ["TRIPSTORY_MEDIA_DIR"] = str(self.media_root)
        os.environ["TRIPSTORY_SESSION_STORE"] = str(self.session_store)
        for key in (
            "TRIPSTORY_LLM_PROVIDER",
            "TRIPSTORY_LLM_URL",
            "TRIPSTORY_LLM_API_KEY",
            "TRIPSTORY_LLM_MODEL",
            "TRIPSTORY_LLM_TIMEOUT",
            "TRIPSTORY_LLM_MIN_INTERVAL_SECONDS",
            "TRIPSTORY_LLM_MAX_RETRIES",
            "TRIPSTORY_LLM_REASONING_EFFORT",
            "TRIPSTORY_LLM_THINKING",
            "TRIPSTORY_STORY_MAX_TOKENS",
            "TRIPSTORY_DEEPSEEK_THINKING",
            "TRIPSTORY_DEEPSEEK_REASONING_EFFORT",
            "TRIPSTORY_VISION_PROVIDER",
            "TRIPSTORY_VISION_MODEL",
            "TRIPSTORY_GEMINI_VISION_MODEL",
            "TRIPSTORY_OPENAI_VISION_MODEL",
            "TRIPSTORY_ENABLE_VISION_ANALYSIS",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "TRIPSTORY_TTS_PROVIDER",
            "TRIPSTORY_TTS_MODEL",
            "TRIPSTORY_TTS_VOICE",
            "TRIPSTORY_ENABLE_TRANSCRIPTION",
            "TRIPSTORY_SESSION_DB",
            "TRIPSTORY_SQLITE_TIMEOUT_SECONDS",
            "TRIPSTORY_QUEUE_BACKEND",
            "TRIPSTORY_REDIS_URL",
            "TRIPSTORY_QUEUE_NAME",
            "TRIPSTORY_JOB_TIMEOUT_SECONDS",
            "TRIPSTORY_LOG_LEVEL",
            "TRIPSTORY_LOG_FILE",
            "TRIPSTORY_LOG_API_PAYLOADS",
            "TRIPSTORY_LOG_HTTP_REQUESTS",
        ):
            os.environ.pop(key, None)

        import api_server

        self.api_server = importlib.reload(api_server)
        for key in (
            "TRIPSTORY_LLM_PROVIDER",
            "TRIPSTORY_LLM_URL",
            "TRIPSTORY_LLM_API_KEY",
            "TRIPSTORY_LLM_MODEL",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
            "TRIPSTORY_TTS_PROVIDER",
            "TRIPSTORY_QUEUE_BACKEND",
        ):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.pop("TRIPSTORY_MEDIA_DIR", None)
        os.environ.pop("TRIPSTORY_SESSION_STORE", None)
        self.temp_dir.cleanup()

    def _write_test_video(self, path: Path, seconds: float = 3.0) -> None:
        from media_tools import ffmpeg_bin

        ffmpeg = ffmpeg_bin()
        if not ffmpeg:
            self.skipTest("ffmpeg is required for render integration tests")
        subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=size=320x240:rate=25:duration={seconds:.2f}",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )

    def test_tripstory_mvp_flow_persists_and_renders(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]

        context = {
            "destination": "Kyoto",
            "duration": "5 days",
            "places_visited": "Gion, Arashiyama, Nishiki Market",
            "travel_dates": "April 2026",
            "companions": "family",
            "highlights": "sunset by the river",
            "mood": "warm and reflective",
            "audience": "friends and family",
            "language": "en",
            "notes": "",
            "llm_provider": "local",
            "llm_model": "",
        }
        self.api_server._update_session(session_id, trip_context=context, phase="collecting_context")

        media_dir = self.media_root / session_id / "media"
        media_dir.mkdir(parents=True)
        clip_path = media_dir / "000_clip.mp4"
        self._write_test_video(clip_path)
        media_item = {
            "id": "clip1",
            "filename": "clip.mp4",
            "kind": "video",
            "path": str(clip_path),
            "url": f"/files/{session_id}/media/{clip_path.name}",
            "size_bytes": clip_path.stat().st_size,
        }
        uploaded = self.api_server._update_session(
            session_id,
            phase="ready_to_plan",
            media_items=[media_item],
            recorded_clips=[str(clip_path)],
        )
        self.assertEqual(uploaded["phase"], "ready_to_plan")

        self.api_server._generate_story_background(session_id)
        planned = self.api_server._public_session(session_id)
        self.assertEqual(planned["phase"], "ready_to_render")
        self.assertIn("Kyoto", planned["story_plan"]["title"])
        self.assertTrue(planned["script"])
        self.assertTrue(planned["story_plan"]["edit_decisions"])
        self.assertTrue(planned["story_plan"]["voiceover_segments"])
        self.assertEqual(
            planned["story_plan"]["edit_decisions"][0]["clip_id"],
            planned["story_plan"]["voiceover_segments"][0]["clip_id"],
        )
        self.assertNotIn("1280x720", planned["script"])
        self.assertNotIn("face hits", planned["script"])
        self.assertIn("reason", planned["story_plan"]["edit_decisions"][0])
        self.assertFalse(planned["story_plan"]["generation"]["llm_used"])
        planning_events = [event["label"] for event in planned["events"]]
        self.assertIn("Analyzing trip brief and clip intelligence", planning_events)
        self.assertIn("Using local fallback because local is not configured", planning_events)
        self.assertIn("Narrative plan generated with local fallback", planning_events)

        self.api_server._render_background(session_id)
        rendered = self.api_server._public_session(session_id)
        self.assertEqual(rendered["phase"], "complete")
        self.assertTrue(rendered["final_video_url"].endswith("holiday_recap.mp4"))
        self.assertTrue(rendered["edit_decisions_url"].endswith("edit_decisions.json"))
        self.assertIsNone(rendered["voiceover_audio_url"])
        self.assertTrue((self.media_root / session_id / "holiday_recap.mp4").exists())
        self.assertTrue((self.media_root / session_id / "story_plan.json").exists())
        self.assertTrue((self.media_root / session_id / "edit_decisions.json").exists())
        self.assertTrue(self.session_store.exists())
        render_events = [event["label"] for event in rendered["events"]]
        self.assertIn("Preparing story-aware render", render_events)
        self.assertIn("Writing captions and edit decisions", render_events)
        self.assertIn("Render finished", render_events)

        reloaded = importlib.reload(self.api_server)
        persisted = reloaded._public_session(session_id)
        self.assertEqual(persisted["phase"], "complete")

    def test_trip_context_does_not_accept_or_expose_api_keys(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]
        request = self.api_server.TripContextRequest(
            destination="Paris",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )

        updated = self.api_server.save_context(session_id, request)

        self.assertEqual(updated["trip_context"]["llm_provider"], "openai")
        self.assertNotIn("llm_api_key", updated["trip_context"])
        public = self.api_server._public_session(session_id)
        self.assertNotIn("llm_api_key", public["trip_context"])

    def test_session_poll_logs_structured_http_state(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]

        fields = self.api_server._session_status_fields(f"/sessions/{session_id}", 200)

        self.assertEqual(fields["session_phase"], "collecting_context")
        self.assertEqual(fields["session_screen"], "context")
        self.assertEqual(fields["session_progress_percent"], 0)
        self.assertEqual(fields["media_count"], 0)
        self.assertFalse(fields["final_video_ready"])

    def test_session_timestamps_are_normalized_for_listing_sort(self) -> None:
        first = self.api_server._create_session()
        second = self.api_server._create_session()
        with self.api_server._connect_db() as conn:
            first_data = json.loads(conn.execute("SELECT data FROM sessions WHERE id = ?", (first["id"],)).fetchone()[0])
            first_data["updated_at"] = "2000000000"
            conn.execute(
                "UPDATE sessions SET updated_at = ?, data = ? WHERE id = ?",
                (2000000000.0, json.dumps(first_data), first["id"]),
            )
            conn.commit()

        listed = self.api_server.list_sessions()

        self.assertEqual(listed["sessions"][0]["id"], first["id"])
        self.assertIsInstance(self.api_server._normalize_session({"id": first["id"], "updated_at": "200"})["updated_at"], float)

    def test_generate_story_endpoint_enqueues_rq_job(self) -> None:
        from unittest.mock import patch

        session = self.api_server._create_session()
        session_id = session["id"]
        context = dict(session["trip_context"])
        context.update({"destination": "Kyoto", "llm_provider": "local"})
        self.api_server._update_session(
            session_id,
            trip_context=context,
            media_items=[{"id": "clip1", "filename": "clip.mp4", "kind": "video", "path": "clip.mp4", "analysis": {}}],
            recorded_clips=["clip.mp4"],
            phase="ready_to_plan",
        )
        os.environ["TRIPSTORY_QUEUE_BACKEND"] = "rq"
        with patch.object(self.api_server, "_enqueue_rq_job", return_value="rq-story-1") as enqueue:
            queued = self.api_server.generate_story(session_id)

        enqueue.assert_called_once()
        self.assertEqual(queued["phase"], "planning")
        self.assertIsNotNone(queued["active_job"])
        self.assertEqual(queued["active_job"]["type"], "story_generation")
        self.assertEqual(queued["active_job"]["state"], "queued")
        self.assertEqual(queued["active_job"]["rq_job_id"], "rq-story-1")

        job = self.api_server.get_job(session_id, queued["active_job"]["id"])
        self.assertEqual(job["session_id"], session_id)
        self.assertEqual(job["type"], "story_generation")
        os.environ.pop("TRIPSTORY_QUEUE_BACKEND", None)

    def test_render_endpoint_enqueues_rq_job(self) -> None:
        from unittest.mock import patch

        session = self.api_server._create_session()
        session_id = session["id"]
        self.api_server._update_session(
            session_id,
            story_plan={"title": "Kyoto", "voiceover_script": "A trip begins.", "edit_decisions": []},
            recorded_clips=["clip.mp4"],
            phase="ready_to_render",
        )
        os.environ["TRIPSTORY_QUEUE_BACKEND"] = "rq"
        with patch.object(self.api_server, "_enqueue_rq_job", return_value="rq-render-1") as enqueue:
            queued = self.api_server.render_session(session_id, self.api_server.RenderRequest())

        enqueue.assert_called_once()
        self.assertEqual(queued["phase"], "rendering")
        self.assertIsNotNone(queued["active_job"])
        self.assertEqual(queued["active_job"]["type"], "render")
        self.assertEqual(queued["active_job"]["rq_job_id"], "rq-render-1")
        os.environ.pop("TRIPSTORY_QUEUE_BACKEND", None)

    def test_worker_completes_story_generation_job(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]
        context = dict(session["trip_context"])
        context.update({"destination": "Kyoto", "llm_provider": "local"})
        self.api_server._update_session(
            session_id,
            trip_context=context,
            media_items=[{"id": "clip1", "filename": "clip.mp4", "kind": "video", "path": "clip.mp4", "analysis": {}}],
            recorded_clips=["clip.mp4"],
            phase="planning",
        )
        job = self.api_server._create_job(session_id, "story_generation", "Queued story generation")

        self.api_server.run_queued_job(job["id"])

        completed = self.api_server._get_job(job["id"])
        planned = self.api_server._public_session(session_id)
        self.assertEqual(completed["state"], "complete")
        self.assertEqual(completed["progress_percent"], 100)
        self.assertEqual(planned["phase"], "ready_to_render")
        self.assertIsNone(planned["active_job"])

    def test_worker_marks_failed_job_and_session_error(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]
        job = self.api_server._create_job(session_id, "story_generation", "Queued story generation")

        self.api_server.run_queued_job(job["id"])

        failed = self.api_server._get_job(job["id"])
        public = self.api_server._public_session(session_id)
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(public["phase"], "error")
        self.assertIn("Upload at least one", public["error"])

    def test_stale_active_job_expires_on_session_poll(self) -> None:
        session = self.api_server._create_session()
        session_id = session["id"]
        self.api_server._update_session(session_id, phase="planning", progress_percent=35)
        job = self.api_server._create_job(session_id, "story_generation", "Queued story generation")
        stale_updated_at = self.api_server._now() - self.api_server.DEFAULT_STALE_JOB_SECONDS - 10
        with self.api_server._connect_db() as conn:
            conn.execute(
                "UPDATE jobs SET state = ?, progress_percent = ?, current_step = ?, updated_at = ? WHERE id = ?",
                ("analyzing", 35, "Analyzing trip brief and clip intelligence", stale_updated_at, job["id"]),
            )
            conn.commit()

        public = self.api_server._public_session(session_id)
        expired = self.api_server._get_job(job["id"])

        self.assertIsNone(public["active_job"])
        self.assertEqual(public["phase"], "error")
        self.assertEqual(expired["state"], "failed")
        self.assertIn("interrupted", public["error"])

    def test_sqlite_connections_use_wal_and_busy_timeout(self) -> None:
        with self.api_server._connect_db() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(busy_timeout, int(self.api_server.SQLITE_TIMEOUT_SECONDS * 1000))

    def test_provider_presets_configure_openai_compatible_endpoints(self) -> None:
        from llm_provider import LLMProvider

        for key in ("TRIPSTORY_OPENAI_MODEL", "TRIPSTORY_GEMINI_MODEL", "TRIPSTORY_DEEPSEEK_MODEL", "TRIPSTORY_LLM_MODEL"):
            os.environ.pop(key, None)

        cases = [
            ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
            ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
            ("deepseek", "https://api.deepseek.com", "deepseek-v4-pro"),
        ]

        for provider_name, base_url, model in cases:
            with self.subTest(provider=provider_name):
                env_key = f"{provider_name.upper()}_API_KEY"
                if provider_name == "gemini":
                    env_key = "GEMINI_API_KEY"
                os.environ[env_key] = "test-key"
                provider = LLMProvider(provider=provider_name)
                self.assertTrue(provider.configured)
                self.assertEqual(provider.base_url, base_url)
                self.assertEqual(provider.model, model)
                os.environ.pop(env_key, None)

        self.assertFalse(LLMProvider(provider="local").configured)

    def test_env_provider_is_used_when_context_provider_is_local(self) -> None:
        from llm_provider import LLMProvider

        os.environ["TRIPSTORY_LLM_PROVIDER"] = "openai"
        os.environ["OPENAI_API_KEY"] = "test-key"
        provider = LLMProvider(provider=None)
        self.assertEqual(provider.provider, "openai")
        self.assertTrue(provider.configured)
        os.environ.pop("TRIPSTORY_LLM_PROVIDER", None)
        os.environ.pop("OPENAI_API_KEY", None)

    def test_deepseek_is_default_text_provider_when_key_exists(self) -> None:
        from llm_provider import LLMProvider

        os.environ.pop("TRIPSTORY_LLM_PROVIDER", None)
        os.environ.pop("TRIPSTORY_LLM_URL", None)
        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        provider = LLMProvider(provider=None)
        self.assertEqual(provider.provider, "deepseek")
        self.assertTrue(provider.configured)
        os.environ.pop("DEEPSEEK_API_KEY", None)

    def test_gemini_is_default_vision_provider_when_key_exists(self) -> None:
        from media_intelligence import _vision_provider_config, vision_semantics_source

        os.environ.pop("TRIPSTORY_VISION_PROVIDER", None)
        os.environ["GEMINI_API_KEY"] = "test-key"
        self.assertEqual(vision_semantics_source(), "gemini_vision")
        os.environ["TRIPSTORY_VISION_MODEL"] = "gpt-4o-mini"
        self.assertEqual(_vision_provider_config()["model"], "gemini-2.0-flash")
        os.environ["TRIPSTORY_ENABLE_VISION_ANALYSIS"] = "0"
        self.assertIsNone(vision_semantics_source())
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("TRIPSTORY_VISION_MODEL", None)
        os.environ.pop("TRIPSTORY_ENABLE_VISION_ANALYSIS", None)

    def test_llm_provider_rate_limit_defaults_are_configurable(self) -> None:
        from llm_provider import LLMProvider

        os.environ["TRIPSTORY_LLM_MIN_INTERVAL_SECONDS"] = "0.5"
        os.environ["TRIPSTORY_LLM_MAX_RETRIES"] = "4"
        provider = LLMProvider(provider="local")
        self.assertEqual(provider.min_interval, 0.5)
        self.assertEqual(provider.max_retries, 4)
        os.environ.pop("TRIPSTORY_LLM_MIN_INTERVAL_SECONDS", None)
        os.environ.pop("TRIPSTORY_LLM_MAX_RETRIES", None)

    def test_story_generation_normalizes_malformed_llm_shapes(self) -> None:
        from trip_story import generate_trip_story

        class MalformedProvider:
            provider = "deepseek"
            model = "deepseek-chat"
            configured = True

            def chat(self, messages, max_tokens=900):
                return json.dumps(
                    {
                        "title": ["Bad shape title"],
                        "language": {"name": "English"},
                        "narrative_arc": "Open\nMiddle\nClose",
                        "voiceover_script": ["Line one", "Line two"],
                        "edit_notes": {"note": "Use best clip"},
                        "clip_plan": "clip.mp4",
                        "edit_decisions": {
                            "clip": "clip.mp4",
                            "start_time": "1.5",
                            "duration": "4",
                            "reason": "Strong moment",
                        },
                        "voiceover_segments": {
                            "clip": "clip.mp4",
                            "start_time": "1.5",
                            "duration": "4",
                            "voiceover": "This line belongs to the selected clip.",
                        },
                    }
                )

        plan = generate_trip_story(
            {"destination": "Kyoto", "language": "en"},
            [{"id": "clip1", "filename": "clip.mp4", "kind": "video", "size_bytes": 100, "analysis": {}}],
            MalformedProvider(),
        )

        self.assertIsInstance(plan["title"], str)
        self.assertIsInstance(plan["narrative_arc"], list)
        self.assertIsInstance(plan["edit_notes"], list)
        self.assertIsInstance(plan["clip_plan"], list)
        self.assertIsInstance(plan["edit_decisions"], list)
        self.assertIsInstance(plan["voiceover_segments"], list)
        self.assertIsInstance(plan["edit_decisions"][0]["duration"], float)
        self.assertIn("selected clip", plan["voiceover_script"])
        self.assertTrue(plan["generation"]["llm_used"])

    def test_story_generation_repairs_technical_voiceover_for_audience(self) -> None:
        from trip_story import generate_trip_story

        class TechnicalProvider:
            provider = "deepseek"
            model = "deepseek-chat"
            configured = True

            def chat(self, messages, max_tokens=900):
                return json.dumps(
                    {
                        "title": "Tromso Story",
                        "language": "English",
                        "voiceover_script": "In Tromso, this moment shows 25.19s, 1280x720, 1 scenes, strong quality, 9 face hits, audio present.",
                        "edit_decisions": [
                            {
                                "clip_id": "clip1",
                                "clip": "tromso.mp4",
                                "start_time": 2,
                                "duration": 5,
                                "reason": "Strong faces and ambience.",
                            }
                        ],
                        "voiceover_segments": [
                            {
                                "clip_id": "clip1",
                                "clip": "tromso.mp4",
                                "voiceover": "In Tromso, this moment shows 25.19s, 1280x720, 1 scenes, strong quality, 9 face hits, audio present.",
                            }
                        ],
                    }
                )

        plan = generate_trip_story(
            {"destination": "Tromso, Norway", "language": "en", "highlights": "northern lights"},
            [
                {
                    "id": "clip1",
                    "filename": "tromso.mp4",
                    "kind": "video",
                    "size_bytes": 100,
                    "analysis": {
                        "duration_seconds": 25.19,
                        "width": 1280,
                        "height": 720,
                        "scene_count": 1,
                        "quality_label": "strong",
                        "face_count": 9,
                        "has_audio": True,
                        "summary": "25.19s, 1280x720, 1 scenes, strong quality, 9 face hits, audio present",
                    },
                }
            ],
            TechnicalProvider(),
        )

        self.assertNotIn("1280x720", plan["voiceover_script"])
        self.assertNotIn("face hits", plan["voiceover_script"])
        self.assertNotIn("audio present", plan["voiceover_script"])
        self.assertIn("Tromso", plan["voiceover_script"])
        self.assertTrue(plan["generation"]["llm_used"])

    def test_story_generation_sends_compact_manifest_not_raw_analysis(self) -> None:
        from trip_story import generate_trip_story

        captured = {}

        class CapturingProvider:
            provider = "deepseek"
            model = "deepseek-v4-pro"
            configured = True

            def chat(self, messages, max_tokens=900):
                captured["messages"] = messages
                return json.dumps(
                    {
                        "title": "Compact Story",
                        "language": "English",
                        "edit_decisions": [
                            {
                                "clip_id": "clip1",
                                "clip": "clip.mp4",
                                "start_time": 4,
                                "duration": 5,
                                "reason": "Opening beat with visible mountain hike energy.",
                            }
                        ],
                        "voiceover_segments": [
                            {
                                "clip_id": "clip1",
                                "clip": "clip.mp4",
                                "voiceover": "This is the moment the trip starts feeling real.",
                            }
                        ],
                    }
                )

        generate_trip_story(
            {"destination": "Tromso", "language": "en"},
            [
                {
                    "id": "clip1",
                    "filename": "clip.mp4",
                    "kind": "video",
                    "size_bytes": 100,
                    "analysis": {
                        "duration_seconds": 12.5,
                        "width": 1280,
                        "height": 720,
                        "scene_count": 1,
                        "quality_label": "strong",
                        "face_count": 2,
                        "avg_motion": 31,
                        "has_audio": True,
                        "semantic_summary": "A man is walking on a snowy mountain trail with wind and friends nearby.",
                        "best_moment_timestamps": [4.2, 8.8],
                        "landmark_candidate_timestamps": [6.0],
                        "transcript": "This raw transcript is intentionally long and should not be copied wholesale into the prompt.",
                    },
                }
            ],
            CapturingProvider(),
        )

        user_payload = json.loads(captured["messages"][1]["content"])
        prompt_text = captured["messages"][1]["content"]
        self.assertIn("clip_manifest", user_payload)
        self.assertNotIn("uploaded_media", user_payload)
        self.assertNotIn('"analysis"', prompt_text)
        self.assertNotIn('"width"', prompt_text)
        self.assertNotIn("1280", prompt_text)
        self.assertNotIn("face_count", prompt_text)
        self.assertIn("[Clip clip1] 12s", user_payload["clip_manifest"][0])
        self.assertIn("snowy mountain", user_payload["clip_manifest"][0])

    def test_story_generation_uses_configurable_output_budget(self) -> None:
        from trip_story import generate_trip_story

        captured = {}

        class CapturingProvider:
            provider = "deepseek"
            model = "deepseek-v4-flash"
            configured = True

            def chat(self, messages, max_tokens=900):
                captured["max_tokens"] = max_tokens
                return json.dumps(
                    {
                        "title": "Enough Budget",
                        "language": "English",
                        "edit_decisions": [
                            {
                                "clip_id": "clip1",
                                "clip": "clip.mp4",
                                "start_time": 0,
                                "duration": 4,
                                "reason": "Opening travel beat.",
                            }
                        ],
                        "voiceover_segments": [
                            {
                                "clip_id": "clip1",
                                "clip": "clip.mp4",
                                "voiceover": "The trip begins with a quiet first step.",
                            }
                        ],
                    }
                )

        os.environ["TRIPSTORY_STORY_MAX_TOKENS"] = "4096"
        plan = generate_trip_story(
            {"destination": "Tromso", "language": "en"},
            [{"id": "clip1", "filename": "clip.mp4", "kind": "video", "size_bytes": 100, "analysis": {}}],
            CapturingProvider(),
        )

        self.assertEqual(captured["max_tokens"], 4096)
        self.assertTrue(plan["generation"]["llm_used"])

    def test_story_generation_empty_configured_provider_reports_empty_response(self) -> None:
        from trip_story import generate_trip_story

        class EmptyProvider:
            provider = "deepseek"
            model = "deepseek-v4-flash"
            configured = True

            def chat(self, messages, max_tokens=900):
                return ""

        plan = generate_trip_story(
            {"destination": "Tromso", "language": "en"},
            [{"id": "clip1", "filename": "clip.mp4", "kind": "video", "size_bytes": 100, "analysis": {}}],
            EmptyProvider(),
        )

        reason = plan["generation"]["fallback_reason"]
        self.assertFalse(plan["generation"]["llm_used"])
        self.assertTrue(plan["generation"]["llm_configured"])
        self.assertIn("empty response", reason)
        self.assertNotIn("not configured", reason)

    def test_deepseek_payload_supports_thinking_and_reasoning_env(self) -> None:
        from llm_provider import LLMProvider
        from unittest.mock import patch

        captured = {}

        class FakeResponse:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "{}"}}]}

        def fake_post(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

        os.environ["DEEPSEEK_API_KEY"] = "test-key"
        os.environ["TRIPSTORY_DEEPSEEK_MODEL"] = "deepseek-v4-pro"
        os.environ["TRIPSTORY_DEEPSEEK_THINKING"] = "enabled"
        os.environ["TRIPSTORY_DEEPSEEK_REASONING_EFFORT"] = "high"
        with patch("llm_provider.requests.post", side_effect=fake_post):
            LLMProvider(provider="deepseek").chat([{"role": "user", "content": "Hello!"}])

        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["json"]["model"], "deepseek-v4-pro")
        self.assertEqual(captured["json"]["thinking"], {"type": "enabled"})
        self.assertEqual(captured["json"]["reasoning_effort"], "high")
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("TRIPSTORY_DEEPSEEK_MODEL", None)
        os.environ.pop("TRIPSTORY_DEEPSEEK_THINKING", None)
        os.environ.pop("TRIPSTORY_DEEPSEEK_REASONING_EFFORT", None)

    def test_tts_provider_uses_server_environment_only(self) -> None:
        from tts_provider import TTSProvider

        os.environ["TRIPSTORY_TTS_PROVIDER"] = "disabled"
        self.assertFalse(TTSProvider().configured)
        os.environ.pop("TRIPSTORY_TTS_PROVIDER", None)
        os.environ["OPENAI_API_KEY"] = "test-key"
        provider = TTSProvider()
        self.assertTrue(provider.configured)
        self.assertEqual(provider.model, "gpt-4o-mini-tts")
        self.assertEqual(provider.voice, "coral")
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ["TRIPSTORY_TTS_PROVIDER"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "test-gemini-key"
        provider = TTSProvider()
        self.assertTrue(provider.configured)
        self.assertEqual(provider.model, "gemini-3.1-flash-tts-preview")
        self.assertEqual(provider.voice, "Kore")
        os.environ.pop("TRIPSTORY_TTS_PROVIDER", None)
        os.environ.pop("GEMINI_API_KEY", None)

    def test_gemini_tts_writes_wave_audio(self) -> None:
        from tts_provider import TTSProvider
        from unittest.mock import patch

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": "audio/pcm",
                                            "data": base64.b64encode(b"\x00\x00\x01\x00").decode("ascii"),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }

        captured: dict[str, object] = {}

        def fake_post(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers")
            captured["json"] = kwargs.get("json")
            return FakeResponse()

        os.environ["TRIPSTORY_TTS_PROVIDER"] = "gemini"
        os.environ["GEMINI_API_KEY"] = "gemini-secret"
        os.environ["TRIPSTORY_TTS_MIN_INTERVAL_SECONDS"] = "0"
        target = Path(self.temp_dir.name) / "voiceover.wav"
        with patch("tts_provider.requests.post", side_effect=fake_post):
            output_path = TTSProvider().synthesize("This is the narration.", target, instructions="Say warmly.")

        self.assertEqual(output_path, str(target))
        self.assertTrue(target.read_bytes().startswith(b"RIFF"))
        self.assertEqual(captured["url"], "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent")
        self.assertEqual(captured["headers"]["x-goog-api-key"], "gemini-secret")
        payload = captured["json"]
        self.assertEqual(payload["generationConfig"]["responseModalities"], ["AUDIO"])
        self.assertEqual(payload["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"], "Kore")
        os.environ.pop("TRIPSTORY_TTS_PROVIDER", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("TRIPSTORY_TTS_MIN_INTERVAL_SECONDS", None)

    def test_renderer_ffmpeg_commands_are_noninteractive_and_bounded(self) -> None:
        from trip_renderer import _make_title_card
        from unittest.mock import patch

        target = Path(self.temp_dir.name) / "title.mp4"
        with patch("trip_renderer.subprocess.run") as run:
            _make_title_card(target, {"title": "Tromso"}, {"duration": "2 days"}, "landscape")

        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(Path(command[0]).name, "ffmpeg")
        self.assertEqual(command[1], "-nostdin")
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertGreater(kwargs["timeout"], 0)

    def test_audio_mix_ffmpeg_commands_are_noninteractive_and_bounded(self) -> None:
        from tts_provider import mix_narration
        from unittest.mock import patch

        with patch("tts_provider.audio_stream_exists", return_value=False), patch("tts_provider.subprocess.run") as run:
            mix_narration(Path(self.temp_dir.name) / "video.mp4", Path(self.temp_dir.name) / "voiceover.wav", Path(self.temp_dir.name) / "mixed.mp4")

        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertEqual(Path(command[0]).name, "ffmpeg")
        self.assertEqual(command[1], "-nostdin")
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertGreater(kwargs["timeout"], 0)

    def test_renderer_scales_timeline_to_target_duration(self) -> None:
        from trip_renderer import _apply_target_duration

        timeline = [
            ({"id": "a"}, {"duration": 10}),
            ({"id": "b"}, {"duration": 10}),
            ({"id": "c"}, {"duration": 10}),
        ]
        adjusted = _apply_target_duration(timeline, {"target_duration_seconds": 17}, True, 6)

        self.assertLessEqual(sum(decision["duration"] for _, decision in adjusted) + 2, 17.01)
        self.assertTrue(all(decision["duration"] >= 1 for _, decision in adjusted))

    def test_llm_and_tts_logs_attempts_retries_without_secrets(self) -> None:
        from llm_provider import LLMProvider
        from tts_provider import TTSProvider
        from unittest.mock import patch

        class FakeResponse:
            def __init__(self, status_code: int, payload: dict | None = None, content: bytes = b"audio") -> None:
                self.status_code = status_code
                self.headers = {"Retry-After": "0"} if status_code == 429 else {}
                self._payload = payload or {"choices": [{"message": {"content": "Story JSON"}}]}
                self.content = content

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(f"HTTP {self.status_code}")
                return None

            def json(self):
                return self._payload

        os.environ["DEEPSEEK_API_KEY"] = "sk-test-secret-llm"
        os.environ["TRIPSTORY_LLM_MIN_INTERVAL_SECONDS"] = "0"
        os.environ["TRIPSTORY_LLM_MAX_RETRIES"] = "1"
        with self.assertLogs("tripstory.llm", level="INFO") as llm_logs:
            with patch("llm_provider.requests.post", side_effect=[FakeResponse(429), FakeResponse(200)]):
                result = LLMProvider(provider="deepseek").chat([{"role": "user", "content": "private trip context"}])

        self.assertEqual(result, "Story JSON")
        llm_output = "\n".join(llm_logs.output)
        self.assertIn("llm_request_attempt", llm_output)
        self.assertIn("llm_request_retry", llm_output)
        self.assertIn("llm_request_complete", llm_output)
        self.assertNotIn("sk-test-secret-llm", llm_output)
        self.assertNotIn("private trip context", llm_output)

        os.environ["OPENAI_API_KEY"] = "sk-test-secret-tts"
        os.environ["TRIPSTORY_TTS_MIN_INTERVAL_SECONDS"] = "0"
        os.environ["TRIPSTORY_TTS_MAX_RETRIES"] = "1"
        tts_target = Path(self.temp_dir.name) / "voiceover.mp3"
        with self.assertLogs("tripstory.tts", level="INFO") as tts_logs:
            with patch("tts_provider.requests.post", side_effect=[FakeResponse(429), FakeResponse(200, content=b"mp3")]):
                output_path = TTSProvider().synthesize("This is private narration.", tts_target)

        self.assertEqual(output_path, str(tts_target))
        tts_output = "\n".join(tts_logs.output)
        self.assertIn("tts_request_attempt", tts_output)
        self.assertIn("tts_request_retry", tts_output)
        self.assertIn("tts_request_complete", tts_output)
        self.assertNotIn("sk-test-secret-tts", tts_output)
        self.assertNotIn("This is private narration", tts_output)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("TRIPSTORY_LLM_MIN_INTERVAL_SECONDS", None)
        os.environ.pop("TRIPSTORY_LLM_MAX_RETRIES", None)
        os.environ.pop("TRIPSTORY_TTS_MIN_INTERVAL_SECONDS", None)
        os.environ.pop("TRIPSTORY_TTS_MAX_RETRIES", None)

    def test_llm_retries_read_timeout(self) -> None:
        import requests
        from llm_provider import LLMProvider
        from unittest.mock import patch

        class FakeResponse:
            status_code = 200
            headers: dict[str, str] = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "Story JSON"}}]}

        os.environ["DEEPSEEK_API_KEY"] = "sk-test-secret-llm"
        os.environ["TRIPSTORY_LLM_TIMEOUT"] = "120"
        os.environ["TRIPSTORY_LLM_MIN_INTERVAL_SECONDS"] = "0"
        os.environ["TRIPSTORY_LLM_MAX_RETRIES"] = "1"
        with patch("llm_provider.random.uniform", return_value=0), patch("llm_provider.time.sleep"):
            with patch("llm_provider.requests.post", side_effect=[requests.ReadTimeout("slow"), FakeResponse()]) as post:
                result = LLMProvider(provider="deepseek").chat([{"role": "user", "content": "private trip context"}])

        self.assertEqual(result, "Story JSON")
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs["timeout"], 120)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("TRIPSTORY_LLM_TIMEOUT", None)
        os.environ.pop("TRIPSTORY_LLM_MIN_INTERVAL_SECONDS", None)
        os.environ.pop("TRIPSTORY_LLM_MAX_RETRIES", None)


if __name__ == "__main__":
    unittest.main()
