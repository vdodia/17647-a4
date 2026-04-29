#!/usr/bin/env bash
#
# deploy.sh – Build, push to ECR, deploy to EKS (A4: book command + query + sync).
#
# Usage:
#   ./deploy.sh
#   ./deploy.sh build | push | deploy | create-ecr | create-secrets | create-secrets-a4
#   ./deploy.sh configure-kubectl | urls | all
#
set -euo pipefail

REGION="us-east-1"
# Microservice deployments (not CronJob)
SERVICES=(
  "web-bff"
  "mobile-bff"
  "customer-service"
  "book-command-service"
  "book-query-service"
  "crm-service"
)
SYNC_IMAGE="book-sync"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "ACCOUNT_ID")
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
EKS_CLUSTER_NAME="${EKS_CLUSTER_NAME:-bookstore-dev-BookstoreEKSCluster}"

ecr_login() {
  echo ">>> Logging into ECR..."
  aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${ECR_BASE}"
}

create_ecr_repos() {
  echo ">>> Creating ECR repositories..."
  for svc in "${SERVICES[@]}"; do
    aws ecr create-repository \
      --repository-name "bookstore/${svc}" \
      --region "${REGION}" 2>/dev/null || echo "  (bookstore/${svc} already exists)"
  done
  aws ecr create-repository \
    --repository-name "bookstore/${SYNC_IMAGE}" \
    --region "${REGION}" 2>/dev/null || echo "  (bookstore/${SYNC_IMAGE} already exists)"
}

build_images() {
  echo ">>> Building Docker images..."
  for svc in "${SERVICES[@]}"; do
    echo "  Building ${svc}..."
    docker build -t "bookstore/${svc}:latest" "./${svc}/"
  done
  echo "  Building ${SYNC_IMAGE}..."
  docker build -t "bookstore/${SYNC_IMAGE}:latest" "./book-sync/"
}

push_images() {
  ecr_login
  echo ">>> Pushing images to ECR..."
  for svc in "${SERVICES[@]}"; do
    echo "  Pushing ${svc}..."
    docker tag "bookstore/${svc}:latest" "${ECR_BASE}/bookstore/${svc}:latest"
    docker push "${ECR_BASE}/bookstore/${svc}:latest"
  done
  echo "  Pushing ${SYNC_IMAGE}..."
  docker tag "bookstore/${SYNC_IMAGE}:latest" "${ECR_BASE}/bookstore/${SYNC_IMAGE}:latest"
  docker push "${ECR_BASE}/bookstore/${SYNC_IMAGE}:latest"
}

update_k8s_images() {
  echo ">>> Updating image references in K8S manifests..."
  for svc in "${SERVICES[@]}"; do
    if [ -f "./${svc}/k8s/deployment.yaml" ]; then
      # Placeholder or any 12-digit AWS account ID in ECR URLs
      sed -i "s|ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com|${ECR_BASE}|g" "./${svc}/k8s/deployment.yaml"
      sed -i -E "s|[0-9]{12}\\.dkr\\.ecr\\.us-east-1\\.amazonaws\\.com|${ECR_BASE}|g" "./${svc}/k8s/deployment.yaml"
    fi
  done
  if [ -f "./book-sync/k8s/cronjob.yaml" ]; then
    sed -i "s|ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com|${ECR_BASE}|g" "./book-sync/k8s/cronjob.yaml"
    sed -i -E "s|[0-9]{12}\\.dkr\\.ecr\\.us-east-1\\.amazonaws\\.com|${ECR_BASE}|g" "./book-sync/k8s/cronjob.yaml"
  fi
}

setup_ses() {
  local sender_email="${1:?Usage: $0 setup-ses <sender-email>}"
  echo ">>> Verifying SES email identity: ${sender_email}"
  aws ses verify-email-identity --email-address "${sender_email}" --region "${REGION}"
  echo "    Check ${sender_email} inbox and click the verification link from AWS."
  echo ""
  echo ">>> Updating CRM deployment with sender email..."
  sed -i "s|SES_SENDER_EMAIL|${sender_email}|g" ./crm-service/k8s/deployment.yaml
  echo "    Done. CRM deployment updated."
}

create_secrets() {
  echo ">>> Creating K8S secrets (DB + Gemini + Gmail SMTP)..."
  read -rp "DB Host (RDS writer endpoint): " DB_HOST
  read -rp "DB Username: " DB_USER
  read -rsp "DB Password: " DB_PASS
  echo ""
  local gemini_key="${GEMINI_API_KEY:-}"
  if [ -z "${gemini_key}" ]; then
    read -rsp "Gemini API key (or set GEMINI_API_KEY env var): " gemini_key
    echo ""
  fi
  if [ -z "${gemini_key}" ]; then
    echo "ERROR: Gemini API key is required." >&2
    exit 1
  fi
  read -rp "Gmail address (SMTP sender): " SMTP_USER
  read -rsp "Gmail app password: " SMTP_PASS
  echo ""
  _apply_db_app_email_secrets "$DB_HOST" "$DB_USER" "$DB_PASS" "$gemini_key" "$SMTP_USER" "$SMTP_PASS"
  echo ">>> All secrets created/updated."
}

