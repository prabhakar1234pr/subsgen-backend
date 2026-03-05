"""
Upload video to GCS and return a short-lived signed URL (1–2 hours).
Objects are auto-deleted by bucket lifecycle (24h).

Uses IAM signBlob API for Cloud Run (no private key needed).
"""

import logging
import uuid
from pathlib import Path

import google.auth
from google.auth.transport import requests as auth_requests
from google.cloud import storage
from google.cloud.storage import Client

logger = logging.getLogger(__name__)

SIGNED_URL_EXPIRY_HOURS = 2


def upload_and_get_signed_url(local_path: Path, bucket_name: str, object_name: str | None = None) -> str:
    """
    Upload file to GCS and return a signed URL valid for 2 hours.
    Uses IAM signBlob when no private key (Cloud Run).
    """
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(auth_requests.Request())

    client: Client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    name = object_name or f"reels/{uuid.uuid4()}.mp4"
    blob = bucket.blob(name)

    logger.info(f"[GCS] Uploading {local_path} -> gs://{bucket_name}/{name}")
    blob.upload_from_filename(str(local_path), content_type="video/mp4")

    # Cloud Run: pass service_account_email + access_token for IAM signBlob (no private key)
    service_account_email = getattr(credentials, "service_account_email", None)
    access_token = credentials.token
    if service_account_email and access_token:
        url = blob.generate_signed_url(
            version="v4",
            expiration=3600 * SIGNED_URL_EXPIRY_HOURS,
            method="GET",
            service_account_email=service_account_email,
            access_token=access_token,
        )
    else:
        url = blob.generate_signed_url(
            version="v4",
            expiration=3600 * SIGNED_URL_EXPIRY_HOURS,
            method="GET",
        )
    logger.info(f"[GCS] Signed URL generated (expires in {SIGNED_URL_EXPIRY_HOURS}h)")
    return url
