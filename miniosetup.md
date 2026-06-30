# MinIO setup — run alongside Redis

## Start MinIO container

docker run -d \
  --name dataiq-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e "MINIO_ROOT_USER=dataiq" \
  -e "MINIO_ROOT_PASSWORD=dataiq_local_dev_password" \
  -v dataiq_minio_data:/data \
  minio/minio server /data --console-address ":9001"

## What the ports mean
- 9000 = S3-compatible API (your backend talks to this)
- 9001 = Web console UI (open http://localhost:9001 in browser to see buckets visually)

## First-time setup
1. Run the docker command above
2. Open http://localhost:9001 in your browser
3. Login: dataiq / dataiq_local_dev_password
4. The bucket "dataiq-csv-exports" will be auto-created by the backend on first extraction —
   no need to create it manually.

## Environment variables to add to backend/.env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=dataiq
MINIO_SECRET_KEY=dataiq_local_dev_password
MINIO_BUCKET=dataiq-csv-exports
MINIO_SECURE=False

## Python package needed
pip install minio --break-system-packages