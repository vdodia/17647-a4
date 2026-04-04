# A3 Deployment Commands

## Step 1: Deploy CloudFormation Stack

```bash
aws cloudformation create-stack \
  --stack-name bookstore-a3 \
  --template-body file://templates/CF-A3-cmu.yml \
  --parameters \
    ParameterKey=LabRoleARN,ParameterValue="<YOUR_LAB_ROLE_ARN>" \
    ParameterKey=DBUsername,ParameterValue="admin" \
    ParameterKey=DBPassword,ParameterValue="<YOUR_DB_PASSWORD>" \
  --region us-east-1

# Monitor stack creation (~25-30 min)
aws cloudformation describe-stacks --stack-name bookstore-a3 --query 'Stacks[0].StackStatus'
```

## Step 2: Configure kubectl

```bash
aws eks update-kubeconfig --name bookstore-dev-BookstoreEKSCluster --region us-east-1
kubectl get nodes   # verify nodes are ready
```

## Step 3: Grant EKS Access (if needed)

Go to AWS Console -> EKS -> bookstore-dev-BookstoreEKSCluster -> Access tab
-> Create access entry for your LabRole with AmazonEKSClusterAdminPolicy

## Step 4: Create ECR Repos

```bash
./deploy.sh create-ecr
```

## Step 5: Setup SES Sender Email

```bash
./deploy.sh setup-ses your-email@example.com
```
Then check that inbox and click the AWS verification link. No SMTP passwords needed --
the EKS nodes' LabRole provides IAM credentials to boto3 automatically.

## Step 6: Build and Push Images

```bash
./deploy.sh build
./deploy.sh push
```

## Step 7: Create K8S Namespace and Secrets

```bash
kubectl apply -f k8s/namespace.yaml
export GEMINI_API_KEY='your-key-here'   # recommended: never commit this
./deploy.sh create-secrets
```
DB credentials are prompted; Gemini is taken from `GEMINI_API_KEY` or a final prompt. Email uses SES via IAM role (no SMTP secret).

## Step 8: Deploy to K8S

```bash
./deploy.sh deploy
```

## Step 9: Get URLs

```bash
./deploy.sh urls
# Or directly:
kubectl get svc -n bookstore-ns
```

## Step 10: Create url.txt

Use the LoadBalancer hostnames from Step 9:
```
http://<web-bff-hostname>:80
http://<mobile-bff-hostname>:80
vdodia
your-email@example.com
```

## Useful Debugging Commands

```bash
kubectl get pods -n bookstore-ns
kubectl logs <pod-name> -n bookstore-ns
kubectl describe pod <pod-name> -n bookstore-ns
kubectl rollout restart deployment/<service-name> -n bookstore-ns
```

## Teardown

```bash
kubectl delete namespace bookstore-ns
aws cloudformation delete-stack --stack-name bookstore-a3
```
