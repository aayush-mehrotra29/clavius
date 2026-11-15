# Build from the repository root. Native execution is gated by the benchmark,
# independently of whether the image builds successfully.
ARG ROS_IMAGE=ros:jazzy-ros-base-noble
FROM ${ROS_IMAGE}
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ENV DEBIAN_FRONTEND=noninteractive
RUN if dpkg-query -W libgz-sim8-plugins python3-gz-sim8 libgz-physics7-dartsim >/dev/null 2>&1; then echo 'Reusing the installed native SDK'; else \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates curl gnupg python3-venv \
    && curl -fsSL https://packages.osrfoundation.org/gazebo.gpg -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable noble main" > /etc/apt/sources.list.d/gazebo-stable.list \
    && apt-get update && apt-get install -y --no-install-recommends gz-sim8-cli python3-gz-sim8 libgz-sim8-plugins libgz-physics7-dartsim \
    && rm -rf /var/lib/apt/lists/*; fi
WORKDIR /opt/clavius
COPY requirements-simulation.txt ./
# The system interpreter is required by the Ubuntu Gazebo and ROS extensions.
RUN (test -x /opt/clavius-venv/bin/python || python3 -m venv --system-site-packages /opt/clavius-venv) \
    && /opt/clavius-venv/bin/python -m pip install --no-cache-dir -r requirements-simulation.txt
COPY backend ./backend
COPY contracts ./contracts
COPY public/robots ./public/robots
COPY public/data/simulation-manifest.json ./public/data/simulation-manifest.json
COPY scripts/benchmark_gazebo_worker.py ./scripts/benchmark_gazebo_worker.py
COPY workers/gazebo/entrypoint.sh ./workers/gazebo/entrypoint.sh
ENV PYTHONPATH=/opt/clavius/backend CLAVIUS_ROOT=/opt/clavius CLAVIUS_RUNTIME=/var/lib/clavius OPENBLAS_NUM_THREADS=1
RUN mkdir -p /var/lib/clavius && (id -u clavius >/dev/null 2>&1 || useradd --system --uid 10001 --home-dir /var/lib/clavius clavius) \
    && chown clavius:clavius /var/lib/clavius && chmod +x workers/gazebo/entrypoint.sh
USER clavius
EXPOSE 8002
ENTRYPOINT ["/opt/clavius/workers/gazebo/entrypoint.sh"]
CMD ["/opt/clavius-venv/bin/python", "-m", "uvicorn", "clavius.gazebo_worker:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]
