from __future__ import annotations

import importlib
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
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "DEEPSEEK_API_KEY",
        ):
            os.environ.pop(key, None)

        import api_server

        self.api_server = importlib.reload(api_server)

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

        self.api_server._render_background(session_id)
        rendered = self.api_server._public_session(session_id)
        self.assertEqual(rendered["phase"], "complete")
        self.assertTrue(rendered["final_video_url"].endswith("holiday_recap.mp4"))
        self.assertTrue((self.media_root / session_id / "holiday_recap.mp4").exists())
        self.assertTrue((self.media_root / session_id / "story_plan.json").exists())
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

        cases = [
            ("openai", "https://api.openai.com/v1", "gpt-4o-mini"),
            ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash"),
            ("deepseek", "https://api.deepseek.com", "deepseek-chat"),
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


if __name__ == "__main__":
    unittest.main()
