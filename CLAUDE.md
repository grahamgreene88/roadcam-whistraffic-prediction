# Sea-to-Sky Traffic Prediction

ML project to tell skiers when traffic builds on Highway 99 (Vancouver → Whistler) and where, so they can choose their own departure time. Non-commercial UBC student project for now; a public app is a possible later goal.

## Working conventions

- Show proposed code changes (diff or snippet) before applying them to a file.
- Store all timestamps in UTC. Convert to America/Vancouver only for display and feature engineering.
- Raw data is immutable: save sources exactly as received; parse into separate derived files.
- Every source has a licence or terms constraint (see below). Don't add a data source without checking its terms first.
- Never create, resize, power off or destroy cloud resources (droplets, buckets, tokens) yourself, and never write scripts or scheduled jobs that do so automatically. Graham makes those changes manually. Write instructions or scripts for him to review and run.

## Problem definition (decided)

- **Question answered:** when does northbound traffic start, and where along the corridor?
- **Target:** probability that each camera site is congested in each 15-minute slot (northbound, mornings). Onset time per site is derived from that curve. This handles days with no traffic and days where traffic clears and rebuilds.
- **Prediction horizon:** day-ahead. The prediction is made the evening before (about 8 p.m.).
- **Feature rule:** every feature must be known by the prediction time. Same-day snow reports, same-day observations and live incidents are not valid features. Unplanned incidents can be used to explain outliers, not as inputs.
- **Possible extension:** afternoon southbound return trip (same cameras).

## Labels: webcam-based congestion (open design work)

- Congestion will be measured from DriveBC webcam images, which update about every 15 minutes.
- Planned approach: a pretrained vehicle detector (e.g. YOLO) counts vehicles inside a hand-drawn region of interest per camera view covering the northbound lane(s). Density (vehicle spacing) is the proxy for congestion.
- Hand-label a few hundred images (free-flowing / heavy / queued) to validate the detector, especially at night and in snow.
- **Open questions:** exact definition of "congested"; detector performance on low-resolution rural images in darkness (December sunrise is around 8:00, ski traffic often starts earlier) and in snow; which views are usable; camera gap between Horseshoe Bay and Lions Bay (about 10 km).

## Data sources

### Logging now (no public archive: missed days are lost)

| Source | Licence / terms | Notes |
|---|---|---|
| DriveBC webcams, 49 views at 22 sites (`sea_to_sky_cameras.csv`) | Open Government Licence – BC; the DataBC "BC HighwayCams" record says it covers the images | Images deleted after 24 h. Image URL in `links_imageURL` (`https://www.drivebc.ca/images/<id>.jpg`). Attribution: "Contains information licensed under the Open Government Licence – British Columbia." Contact: cameraprogram@gov.bc.ca |
| Environment Canada citypage forecasts: Whistler `s0000078`, Squamish `s0000323`, Vancouver `s0000141` | ECCC Data Server End-use Licence (commercial use allowed, attribution "Data Source: Environment and Climate Change Canada") | Datamart keeps files only a few days. Usage policy: use the AMQP notification service (`sr3`), not polling of directory listings. Directory layout changed in 2025; check current docs. |
| Whistler Blackcomb snow report | Vail Resorts website terms: personal, non-commercial use only, no redistribution. robots.txt allows the page (`Allow: /`). | Once a day only. Private use; ask Whistler Blackcomb for permission before publishing figures or using them in an app. |

### Available later (already archived)

- **Open-Meteo Previous Runs API:** day-ahead model forecasts (`*_previous_day1`), model GEM HRDPS West. Docs suggest only the last ~3 months are kept. Verify the earliest available date; if it is a rolling window, add a once-a-day fetch to the logger (well before late February). Free for non-commercial use; check licence before any app.
- **Historical DriveBC Events (2006–2025):** one CSV per year on the BC Data Catalogue, OGL-BC, updated annually. Use for planned closures and for explaining outliers.
- **Historical weather observations:** Environment Canada stations near Whistler, or Open-Meteo Historical Weather API (ERA5 reanalysis; note it disagreed strongly with GEM on a mountain storm, so pick one source per feature and keep it).
- **Calendar features:** BC and Washington holidays, long weekends, school breaks (BC spring break, WA mid-winter break), US Thanksgiving, Lunar New Year, Whistler events, Epic Pass blackout dates.

### Ruled out (don't suggest these)

- Mapbox, Google, Apple routing APIs: terms prohibit storing results, automated queries and/or ML training.
- TomTom and HERE trials: evaluation-only licences. A negotiated academic licence is the only route.
- BC MoT Traffic Data Program: only daily totals at one site (Cheekye); confirmed no finer data.
- OpenSnow, snow-forecast.com: commercial; not pursued.

## Logger requirements

Run in the cloud, not on a laptop. Expected volume: about 4,700 unique images a day, roughly 35 GB a season.

