#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

IMAGE_REPO="${DEER_FLOW_IMAGE_REPO:-kkk2099/kkk}"
IMAGE_VERSION="${DEER_FLOW_IMAGE_VERSION:-1.0.0}"
REGISTRY_SERVICES="${DEER_FLOW_REGISTRY_SERVICES:-frontend gateway langgraph}"

usage() {
    cat <<EOF
Usage:
  scripts/registry-deploy.sh release [--standard|--gateway]
      Build with the native deploy script, tag images for Docker Hub, then push.

  scripts/registry-deploy.sh build
      Build images with the native deploy script only.

  scripts/registry-deploy.sh push
      Tag current local images and push them to Docker Hub.

  scripts/registry-deploy.sh pull
      Pull Docker Hub images and tag them back to native local image names.

  scripts/registry-deploy.sh up [--standard|--gateway]
      Pull/tag Docker Hub images, then start with the native deploy script
      without rebuilding.

  scripts/registry-deploy.sh start [--standard|--gateway]
      Start with the native deploy script without pull/build.

  scripts/registry-deploy.sh down
      Stop with the native deploy script.

  scripts/registry-deploy.sh images
      Print local-to-registry image mapping.

Environment:
  DEER_FLOW_IMAGE_REPO       default: kkk2099/kkk
  DEER_FLOW_IMAGE_VERSION    default: 1.0.0
  DEER_FLOW_REGISTRY_SERVICES default: frontend gateway langgraph

Examples:
  DEER_FLOW_IMAGE_VERSION=1.0.1 scripts/registry-deploy.sh release
  DEER_FLOW_IMAGE_VERSION=1.0.1 scripts/registry-deploy.sh up
  DEER_FLOW_REGISTRY_SERVICES="frontend gateway langgraph provisioner" scripts/registry-deploy.sh release
EOF
}

local_image() {
    printf 'deer-flow-%s' "$1"
}

remote_image() {
    printf '%s:deer-flow-%s-%s' "$IMAGE_REPO" "$1" "$IMAGE_VERSION"
}

print_images() {
    for service in $REGISTRY_SERVICES; do
        printf '%-24s -> %s\n' "$(local_image "$service")" "$(remote_image "$service")"
    done
}

tag_for_push() {
    for service in $REGISTRY_SERVICES; do
        docker image inspect "$(local_image "$service")" >/dev/null
        docker tag "$(local_image "$service")" "$(remote_image "$service")"
    done
}

push_images() {
    tag_for_push
    for service in $REGISTRY_SERVICES; do
        docker push "$(remote_image "$service")"
    done
}

pull_images() {
    for service in $REGISTRY_SERVICES; do
        docker pull "$(remote_image "$service")"
        docker tag "$(remote_image "$service")" "$(local_image "$service")"
    done
}

mode_arg="${2:-}"
case "$mode_arg" in
    ""|--standard|--gateway) ;;
    *)
        echo "Unknown mode: $mode_arg" >&2
        usage
        exit 1
        ;;
esac

cd "$REPO_ROOT"

case "${1:-}" in
    release)
        "$REPO_ROOT/scripts/deploy.sh" build
        push_images
        ;;
    build)
        "$REPO_ROOT/scripts/deploy.sh" build
        ;;
    push)
        push_images
        ;;
    pull)
        pull_images
        ;;
    up)
        pull_images
        "$REPO_ROOT/scripts/deploy.sh" start ${mode_arg:---standard}
        ;;
    start)
        "$REPO_ROOT/scripts/deploy.sh" start ${mode_arg:---standard}
        ;;
    down)
        "$REPO_ROOT/scripts/deploy.sh" down
        ;;
    images)
        print_images
        ;;
    ""|-h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: $1" >&2
        usage
        exit 1
        ;;
esac
