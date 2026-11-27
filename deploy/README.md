# Deploying the loggers

Cloud resources are created and changed by hand only. `setup.sh` configures a droplet that
already exists; it never creates, resizes or destroys anything.

## 1. Create the resources (manual)

**DigitalOcean**
- Droplet: Ubuntu 24.04 LTS, Basic, 1 GiB / 1 vCPU / 25 GiB ($6/month), Toronto region,
  your SSH key, backups off.
- Billing alert (Settings → Billing).

**Cloudflare R2**
- Create one bucket. Leave public access **off**.
- Create an R2 API token: *Object Read & Write*, applied to **this bucket only**.
  Note the Access Key ID, Secret Access Key and the S3 endpoint
  (`https://<account_id>.r2.cloudflarestorage.com`).
- Billing alert / budget notification.

**healthchecks.io**
- Check `webcams`: period 5 minutes, grace 30 minutes, email notification. Copy the ping URL.

## 2. Set up the droplet

```bash
ssh root@<droplet-ip>
git clone https://github.com/<you>/whistler-traffic.git /opt/whistler-traffic
bash /opt/whistler-traffic/deploy/setup.sh      # creates /etc/whistler-traffic/.env, then stops
nano /etc/whistler-traffic/.env                 # fill in every value
bash /opt/whistler-traffic/deploy/setup.sh      # second run starts the logger
```

**Before closing the root session**, open a second terminal and check:

```bash
ssh grahamg@<droplet-ip>
sudo -v
```

After the first run, root SSH login is disabled; use `grahamg` with `sudo` from then on.

## 3. Check it works

- `journalctl -u whistler-webcams -f`: watch one cycle (about 5 minutes).
- Cloudflare dashboard: objects appear under `raw/webcams/` and `logs/webcams/`.
- healthchecks.io: the check turns green.
- Next day: `free -h` and `df -h`.
- Alert test: `sudo systemctl stop whistler-webcams`, wait for the healthchecks email
  (about 35 minutes), then `sudo systemctl start whistler-webcams`.

## Updating

```bash
cd /opt/whistler-traffic && sudo git pull && sudo bash deploy/setup.sh
```

## Before any teardown (manual decision)

Confirm the buffer is empty (`sudo find /var/lib/whistler-traffic/buffer -type f | wc -l`
shows 0) and all data is in R2. Always keep the R2 bucket.
