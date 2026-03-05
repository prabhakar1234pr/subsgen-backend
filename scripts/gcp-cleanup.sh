#!/bin/bash
# GCP Cleanup - Run this to delete all GCP resources for subsgen-backend
# WARNING: This permanently deletes VMs, firewall rules, etc.
# Run: gcloud auth login first, then: bash scripts/gcp-cleanup.sh

set -e
PROJECT=subsgen-backend-488200

echo "=== Deleting GCP resources in project $PROJECT ==="

# Delete VM
echo "Deleting VM subsgen-vm..."
gcloud compute instances delete subsgen-vm --zone=us-central1-a --project=$PROJECT --quiet 2>/dev/null || true

# Delete firewall rules we created
for rule in allow-ssh-from-iap allow-ssh-from-private-pool; do
  echo "Deleting firewall $rule..."
  gcloud compute firewall-rules delete $rule --project=$PROJECT --quiet 2>/dev/null || true
done

# Delete Cloud Build worker pool
echo "Deleting worker pool subsgen-pool..."
gcloud builds worker-pools delete subsgen-pool --region=us-central1 --project=$PROJECT --quiet 2>/dev/null || true

# Delete VPC peering (release the allocated range)
echo "Releasing VPC peering..."
gcloud services vpc-peerings delete --network=default --project=$PROJECT --quiet 2>/dev/null || true

# Delete allocated IP range
echo "Deleting allocated IP range..."
gcloud compute addresses delete cloudbuild-private-range --global --project=$PROJECT --quiet 2>/dev/null || true

echo "=== Cleanup complete ==="
echo "Note: Default firewall rules (allow-ssh, default-allow-*) remain."
echo "To delete the entire project: gcloud projects delete $PROJECT"
