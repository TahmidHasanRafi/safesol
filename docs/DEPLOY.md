# Deploying SafeSol on a VPS (Ubuntu 22.04 / 24.04)

SafeSol is one FastAPI process that serves both the API (`/api/*`) and the web app (`/`).
It reads only local files, so the server never calls NASA at runtime (`OFFLINE=1`).

## 1. Copy the code

```bash
sudo mkdir -p /opt/safesol && sudo chown $USER /opt/safesol
git clone https://github.com/<you>/<repo>.git /opt/safesol
cd /opt/safesol
```

## 2. Python environment

```bash
sudo apt update && sudo apt install -y python3-venv nginx
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest            # all tests should pass
```

rasterio and pyproj install as wheels with GDAL/PROJ included; no system GDAL is needed.

## 3. Terrain data

The repository already contains `demo_fixtures/` (committed demo data), so the app starts as is.
To prepare fresh data on the server instead, upload the DEM and run:

```bash
.venv/bin/python -m src.acquire.dem --dem cache/raw/jezero_dem.tif --name "Jezero Crater"
.venv/bin/python -m src.acquire.donki --start 2017-09-01 --end 2017-09-30
```

## 4. Service

```bash
sudo chown -R www-data:www-data /opt/safesol
sudo cp deploy/safesol.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now safesol
curl http://127.0.0.1:8020/api/health
```

Port 8020 is used to avoid clashing with other apps. Change it in both `deploy/` files if needed.

## 5. nginx and HTTPS

```bash
sudo cp deploy/nginx-safesol.conf /etc/nginx/sites-available/safesol
sudo nano /etc/nginx/sites-available/safesol      # set server_name
sudo ln -s /etc/nginx/sites-available/safesol /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d safesol.example.com
```

## Updating

```bash
cd /opt/safesol && sudo -u www-data git pull
sudo -u www-data .venv/bin/pip install -r requirements.txt
sudo systemctl restart safesol
```

## Logs

```bash
journalctl -u safesol -f
```
