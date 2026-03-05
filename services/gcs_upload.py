"""
Upload video to GCS and return a short-lived signed URL (1–2 hours).
Objects are auto-deleted by bucket lifecycle (24h).
"""

import logging
import uuid
from pathlib import Path

from google.cloud import storage
from google.cloud.storage import Client

logger = logging.getLogger(__name__)

SIGNED_URL_EXPIRY_HOURS = 2


def upload_and_get_signed_url(local_path: Path, bucket_name: str, object_name: str | None = None) -> str:
    """
    Upload file to GCS and return a signed URL valid for 2 hours.
    """
    client: Client = storage.Client()
    bucket = client.bucket(bucket_name)
    name = object_name or f"reels/{uuid.uuid4()}.mp4"
    blob = bucket.blob(name)

    logger.info(f"[GCS] Uploading {local_path} -> gs://{bucket_name}/{name}")
    blob.upload_from_filename(str(local_path), content_type="video/mp4")

    url = blob.generate_signed_url(
        version="v4",
        expiration=3600 * SIGNED_URL_EXPIRY_HOURS,
        method="GET",
    )
    logger.info(f"[GCS] Signed URL generated (expires in {SIGNED_URL_EXPIRY_HOURS}h)")
    return url
