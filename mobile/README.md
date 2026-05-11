# TrendFlow Mobile

Expo client for the guided TrendFlow workflow.

## Run

Start the Python API from the repository root:

```bash
venv/bin/uvicorn api_server:app --host 0.0.0.0 --port 8010
```

Then install and run the mobile app:

```bash
cd mobile
npm install
npm run start
```

Android emulator default API URL:

```text
http://10.0.2.2:8010
```

Physical Android device:

```text
http://<your-computer-lan-ip>:8010
```

## Flow

The app does not expose manual workflow tabs. It follows the server session phase:

```text
awaiting_reference -> analyzing -> ready_to_film -> needs_adjustment
-> ready_to_record -> uploading -> rendering -> evaluating -> complete
```

When analysis finishes, the UI moves into Studio. When pre-flight returns `ready_to_record`, the app counts down, records the shot, uploads it, and either continues to the next shot or moves into Output for render and evaluation.
