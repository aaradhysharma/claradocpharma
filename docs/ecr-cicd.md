# ECR CI/CD Path

The local demo uses images loaded into kind:

```text
clara-api:0.0.1
clara-worker:0.0.1
clara-web:0.0.1
```

The cloud path publishes the same services to AWS ECR through GitHub Actions.

## Required GitHub Secrets

- `AWS_ROLE_TO_ASSUME`: IAM role ARN trusted by GitHub OIDC.
- `AWS_REGION`: AWS region, for example `us-east-1`.

## Terraform Resources

The Terraform stack in `infra/terraform` creates:

- ECR repositories for API, worker, and web.
- S3 artifact bucket.
- EC2 instance for single-node k3s.
- Security group for SSH, Kubernetes API, and demo web NodePort.

## Image Tags

CI pushes two tags for each image:

- `0.0.1`: human-readable demo version.
- Git commit SHA: immutable traceability for rollbacks.

## Interview Talking Point

Local kind is the fast feedback loop. ECR is the enterprise delivery path. ArgoCD watches Git and applies Kubernetes desired state, while GitHub Actions builds and publishes immutable container images.
