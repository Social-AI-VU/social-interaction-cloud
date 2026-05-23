FROM sic-base:local AS pypi
ARG SIC_VERSION
RUN pip install --no-cache-dir "social-interaction-cloud[webserver]==${SIC_VERSION}"

FROM sic-base:local AS local
COPY . /tmp/social-interaction-cloud
RUN pip install --no-cache-dir "/tmp/social-interaction-cloud[webserver]" \
    && rm -rf /tmp/social-interaction-cloud

CMD ["run-webserver"]
