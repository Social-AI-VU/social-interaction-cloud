FROM sic-base:local AS pypi
RUN pip install --no-cache-dir "openai>=1.52.2" "python-dotenv"
CMD ["run-gpt"]

FROM sic-base:local AS local
COPY . /tmp/social-interaction-cloud
RUN pip install --no-cache-dir "/tmp/social-interaction-cloud[openai-gpt]" \
    && rm -rf /tmp/social-interaction-cloud
CMD ["run-gpt"]
