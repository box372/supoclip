# ChunkVex AI — personal installation

A one-person deployment with no sign-in, no billing and no paid APIs. It runs
the same frontend, backend, worker and database as before; personal mode only
removes the multi-user surfaces and switches the AI steps to free local ones.

## What personal mode does

| Area | Behaviour |
|---|---|
| Accounts | No sign-in screen, no sign-up, no password reset. One owner id (`personal-owner`) is seeded in the database and used for every request. |
| Plans | No pricing page, no plan limits, no Stripe/RevenueCat calls. Every generation is allowed. |
| Hidden routes | `/affiliate`, `/analytics`, `/settings/social`, `/settings/creator-program`, `/admin`, and the auth pages redirect home. |
| Transcription | `TRANSCRIPTION_PROVIDER=whisper` — local Whisper on CPU, no AssemblyAI key. |
| Clip selection | `AI_ANALYSIS_ENABLED=false` — evenly spaced, line-aligned transcript windows instead of an LLM. No key, no model, no network. |
| Hooks | Off in the model-free mode (`hook_title` is empty). Captions still come from Whisper word timings and remain optional per generation. |
| Storage | Local disk volumes (`uploads`, `clips`). No S3/R2. |
| Scheduling, social publishing, MCP | Not exposed. The code stays in the repository. |

The clipping interface itself — YouTube/Twitch/Kick URL, uploads, moment
selection, 9:16 reframe, caption editing, preview, MP4 export — is unchanged.

## What runs where

```
Chrome (Windows 7)  ──HTTPS──>  Cloudflare Tunnel  ──>  Oracle Cloud Always Free VM
                                                          ├─ frontend  (Next.js, port 3107)
                                                          ├─ backend   (FastAPI, 8000)
                                                          ├─ worker    (FFmpeg + Whisper)
                                                          ├─ postgres  (tasks, clips)
                                                          └─ redis     (job queue)
```

Everything is server-side: the browser only shows pages and downloads finished
MP4s. Nothing needs to be installed on your computer.

## Cost

- **Oracle Cloud Always Free**: 4 ARM cores / 24 GB RAM / up to 200 GB block
  storage, free indefinitely (`A1.Flex` shape). Oracle asks for a card to verify
  identity; the Always Free resources are not charged.
- **Cloudflare Tunnel**: free, no open ports, no static IP.
- **Domain**: optional. A free DuckDNS subdomain works; Cloudflare Quick Tunnel
  needs no domain at all (random URL that changes on restart).
- **Transcription and clip selection**: £0, local CPU.
- Free-tier limits are enough for personal use but **not** fast: CPU Whisper and
  FFmpeg share four cores. Expect roughly real-time-to-2× for `base` Whisper and
  a 30–60 s render for a one-minute 9:16 clip.

## 1. Create the free server

1. Sign up at `cloud.oracle.com`, choose a home region near you.
2. Compute → Instances → Create instance.
3. Image: **Ubuntu 22.04** (aarch64). Shape: **VM.Standard.A1.Flex**, 4 OCPUs,
   24 GB memory (Always Free eligible).
4. Add your SSH public key, create, and note the public IP.
5. If the shape is sold out, try another availability domain or retry later —
   Always Free ARM capacity comes and goes.

## 2. Install Docker and the app

```bash
ssh ubuntu@<server-ip>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker

git clone https://github.com/box372/supoclip
cd supoclip
cp .env.personal.example .env
```

Edit `.env`:

```bash
# Required
NEXT_PUBLIC_APP_URL=https://your-public-url
BETTER_AUTH_URL=https://your-public-url
CORS_ORIGINS=https://your-public-url

# Both secrets: openssl rand -hex 32
BETTER_AUTH_SECRET=...
BACKEND_AUTH_SECRET=...
```

Then start it:

```bash
docker compose up -d --build
docker compose ps
```

First start downloads the Whisper weights into the `whisper_cache` volume the
first time a video is transcribed (about 74 MB for `base`).

## 3. Get a public HTTPS URL

### Option A — Cloudflare Quick Tunnel (no domain, fastest)

```bash
# Host networking lets the tunnel reach the frontend on 127.0.0.1:3001.
docker run -d --name chunkvex-tunnel --restart unless-stopped --network host \
  cloudflare/cloudflared:latest tunnel --no-autoupdate --url http://127.0.0.1:3001
```

Find the URL:

```bash
docker logs chunkvex-tunnel 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

Put that URL in `NEXT_PUBLIC_APP_URL`, `BETTER_AUTH_URL` and `CORS_ORIGINS`,
then rebuild the frontend so the value is compiled in:

```bash
docker compose up -d --build frontend
```

The URL changes whenever the tunnel container is recreated. For a stable
address, use Option B.

### Option B — named tunnel with a domain

```bash
# On the VM
docker run -it --rm -v ~/.cloudflared:/home/nonroot/.cloudflared \
  cloudflare/cloudflared:latest tunnel login
