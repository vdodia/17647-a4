#!/usr/bin/env bash
# Run after: CloudFormation stack bookstore-a4 = CREATE_COMPLETE
# Requires: Docker, kubectl, AWS CLI; plus exports below.
#
#   export MONGO_URI='...'
#   export GEMINI_API_KEY='...'
#   export GMAIL_ADDRESS='...'
#   export GMAIL_APP_PASSWORD='...'
#
# Optional: export EKS_CLUSTER_NAME=...  (read from stack if unset)
# DB host/password: taken from stack output + .deploy/db_password.txt
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
REGION="${AWS_REGION:-us-east-1}"
STACK="${CF_STACK_NAME:-bookstore-a4}"
DB_PASS_FILE=".deploy/db_password.txt"

if [[ ! -f "$DB_PASS_FILE" ]]; then
  echo "Missing $DB_PASS_FILE">&2
  exit 1
fi
export DB_HOST="${DB_HOST:-$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='AuroraWriterEndpoint'].OutputValue" --output text)}"
export DB_USERNAME="${DB_USERNAME:-bookadmin}"
export DB_PASSWORD="${DB_PASSWORD:-$(cat "$DB_PASS_FILE")}"
export EKS_CLUSTER_NAME="${EKS_CLUSTER_NAME:-$(aws cloudformation describe-stacks --stack-name "$STACK" --region "$REGION" --query "Stacks[0].Outputs[?OutputKey=='EksClusterName'].OutputValue" --output text)}"

: "${MONGO_URI:?set MONGO_URI}" "${GEMINI_API_KEY:?set GEMINI_API_KEY}" \
  "${GMAIL_ADDRESS:?set GMAIL_ADDRESS}" "${GMAIL_APP_PASSWORD:?set GMAIL_APP_PASSWORD}"

export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$REGION}"

./deploy.sh configure-kubectl
./deploy.sh create-ecr
./deploy.sh create-secrets-a4
./deploy.sh all
echo ">>> If pods were already running, restart to pick up secrets:"
for d in web-bff mobile-bff customer-service book-command-service book-query-service crm-service; do
  kubectl rollout restart "deployment/${d}" -n bookstore-ns 2>/dev/null || true
done
kubectl get pods -n bookstore-ns
./deploy.sh urls
echo ">>> Set url.txt to the BFF URLs and your andrewid/email for submission."