_apply_db_app_email_secrets() {
  local host="$1" user="$2" pass="$3" gemini="$4" smtp_user="$5" smtp_pass="$6"
  kubectl create secret generic db-credentials \
    --namespace=bookstore-ns \
    --from-literal=host="${host}" \
    --from-literal=username="${user}" \
    --from-literal=password="${pass}" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl create secret generic app-secrets \
    --namespace=bookstore-ns \
    --from-literal=gemini-api-key="${gemini}" \
    --dry-run=client -o yaml | kubectl apply -f -
  kubectl create secret generic email-credentials \
    --namespace=bookstore-ns \
    --from-literal=smtp-user="${smtp_user}" \
    --from-literal=smtp-password="${smtp_pass}" \
    --dry-run=client -o yaml | kubectl apply -f -
}

create_secrets_a4() {
  echo ">>> Non-interactive A4 secrets (set env vars first)..."
  kubectl apply -f k8s/namespace.yaml
  # Required: MONGO_URI, and either DB_HOST/DB_USERNAME/DB_PASSWORD or use RDS writer from stack.
  : "${MONGO_URI:?Set MONGO_URI to your MongoDB connection string}"
  : "${DB_HOST:?Set DB_HOST to Aurora writer hostname}"
  : "${DB_USERNAME:?Set DB_USERNAME}"
  : "${DB_PASSWORD:?Set DB_PASSWORD}"
  : "${GEMINI_API_KEY:?Set GEMINI_API_KEY}"
  : "${GMAIL_ADDRESS:?Set GMAIL_ADDRESS}"
  : "${GMAIL_APP_PASSWORD:?Set GMAIL_APP_PASSWORD}"

  _apply_db_app_email_secrets \
    "$DB_HOST" \
    "$DB_USERNAME" \
    "$DB_PASSWORD" \
    "$GEMINI_API_KEY" \
    "$GMAIL_ADDRESS" \
    "$GMAIL_APP_PASSWORD"

  kubectl create secret generic mongo-credentials \
    --namespace=bookstore-ns \
    --from-literal=uri="${MONGO_URI}" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo ">>> mongo-credentials applied."
  echo ">>> A4 secrets done."
}

deploy_k8s() {
  echo ">>> Deploying K8S resources..."
  kubectl apply -f k8s/namespace.yaml

  for svc in "${SERVICES[@]}"; do
    echo "  Deploying ${svc}..."
    kubectl apply -f "./${svc}/k8s/"
  done

  echo "  Deploying book-sync CronJob..."
  kubectl apply -f "./book-sync/k8s/cronjob.yaml"

  echo ""
  echo ">>> Waiting for deployments to be ready..."
  for svc in "${SERVICES[@]}"; do
    kubectl rollout status "deployment/${svc}" -n bookstore-ns --timeout=120s || true
  done

  echo ""
  echo ">>> Services:"
  kubectl get svc -n bookstore-ns
  echo ""
  echo ">>> Pods:"
  kubectl get pods -n bookstore-ns
  echo ""
  echo ">>> CronJob:"
  kubectl get cronjob -n bookstore-ns 2>/dev/null || true
}

configure_kubectl() {
  echo ">>> Configuring kubectl for EKS cluster: ${EKS_CLUSTER_NAME}"
  aws eks update-kubeconfig --name "${EKS_CLUSTER_NAME}" --region "${REGION}"
}

show_urls() {
  echo ""
  echo ">>> LoadBalancer URLs:"
  echo "Web BFF:"
  kubectl get svc web-bff -n bookstore-ns -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending"
  echo ""
  echo "Mobile BFF:"
  kubectl get svc mobile-bff -n bookstore-ns -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending"
  echo ""
}

case "${1:-all}" in
  build) build_images ;;
  push) push_images ;;
  deploy)
    update_k8s_images
    deploy_k8s
    show_urls
    ;;
  create-ecr) create_ecr_repos ;;
  create-secrets) create_secrets ;;
  create-secrets-a4) create_secrets_a4 ;;
  setup-ses) setup_ses "${2:-}" ;;
  configure-kubectl) configure_kubectl ;;
  urls) show_urls ;;
  all)
    build_images
    push_images
    update_k8s_images
    deploy_k8s
    show_urls
    ;;
  *)
    echo "Usage: $0 {build|push|deploy|create-ecr|create-secrets|create-secrets-a4|setup-ses|configure-kubectl|urls|all}"
    exit 1
    ;;
esac
