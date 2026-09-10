# FFmpeg Video & GIF Optimization Recipes

This guide documents verified FFmpeg recipes for compressing UI screen recordings into crisp, GitHub-optimized assets (<5MB).

## 1. High-Performance H.264 MP4
For embedded video players, web docs, and Discord/Slack sharing:
```bash
ffmpeg -y -i input.webm \
  -c:v libx264 -pix_fmt yuv420p -profile:v high -level 4.0 \
  -movflags +faststart -r 30 -crf 22 \
  output.mp4
```
- `-movflags +faststart`: Relocates the `moov` atom (metadata) to the beginning of the file so video begins playback before the entire file finishes downloading.
- `-crf 22`: Visually lossless for UI typography and sharp code text.
- `-pix_fmt yuv420p`: Essential for compatibility across iOS, Safari, and all modern web browsers.

## 2. Two-Pass Palette-Optimized GIF (< 5MB)
Standard single-pass GIF encoders produce massive 30-50MB files with noisy dithering. A two-pass filtergraph analyzes the actual color distribution of the video:
```bash
ffmpeg -y -i input.webm \
  -vf "fps=12,scale=840:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=80:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \
  output.gif
```

### Parameter Breakdown:
| Parameter | Value | Rationale |
| :--- | :--- | :--- |
| `fps` | `12` - `15` | Fluid motion for cursor movement while cutting frame count by 50% vs 30fps. |
| `scale` | `840:-1` (or `880:-1`) | Fits standard GitHub README width (typically 800-900px wide) without downsampling artifacts. |
| `flags` | `lanczos` | Sharpest interpolation filter for UI fonts and thin indicator lines. |
| `stats_mode` | `diff` | Focuses palette generation on pixels that change between frames, reducing noise in static cards. |
| `max_colors` | `80` - `96` | 80 colors is ideal for clean, modern flat UI/dark mode and dramatically cuts GIF table sizes. |
| `dither` | `bayer` | Patterned dithering prevents gradient banding without the snow/flicker of Floyd-Steinberg dithering. |
| `bayer_scale` | `3` (scale 0-5) | Suppresses high-frequency dithering patterns for clean card backgrounds. |

## 3. High-DPI Screenshot Extraction
To grab specific timestamp frames as PNGs for documentation:
```bash
ffmpeg -y -ss 14.5 -i input.webm -vframes 1 snapshot.png
```
