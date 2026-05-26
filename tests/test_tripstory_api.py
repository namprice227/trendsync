from __future__ import annotations

import importlib
import json
import os
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
            "TRIPSTORY_LLM_MIN_INTERVAL_SECONDS",
            "TRIPSTORY_LLM_MAX_RETRIES",
            "TRIPSTORY_LLM_REASONING_EFFORT",
            "TRIPSTORY_LLM_THINKING",
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
        ):
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        os.environ.pop("TRIPSTORY_MEDIA_DIR", None)
        os.environ.pop("TRIPSTORY_SESSION_STORE", None)
        self.temp_dir.cleanup()

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
        clip_path.write_bytes(b"fake mp4 bytes")
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


if __name__ == "__main__":
    unittest.main()
