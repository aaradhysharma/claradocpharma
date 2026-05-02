# Docker Hub CI/CD Path

The local demo uses images loaded into kind:

```text
clara-api:0.0.1
clara-worker:0.0.1
clara-web:0.0.1
```

The cloud path publishes the same services to **Docker Hub** through GitHub Actions.

## Required GitHub Secrets

- `DOCKERHUB_USERNAME`: your Docker Hub user or org (same as `docker login` username).
- `DOCKERHUB_TOKEN`: a [Docker Hub access token](https://docs.docker.com/security/for-developers/access-tokens/) (not your account password).

If these secrets are unset, the **`build-images`** job is skipped and **`validate`** still runs.

## Kubernetes image names

`infra/k8s/kustomization.yaml` maps the local image names to Docker Hub:

- `docker.io/<DOCKERHUB_USERNAME>/clara-api`
- `docker.io/<DOCKERHUB_USERNAME>/clara-worker`
- `docker.io/<DOCKERHUB_USERNAME>/clara-web`

Edit `newName` in that file if your Docker Hub namespace is not **`aaradhysharma`**.

Apply with Kustomize so replacements are applied:

```bash
kubectl apply -k infra/k8s
```

## Image tags

CI pushes two tags for each image:

- `0.0.1`: human-readable demo version (keep in sync with `APP_VERSION` in `.github/workflows/ci.yml` and `kustomization.yaml` `newTag` when you bump).
- Git commit SHA: immutable traceability for rollbacks.

## Private repositories on Docker Hub

If the repos are **private**, create a Kubernetes `docker-registry` secret and set `imagePullSecrets` on the Deployments (not needed for public repos).

## Interview talking point

Local kind is the fast feedback loop. Docker Hub is a simple, low-cost registry for demos. ArgoCD watches Git and applies Kubernetes desired state, while GitHub Actions builds and publishes immutable container images.
