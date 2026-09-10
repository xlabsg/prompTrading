#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./convert_assets.sh <input_video.webm> [output_base_path] [fps] [scale_width] [max_colors]
# Example:
#   ./convert_assets.sh recording.webm docs/assets/hero-demo 12 840 80

INPUT_FILE="${1:?Error: Missing input video path}"
OUTPUT_BASE="${2:-docs/assets/hero-demo}"
FPS="${3:-12}"
WIDTH="${4:-840}"
MAX_COLORS="${5:-80}"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: Input file '$INPUT_FILE' not found!" >&2
    exit 1
fi

OUTPUT_DIR="$(dirname "$OUTPUT_BASE")"
mkdir -p "$OUTPUT_DIR"

MP4_OUT="${OUTPUT_BASE}.mp4"
GIF_OUT="${OUTPUT_BASE}.gif"

echo "=================================================="
echo "  Web Demo Media Converter (FFmpeg Pipeline)      "
echo "=================================================="
echo " Input File:   $INPUT_FILE"
echo " Output Base:  $OUTPUT_BASE"
echo " Target FPS:   $FPS"
echo " Scale Width:  $WIDTH px"
echo " Max Colors:   $MAX_COLORS"
echo "=================================================="

# 1. Produce H.264 MP4 with faststart for instantaneous streaming
echo -e "\n[1/2] Encoding MP4 (H.264 high profile, CRF 22)..."
ffmpeg -y -i "$INPUT_FILE" \
    -c:v libx264 -pix_fmt yuv420p -profile:v high -level 4.0 \
    -movflags +faststart -r 30 -crf 22 \
    "$MP4_OUT"

# 2. Produce Two-Pass Bayer Dithered GIF (< 5MB)
echo -e "\n[2/2] Encoding Palette-Optimized GIF..."
ffmpeg -y -i "$INPUT_FILE" \
    -vf "fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=${MAX_COLORS}:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
    "$GIF_OUT"

echo -e "\n=================================================="
echo "  Conversion Completed Successfully!              "
echo "=================================================="
ls -lh "$MP4_OUT" "$GIF_OUT"
echo "=================================================="
