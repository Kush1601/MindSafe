# MindSafe Infrastructure

Deployment files for AWS ECS Fargate and EC2.

---

## Options

| Option | Cost | Best for |
|---|---|---|
| **EC2 t2.micro** | Free (yr 1), ~$8.50/mo after | Portfolio / low traffic |
| **ECS Fargate** | ~$15–30/mo (512 CPU / 1024 MB) | Production / auto-scaling |

---

## EC2 t2.micro (recommended for portfolio)

### 1. Launch instance

AWS Console → EC2 → Launch Instance:
- AMI: Amazon Linux 2023
- Type: **t2.micro** (free tier eligible)
- Key pair: create + download `.pem`
- Security group inbound rules: SSH (22), TCP 5001, TCP 5000

### 2. SSH in

```bash
chmod 400 ~/.ssh/mindsafe-key.pem
ssh -i ~/.ssh/mindsafe-key.pem ec2-user@YOUR_EC2_IP
```

### 3. Install Docker

```bash
sudo yum update -y && sudo yum install docker git -y
sudo service docker start && sudo usermod -a -G docker ec2-user
sudo systemctl enable docker
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose
# log out and back in
```

### 4. Deploy

```bash
git clone https://github.com/YOUR_USERNAME/MindSafe.git && cd MindSafe

# Create .env
cat > ai-agents/.env << 'EOF'
ANTHROPIC_API_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_KEY=...
EOF

# Build + start (first build takes ~15 min)
docker-compose -f docker-compose.prod.yml up -d

# Verify
curl http://localhost:5001/health
```

Public URLs after deploy:
- API: `http://YOUR_EC2_IP:5001`
- Frontend: `http://YOUR_EC2_IP:5000`

### 5. Point extension at EC2

Chrome DevTools console:
```javascript
chrome.storage.local.set({ apiBaseUrl: "http://YOUR_EC2_IP:5001" })
```

---

## ECS Fargate (auto-deploy via GitHub Actions)

### Prerequisites

```bash
# Create ECR repos
aws ecr create-repository --repository-name mindsafe-api --region us-east-1
aws ecr create-repository --repository-name mindsafe-frontend --region us-east-1

# Create ECS cluster
aws ecs create-cluster --cluster-name mindsafe --region us-east-1

# Create log groups
aws logs create-log-group --log-group-name /ecs/mindsafe-api --region us-east-1
aws logs create-log-group --log-group-name /ecs/mindsafe-frontend --region us-east-1

# Store secrets
aws secretsmanager create-secret --name mindsafe/anthropic-api-key \
  --secret-string "sk-ant-..." --region us-east-1
aws secretsmanager create-secret --name mindsafe/supabase-url \
  --secret-string "https://xxxx.supabase.co" --region us-east-1
aws secretsmanager create-secret --name mindsafe/supabase-key \
  --secret-string "eyJ..." --region us-east-1
```

### IAM roles

- `ecsTaskExecutionRole` — needs `AmazonECSTaskExecutionRolePolicy` + `SecretsManagerReadWrite`
- `ecsTaskRole` — task-level AWS access (can be minimal)

### Manual first deploy

```bash
# From repo root
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
./infra/deploy.sh us-east-1 $ACCOUNT_ID
```

### GitHub Actions (auto-deploy on push to main)

Add these secrets in repo → Settings → Secrets → Actions:

| Secret | Value |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::ACCOUNT_ID:role/GitHubActionsDeployRole` |
| `AWS_REGION` | `us-east-1` |

The deploy workflow (`.github/workflows/deploy.yml`) uses OIDC — no long-lived AWS keys stored in GitHub.

---

## Files

| File | Purpose |
|---|---|
| `ecs-task-definition.json` | API task def (512 CPU / 1024 MB Fargate) |
| `ecs-task-definition-frontend.json` | Frontend task def (256 CPU / 512 MB Fargate) |
| `deploy.sh` | Manual deploy script — ECR push + ECS service update |
| `supabase_setup.sql` | Supabase table + RLS policy setup |

---

## Cost estimate

| Scenario | Monthly cost |
|---|---|
| EC2 t2.micro (free tier yr 1) | ~$0 |
| EC2 t2.micro (after yr 1) | ~$8.50 |
| ECS Fargate (512/1024 + no ALB, public IP) | ~$12–15 |
| ECS Fargate + ALB | ~$28–35 |
