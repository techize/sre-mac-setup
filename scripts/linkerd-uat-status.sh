#!/usr/bin/env bash
set -euo pipefail

NS_ARGO="argo"
NS_LINKERD="linkerd-system"
APP_CRDS="linkerd-crds"
APP_CP="linkerd-control-plane"

say() { printf "\n=== %s ===\n" "$*"; }

say "Kube context and cluster"
kubectl config current-context || true
kubectl get nodes -o wide || true

say "Namespaces of interest"
kubectl get ns ${NS_ARGO} ${NS_LINKERD} 2>/dev/null || true

say "Argo CD Applications (status + waves + revisions)"
kubectl -n ${NS_ARGO} get applications ${APP_CRDS} ${APP_CP} -o wide 2>/dev/null || true
kubectl -n ${NS_ARGO} get application ${APP_CRDS} -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/sync-wave}{"\n"}' 2>/dev/null || true
kubectl -n ${NS_ARGO} get application ${APP_CP} -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/sync-wave}{"\n"}' 2>/dev/null || true
echo
kubectl -n ${NS_ARGO} get application ${APP_CRDS} -o jsonpath='CRDS targetRevision: {.spec.source.targetRevision}{"\n"}' 2>/dev/null || true
echo
kubectl -n ${NS_ARGO} get application ${APP_CP} -o jsonpath='Control-plane targetRevision: {.spec.source.targetRevision}{"\n"}' 2>/dev/null || true
echo
kubectl -n ${NS_ARGO} get application ${APP_CP} -o jsonpath='valuesFrom?: {.spec.source.helm.valuesFrom[*].name}{"\n"}' 2>/dev/null || true

say "External Secrets – CRDs present?"
kubectl get crd | grep -E 'externalsecrets|secretstores' || true

say "External Secrets – controllers"
kubectl -n external-secrets get deploy,po 2>/dev/null || true

say "IRSA annotations on service accounts"
kubectl -n ${NS_ARGO} get sa linkerd-values-reader -o jsonpath='argo/linkerd-values-reader role-arn: {.metadata.annotations.eks\.amazonaws\.com/role-arn}{"\n"}' 2>/dev/null || true
kubectl -n ${NS_LINKERD} get sa linkerd-secret-reader -o jsonpath='linkerd-system/linkerd-secret-reader role-arn: {.metadata.annotations.eks\.amazonaws\.com/role-arn}{"\n"}' 2>/dev/null || true

say "ExternalSecret / SecretStore / Secret in linkerd-system"
kubectl -n ${NS_LINKERD} get secretstore,externalsecret 2>/dev/null || true
kubectl -n ${NS_LINKERD} get secret linkerd-identity -o jsonpath='linkerd-identity keys: {.data}{"\n"}' 2>/dev/null || true

say "Argo 'linkerd-values' Secret (if valuesFrom is used)"
kubectl -n ${NS_ARGO} get secret linkerd-values -o 'jsonpath={.metadata.name}{"\n"}' 2>/dev/null || true

say "Linkerd control-plane pods"
kubectl -n ${NS_LINKERD} get deploy,po -o wide 2>/dev/null || true

if command -v linkerd >/dev/null 2>&1; then
  say "linkerd version"
  linkerd version || true
  say "linkerd check (control plane)"
  linkerd check --proxy=false || true
else
  say "linkerd CLI not found; skipping linkerd check"
fi

say "Done."
