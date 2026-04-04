#!/usr/bin/env bash
#
# deploy.sh – Build, push Docker images to ECR, and deploy to EKS.
#
# Usage:
#   ./deploy.sh                    # full build + push + deploy
#   ./deploy.sh build              # build only
#   ./deploy.sh push               # push only
#   ./deploy.sh deploy             # kubectl apply only
#   ./deploy.sh create-ecr         # create ECR repos
#   ./deploy.sh create-secrets     # create K8S secrets (DB + Gemini only)
#   ./deploy.sh setup-ses <email>  # verify SES sender identity + update CRM deployment
#
set -euo pipefail

REGION="us-east-1"
SERVICES=("web-bff" "mobile-bff" "customer-service" "book-service" "crm-service")

# Auto-detect AWS account ID
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
}

build_images() {
    echo ">>> Building Docker images..."
    for svc in "${SERVICES[@]}"; do
        echo "  Building ${svc}..."
        docker build -t "bookstore/${svc}:latest" "./${svc}/"
    done
}

push_images() {
    ecr_login
    echo ">>> Pushing images to ECR..."
    for svc in "${SERVICES[@]}"; do
        echo "  Pushing ${svc}..."
        docker tag "bookstore/${svc}:latest" "${ECR_BASE}/bookstore/${svc}:latest"
        docker push "${ECR_BASE}/bookstore/${svc}:latest"
    done
}

update_k8s_images() {
    echo ">>> Updating image references in K8S manifests..."
    for svc in "${SERVICES[@]}"; do
        if [ -f "./${svc}/k8s/deployment.yaml" ]; then
            sed -i "s|ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com|${ECR_BASE}|g" "./${svc}/k8s/deployment.yaml"
        fi
    done
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
    echo ">>> Creating K8S secrets (DB credentials + Gemini API key)..."
    read -rp "DB Host (RDS writer endpoint): " DB_HOST
    read -rp "DB Username: " DB_USER
    read -rsp "DB Password: " DB_PASS
    echo ""

    local gemini_key="${GEMINI_API_KEY:-}"
    if [ -z "${gemini_key}" ]; then
        read -rsp "Gemini API key (or set GEMINI_API_KEY and re-run): " gemini_key
        echo ""
    fi
    if [ -z "${gemini_key}" ]; then
        echo "ERROR: Gemini API key is required." >&2
        exit 1
    fi

    kubectl create secret generic db-credentials \
        --namespace=bookstore-ns \
        --from-literal=host="${DB_HOST}" \
        --from-literal=username="${DB_USER}" \
        --from-literal=password="${DB_PASS}" \
        --dry-run=client -o yaml | kubectl apply -f -

    kubectl create secret generic app-secrets \
        --namespace=bookstore-ns \
        --from-literal=gemini-api-key="${gemini_key}" \
        --dry-run=client -o yaml | kubectl apply -f -

    echo ">>> Secrets created/updated. (No email secrets needed -- SES uses IAM role.)"
}

deploy_k8s() {
    echo ">>> Deploying K8S resources..."
    kubectl apply -f k8s/namespace.yaml

    for svc in "${SERVICES[@]}"; do
        echo "  Deploying ${svc}..."
        kubectl apply -f "./${svc}/k8s/"
    done

    echo ""
    echo ">>> Waiting for deployments to be ready..."
    for svc in "${SERVICES[@]}"; do
        kubectl rollout status deployment/"${svc}" -n bookstore-ns --timeout=120s || true
    done

    echo ""
    echo ">>> Services:"
    kubectl get svc -n bookstore-ns
    echo ""
    echo ">>> Pods:"
    kubectl get pods -n bookstore-ns
}

configure_kubectl() {
    echo ">>> Configuring kubectl for EKS cluster: ${EKS_CLUSTER_NAME}"
    aws eks update-kubeconfig --name "${EKS_CLUSTER_NAME}" --region "${REGION}"
}

show_urls() {
    echo ""
    echo ">>> LoadBalancer URLs:"
    echo "Web BFF:"
    kubectl get svc web-bff -n bookstore-ns -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "(pending)"
    echo ""
    echo "Mobile BFF:"
    kubectl get svc mobile-bff -n bookstore-ns -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "(pending)"
    echo ""
}

case "${1:-all}" in
    build)
        build_images
        ;;
    push)
        push_images
        ;;
    deploy)
        update_k8s_images
        deploy_k8s
        show_urls
        ;;
    create-ecr)
        create_ecr_repos
        ;;
    create-secrets)
        create_secrets
        ;;
    setup-ses)
        setup_ses "${2:-}"
        ;;
    configure-kubectl)
        configure_kubectl
        ;;
    urls)
        show_urls
        ;;
    all)
        build_images
        push_images
        update_k8s_images
        deploy_k8s
        show_urls
        ;;
    *)
        echo "Usage: $0 {build|push|deploy|create-ecr|create-secrets|setup-ses|configure-kubectl|urls|all}"
        exit 1
        ;;
esac
