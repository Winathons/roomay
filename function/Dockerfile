# Workpeg's function base image begins at SDK 0.157.0.
# The Peg UI remains pinned separately to SDK 0.152.0.
# No Function is installed, submitted, or enabled by this Dockerfile.
FROM registry.gitlab.com/workpeg/workpeg-sdk/pegfn-base:0.157.0

# The base supplies the non-root appuser, /app workdir, SDK and runtime.
# No requirements or online build steps are needed for this disabled entrypoint.
COPY app /app/app
COPY domain /app/domain
