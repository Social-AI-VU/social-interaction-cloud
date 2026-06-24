FROM sic-base:local AS pypi
ARG SIC_VERSION
RUN pip install --no-cache-dir "social-interaction-cloud[openai-gpt]==${SIC_VERSION}"
CMD ["run-gpt"]

FROM sic-base:local AS local
COPY . /tmp/social-interaction-cloud
RUN pip install --no-cache-dir "/tmp/social-interaction-cloud[openai-gpt]" \
    && rm -rf /tmp/social-interaction-cloud
CMD ["run-gpt"]
