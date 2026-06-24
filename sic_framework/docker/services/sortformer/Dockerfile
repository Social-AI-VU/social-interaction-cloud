FROM sic-base:local AS pypi
ARG SIC_VERSION
RUN pip install --no-cache-dir "social-interaction-cloud[sortformer]==${SIC_VERSION}" \
    --extra-index-url https://download.pytorch.org/whl/cu130

FROM sic-base:local AS local
COPY . /tmp/social-interaction-cloud
RUN pip install --no-cache-dir "/tmp/social-interaction-cloud[sortformer]" \
    --extra-index-url https://download.pytorch.org/whl/cu130 \
    && rm -rf /tmp/social-interaction-cloud

CMD ["run-sortformer"]