docker run -it --rm -v ~/.cloudflared:/home/nonroot/.cloudflared \
  cloudflare/cloudflared:latest tunnel create chunkvex
# Add a DNS record for clips.example.com pointing at the tunnel, then:
docker run -d --name chunkvex-tunnel --restart unless-stopped --network host \
  -v ~/.cloudflared:/home/nonroot/.cloudflared \
  cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <token>
```

In the tunnel's public-hostname mapping, point `clips.example.com` at
`http://localhost:3001`.

### Option C — DuckDNS + Caddy (no Cloudflare account)

```bash
sudo apt install -y caddy
# /etc/caddy/Caddyfile
your-name.duckdns.org {
    reverse_proxy 127.0.0.1:3001
}
```

Open ports 80 and 443 in the Oracle VCN security list, then
`sudo systemctl reload caddy`.

## 4. Verify it actually clips

Before trusting it, run the bundled pipeline check on the server. It uses a
real bundled video, local Whisper, the model-free selector and the real FFmpeg
renderer, then inspects the exported MP4 with ffprobe:

```bash
docker compose exec worker bash -lc \
  'TRANSCRIPTION_PROVIDER=whisper WHISPER_MODEL=base AI_ANALYSIS_ENABLED=false \
   TEMP_DIR=/tmp/check MEDIA_STORAGE=local \
   .venv/bin/python scripts/personal_pipeline_check.py'
```

A `PASS` line means transcription, selection, 9:16 reframing, captions and MP4
export worked on this machine.

The end-to-end check drives the real HTTP API, queue and worker — upload, task,
render, clip download — and inspects the downloaded file:

```bash
docker compose exec backend bash -lc \
  'PERSONAL_USER_ID=personal-owner BACKEND_AUTH_SECRET=$BACKEND_AUTH_SECRET \
   uv run python scripts/personal_e2e_check.py --api http://127.0.0.1:8000'
```

A `PASS` line means the whole server pipeline worked, not just the renderer.

Then the browser check:

1. Open the public URL. You land on the create screen (no sign-in).
2. Upload a 1–2 minute MP4, or paste a YouTube URL.
3. Wait for the worker; the task page shows progress.
4. Open a clip, check the vertical framing and captions in the editor.
5. Download the MP4 and confirm it plays with audio in a local player.

## 5. Optional local AI (still free)

AI hooks and scoring need a model. Ollama runs on the same VM with no key:

```bash
docker compose --profile ai up -d
docker compose exec ollama ollama pull qwen2.5:3b
```

In `.env`:

```env
AI_ANALYSIS_ENABLED=true
LLM=ollama:qwen2.5:3b
OLLAMA_BASE_URL=http://ollama:11434
```

Restart backend and worker:

```bash
docker compose up -d backend worker
```

Expect several minutes of CPU time per video on a free VM. If it is too slow,
set `AI_ANALYSIS_ENABLED=false` again — clips still work.

## 6. Windows 7 / Chrome

Windows 7's newest Chrome is 109. The theme is now sRGB hex (no `oklch`), but
Next.js 15 and Tailwind 4 officially target Chrome 111+, so the page can render
with missing styles in 109. Recommended fix: install **Supermium**, a free
32-bit Chromium build for Windows 7, and open the site there. Chrome 109 will
load the app, but treat it as unsupported.

## 7. Operations

```bash
docker compose logs -f worker          # render + Whisper progress
docker compose restart backend worker  # after .env changes
docker compose down                    # stop everything (data stays in volumes)
```

Backups:

```bash
docker compose exec -T postgres pg_dump -U supoclip supoclip > backup.sql
docker run --rm -v supoclip_uploads:/data -v $PWD:/backup alpine \
  tar czf /backup/uploads.tgz -C /data .
```

Update:

```bash
git pull && docker compose up -d --build
```

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `whisper` download stalls | The VM needs outbound HTTPS; re-run and check `docker compose logs worker`. |
| YouTube URL fails | YouTube sometimes requires cookies/PO tokens; upload the file instead, or set `YOUTUBE_POT_PROVIDER_URL`. |
| Render is killed | Out of memory — use `WHISPER_MODEL_SIZE=tiny`, lower `MAX_VIDEO_UPLOAD_BYTES`, or render shorter sources. |
| Task stuck in queued | `docker compose ps` — the worker must be running and Redis healthy. |
| Blank/unstyled page in Chrome 109 | Use Supermium (section 6). |
| Tunnel URL changed | Rebuild the frontend with the new `NEXT_PUBLIC_APP_URL`. |

## What this does not give you

- No multi-user accounts, quotas, billing or social publishing.
- No managed object storage or GPU acceleration.
- No SLA: a home-grade free VM can be reclaimed if idle for long periods; keep
  backups of `postgres_data`, `uploads` and `clips`.
