#!/usr/bin/env bash
# Renders out.mp4 (1080x1920, 30fps, H.264/AAC) from ./img, ./voice and optional ./music.
# Usage: HOOK_TEXT="..." ./render.sh   → prints "duration=<sec>" and "render_seconds=<sec>"
set -euo pipefail
START=$(date +%s)
VOICE_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 voice)
TOTAL=$(python3 -c "print(round(float('$VOICE_DUR') + 1.0, 2))")
FRAMES=$(python3 -c "import math; print(math.ceil($TOTAL * 30))")
# wrap the hook to <=22 chars/line and size the font so the longest line fits 1000px
FONTSIZE=$(HOOK_TEXT="${HOOK_TEXT:-}" python3 -c "
import os, textwrap
lines = textwrap.wrap(os.environ['HOOK_TEXT'], 22) or ['']
open('hook.txt', 'w').write(chr(10).join(lines))
print(max(36, min(76, int(1650 / max(len(l) for l in lines or [' '])))) if any(lines) else 76)
")
FONT=${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf}

# Ken Burns push-in on the character + hook text for the first 3 seconds
VF="[0:v]scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,setsar=1,"
VF+="zoompan=z='min(zoom+0.0006,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=${FRAMES}:s=1080x1920:fps=30,"
VF+="drawtext=fontfile=${FONT}:textfile=hook.txt:expansion=none:fontsize=${FONTSIZE}:line_spacing=12:fontcolor=white:borderw=6:bordercolor=black:"
VF+="x=(w-text_w)/2:y=h*0.12:enable='lt(t,3)'[v]"

ENC=(-c:v libx264 -preset veryfast -crf 21 -pix_fmt yuv420p -r 30 -c:a aac -b:a 160k -ar 44100 -movflags +faststart)

if [ -f music ]; then
  # music loops to length and is side-chain ducked under the voice
  AF="[1:a]aresample=44100,apad=pad_dur=1,asplit=2[vo][sc];"
  AF+="[2:a]aresample=44100,volume=0.35,afade=t=in:d=1[m0];"
  AF+="[m0][sc]sidechaincompress=threshold=0.03:ratio=10:attack=15:release=350[m];"
  AF+="[vo][m]amix=inputs=2:duration=first:normalize=0[a]"
  ffmpeg -y -loglevel error -i img -i voice -stream_loop -1 -i music \
    -filter_complex "${VF};${AF}" -map "[v]" -map "[a]" -t "$TOTAL" "${ENC[@]}" out.mp4
else
  ffmpeg -y -loglevel error -i img -i voice \
    -filter_complex "${VF};[1:a]aresample=44100,apad=pad_dur=1[a]" -map "[v]" -map "[a]" -t "$TOTAL" "${ENC[@]}" out.mp4
fi
echo "duration=$TOTAL"
echo "render_seconds=$(( $(date +%s) - START ))"
