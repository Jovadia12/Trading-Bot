# "Why TradeFlow?" — cinematic product demo

`tradeflow_promo.mp4` — 78.5 s, 1920×1080, 60 fps, H.264 + AAC (voiceover, music, UI sounds, -16 LUFS).

Built from the real screen recording (Oct 5, 2026). Footage is used unaltered (browser chrome cropped);
camera moves, highlights, captions and section labels are overlays.

| Section | Source clip (recording time) |
|---|---|
| Opening + Dashboard | 0.3 s (held) |
| Economic Calendar | 10.0–12.5 s (slowed) |
| P&L Calendar | 22.6–27.6 s (month navigation to Jan 2026) |
| Paper Trading | 32.5–35.2 s (chart loading) |
| Payout Tracker | 39.5–44.4 s (request $5000) + 47.0–47.7 s (history) |
| Closing | Dashboard, pull-back, end card |

The recording's final section (ChatGPT, ~57 s onward) is not used.

Rebuild: `bash extract_frames.sh <recording.mov>` → `python3 build.py` → `bash go.sh`.
Voice lines: `voiceover/vo.py` (Kokoro TTS, voice `af_heart`).