1. **Webcams:** read `config/sea_to_sky_cameras.csv`; poll every 5 minutes (cameras update unsynchronised, every 5–15 minutes; see note below); skip an image whose hash matches that camera's previous image; save raw JPEG as `{camera_id}/{UTC timestamp}.jpg`; record response headers in a metadata log; log failed or stale fetches and continue.
   - **Image time:** DriveBC sends no `Last-Modified`. Its nginx `ETag` is `"<mtime hex>-<size hex>"`, the file write time, which the logger decodes as `image_mtime`. The capture time printed on the image is about 2 minutes earlier.
   - **Update interval (observed 26 Nov 2026):** Vancouver cameras 17, 18, 19 published a new image every 5 minutes; rural camera 689's image was about 14 minutes old. Measure per-camera intervals from the metadata log after the first day. If most cameras update every 5 minutes, volume is about 14,000 images a day (roughly 105 GB a season), not 4,700, and a 5-minute poll will miss some images.
2. **ECCC forecasts:** subscribe via AMQP to new citypage files for the three site codes (English XML); save every issued file unchanged.
3. **Snow report:** once a day, early morning; save raw HTML; parse overnight, 24 h and 48 h snowfall, base depth, lifts and terrain open into CSV. If the page loads its data from a separate endpoint, report the path before using it, and check it against robots.txt.
4. **All sources:** User-Agent identifying the project with a contact email; a daily heartbeat that alerts if any source has gone quiet for several hours. Test the alert by stopping a logger deliberately.

## Deployment (decided Nov 2026)

Chosen for low bill risk and fast setup. A move to AWS may happen after the ski season, so everything must stay portable (see below). Expected cost: about $6–7/month while running (droplet $6, R2 under $1).

### Compute: one DigitalOcean droplet

- Basic droplet, 1 GiB RAM / 1 vCPU / 25 GiB SSD ($6/month), Ubuntu LTS. Chosen over the $4 / 512 MiB plan for memory headroom: an out-of-memory kill means missed images that can't be recollected. A Canadian region (Toronto) is preferred but not required.
- Add a 1 GB swap file in the setup script as a safety margin (e.g. during `pip install`).
- Three logger processes, each a systemd unit with `Restart=always`: webcams, ECCC (persistent AMQP subscription), snow report (systemd timer, once a day).
- No serverless: the ECCC AMQP subscription needs a long-lived connection.
- **No Docker for now (decided Nov 2026):** plain systemd units plus a Python virtual environment, to get logging running as fast as possible. Containerizing (Docker Compose, one service per logger) is deferred until after the season, e.g. before an AWS move. Don't introduce Docker without asking.
- Write each file to a local buffer directory first, then upload to storage and delete locally only after a confirmed upload. Retry failed uploads, so a storage or network outage doesn't lose images.
- No droplet backups: the droplet holds no irreplaceable state (data is in R2, setup is a script).
- **Off-season (manual, Graham's decision):** the droplet runs until Graham decides otherwise. Nothing destroys or stops it automatically. Option to consider after the season: destroy it by hand to stop billing (a powered-off droplet is still billed) and rebuild it from the setup script before the next season. Before any teardown, confirm the buffer directory is empty and all data is in R2. Always keep the R2 bucket.

### Storage: Cloudflare R2

- One **private** bucket. Never make it public.
- Access only through `boto3` using standard S3 API calls (`put_object`, `get_object`, etc.).
- Key prefixes by source: `raw/webcams/{camera_id}/{UTC timestamp}.jpg`, `raw/eccc/...`, `raw/snow/...`; metadata logs under `logs/`. Derived and parsed files go under a separate prefix, never mixed into `raw/`.
- **Don't list the bucket in the logging loop.** List operations are billed as Class A operations. Keep each camera's last image hash in local state on the droplet for deduplication.
- Raw data can't be recollected: turn on a periodic copy to a second location (e.g. `rclone` to local or external storage).

### Monitoring

- Heartbeat through an external dead-man's-switch service (e.g. healthchecks.io), not a monitor on the same droplet, so a dead droplet still triggers an alert. Each logger pings on success; alert if pings stop.
- Check memory (`free -h`) and disk after the first day of running.

### Security

- SSH key login only; disable password and root login.
- Firewall: allow inbound SSH only. Loggers make outbound requests only.
- R2 API token scoped to this one bucket, read/write only.
- Secrets live in a `.env` file on the server. `.env` is in `.gitignore` from the first commit; never commit credentials.
- Set a billing alert on both DigitalOcean and Cloudflare.

### Portability rules (keep a later AWS move to an afternoon)

- Every provider-specific value comes from environment variables: storage endpoint URL, bucket name, credentials, heartbeat URLs. Never hard-code them.
- No R2-only features (Workers, bindings). Plain S3 API only, so switching to S3 is an endpoint and credential change.
- Server setup is a script in the repo (packages, swap, Python environment, systemd units, firewall), so a new machine can be built from scratch. No manual server configuration.
- Object key layout is provider-independent (above).
- **Keep it container-ready:** all runtime state (upload buffer, per-camera dedup hashes, `sr3` state) lives under one data directory set by an environment variable (e.g. `DATA_DIR`), and dependencies are pinned in `requirements.txt`. This keeps a later move to Docker small.
- **Migrating:** not during peak season. Run old and new loggers in parallel for at least a day, confirm both are writing, then shut down the old one. Copy existing data with `rclone sync` (R2 has no egress fees). Keeping storage on R2 with compute on AWS is also an acceptable end state.
