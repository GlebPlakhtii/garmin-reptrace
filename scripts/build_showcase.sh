#!/usr/bin/env bash
# Rebuild the optional screenshot slideshow; requires ffmpeg on PATH.
set -euo pipefail
cd "$(dirname "$0")/.."
showcase_list=$(mktemp)
trap 'rm -f "$showcase_list"' EXIT
for frame in overview exercises weekly-volume recovery next-session; do
  printf "file '%s/docs/media/%s.jpg'\nduration 4\n" "$PWD" "$frame" >> "$showcase_list"
done
printf "file '%s/docs/media/next-session.jpg'\n" "$PWD" >> "$showcase_list"
ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$showcase_list" \
  -vf 'scale=1440:-2,format=yuv420p' -r 24 -t 20 -c:v libx264 -crf 23 \
  -movflags +faststart docs/media/garmin-reptrace-tour.mp4
ffmpeg -hide_banner -loglevel error -y -i docs/media/garmin-reptrace-tour.mp4 \
  -filter_complex 'fps=1/4,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse' \
  -loop 0 docs/media/garmin-reptrace-tour.gif
