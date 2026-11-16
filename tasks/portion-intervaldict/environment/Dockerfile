# Starting environment for the "IntervalDict single-key operations" task.
#
# Everything is pinned: base image patch version, upstream commit, and every
# Python package. Network access is only needed while building the image; the
# task itself and its verifier run with networking disabled.
FROM python:3.12.16-slim-bookworm

# git is used to materialise the repository at the pinned commit, and by the
# harness to apply candidate patches.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt

# The real upstream library, at the exact commit the task starts from.
ARG PORTION_COMMIT=2c34f2830bef51b7bba3dd52e18b95daaf9de248
RUN git clone https://github.com/AlexandreDecan/portion.git /workspace/repo \
    && cd /workspace/repo \
    && git reset --hard "$PORTION_COMMIT"

# Editable install, so that edits to /workspace/repo are picked up directly and
# the package metadata required by the upstream test suite is available.
RUN pip install --no-cache-dir --no-deps --no-build-isolation -e /workspace/repo

# A pristine copy of the original IntervalDict, kept outside the repository.
# The verifier uses it as the behavioural oracle for differential testing. It is
# byte-for-byte the upstream file, except that its two relative imports are made
# absolute so that it can live outside the package; the checksum pins the result.
RUN mkdir /workspace/oracle \
    && sed -e 's/^from \.const/from portion.const/' \
           -e 's/^from \.interval/from portion.interval/' \
           /workspace/repo/portion/dict.py > /workspace/oracle/oracle_dict.py \
    && echo "339edad95f4e01c83051224303d6fcaba1a929d4975128842d2201e1784ca397  /workspace/oracle/oracle_dict.py" | sha256sum -c -

WORKDIR /workspace/repo
