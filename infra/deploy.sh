#!/usr/bin/env bash
# MindSafe AWS deployment script
# Usage: ./infra/deploy.sh [REGION] [ACCOUNT_ID]
#
# Prerequisites:
#   - aws cli configured (aws configure)
#   - Docker running
#   - ECR repo created: aws ecr create-repository --repository-name mindsafe-api
#   - ECS cluster created: aws ecs create-cluster --cluster-name mindsafe
#   - Secrets in AWS Secrets Manager (see ecs-task-definition.json)

set -euo pipefail

REGION="${1:-us-east-1}"
ACCOUNT_ID="${2:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPO="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/mindsafe-api"
CLUSTER="mindsafe"
SERVICE="mindsafe-api"

echo "==> Deploying MindSafe API to ECS"
echo "    Region:  $REGION"
echo "    Account: $ACCOUNT_ID"
echo "    Image:   $ECR_REPO:latest"
echo ""

# 1. Authenticate Docker to ECR
echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# 2. Build with ML deps for production
echo "==> Building Docker image (INSTALL_ML_DEPS=1)..."
docker build \
  --build-arg INSTALL_ML_DEPS=1 \
  -t mindsafe-api \
  -f ai-agents/Dockerfile \
  ai-agents/

# 3. Tag and push
echo "==> Pushing to ECR..."
docker tag mindsafe-api:latest "$ECR_REPO:latest"
docker push "$ECR_REPO:latest"

# 4. Substitute placeholders in task definition and register it
echo "==> Registering ECS task definition..."
sed "s/ACCOUNT_ID/$ACCOUNT_ID/g; s/REGION/$REGION/g" \
  infra/ecs-task-definition.json > /tmp/mindsafe-task-def.json
aws ecs register-task-definition \
  --cli-input-json file:///tmp/mindsafe-task-def.json \
  --region "$REGION"

# 5. Update service (create if missing)
echo "==> Updating ECS service..."
if aws ecs describe-services \
    --cluster "$CLUSTER" --services "$SERVICE" \
    --region "$REGION" \
    --query 'services[0].status' --output text 2>/dev/null | grep -q ACTIVE; then
  aws ecs update-service \
    --cluster "$CLUSTER" \
    --service "$SERVICE" \
    --task-definition mindsafe-api \
    --force-new-deployment \
    --region "$REGION"
else
  echo "  Service not found — create it manually via AWS console or CLI:"
  echo "  aws ecs create-service --cluster $CLUSTER --service-name $SERVICE \\"
  echo "    --task-definition mindsafe-api --launch-type FARGATE \\"
  echo "    --desired-count 1 --network-configuration '...'"
fi

echo ""
echo "==> Done. Monitor deployment:"
echo "    aws ecs wait services-stable --cluster $CLUSTER --services $SERVICE --region $REGION"
echo "    Health: https://your-alb-url/health"
