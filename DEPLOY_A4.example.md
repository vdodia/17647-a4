# A4 deployment (no secrets in this file)

## 1) Infrastructure

Use the same pattern as A3, but the template with stack outputs is:

- `templates/CF-A4-cmu.yml`

Example (replace `YOUR_LAB_ROLE_ARN` and a strong `DBPassword` that matches the allowed pattern):

```bash
export AWS_REGION=us-east-1
export LAB_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/LabRole
export DB_USER=bookadmin
export DB_PASS='<generate-alphanumeric-8-41-chars>'

aws cloudformation create-stack \
  --stack-name bookstore-a4 \
  --template-body file://templates/CF-A4-cmu.yml \
  --parameters \
    ParameterKey=LabRoleARN,ParameterValue="${LAB_ROLE_ARN}" \
    ParameterKey=DBUsername,ParameterValue="${DB_USER}" \
    ParameterKey=DBPassword,ParameterValue="${DB_PASS}" \
  --region "${AWS_REGION}"
```

Read outputs after `CREATE_COMPLETE`:

```bash
aws cloudformation describe-stacks --stack-name bookstore-a4 --region us-east-1 \
  --query "Stacks[0].Outputs" --output table
```

`EksClusterName` and `AuroraWriterEndpoint` are needed below.

## 2) EKS access

As in the course Learner Lab notes, you may need an EKS access entry for `LabRole` in the console if `kubectl` is denied. Then:

```bash
export EKS_CLUSTER_NAME=<EksClusterName from outputs>
./deploy.sh configure-kubectl
```

## 3) Secrets, then build and push

Set these in your **shell only** (never commit). If you use `scripts/complete_deploy_a4.sh`, you can omit `DB_HOST` and `DB_PASSWORD` when the `bookstore-a4` stack exists and `.deploy/db_password.txt` is present (see script).

```bash
export DB_HOST=<AuroraWriterEndpoint from CF outputs>   # optional if using complete_deploy_a4.sh
export DB_USERNAME=<same as DBUsername in CF>          # default bookadmin
export DB_PASSWORD=<same as DBPassword in CF>         # or use .deploy/db_password.txt
export GEMINI_API_KEY=<your key>
export GMAIL_ADDRESS=<your sender>
export GMAIL_APP_PASSWORD=<app password>
export MONGO_URI='mongodb+srv://...'   # from instructor; include auth and /BooksDB as needed
```

**Order:** create Kubernetes secrets *before* applying deployments that mount them.

```bash
./deploy.sh configure-kubectl
./deploy.sh create-ecr
./deploy.sh create-secrets-a4
./deploy.sh all
```

`all` = build (requires **Docker** on the machine), push to ECR, `sed` on manifests, `kubectl apply`, show LoadBalancer hostnames.

### One command (after stack and ECR)

```bash
export MONGO_URI='...'
export GEMINI_API_KEY='...'
export GMAIL_ADDRESS='...'
export GMAIL_APP_PASSWORD='...'
bash scripts/complete_deploy_a4.sh
```

## 5) Submission URL file

Set `url.txt` to the two BFF `http://<host>:80` lines plus your Andrew ID and email (same as A3).

## 6) Notes

- Book sync runs every **60 seconds** (`CronJob` schedule `* * * * *`).
- Mongo collection per assignment: `books_<andrewid>`; this repo’s manifests default to `books_vdodia` for andrewid `vdodia` — change `MONGO_COLLECTION` in `book-query-service` and `book-sync` if your id differs, or set via a patch/overlay.
- `DEPLOY_COMMANDS.md` is listed in `.gitignore`; keep local copies with real credentials out of version control.
