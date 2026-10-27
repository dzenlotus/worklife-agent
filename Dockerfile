FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && pip install --no-cache-dir --no-deps .
RUN useradd --create-home --uid 10001 worklife && mkdir /data && chown worklife:worklife /data
USER worklife
ENV WORKLIFE_HOME=/data
EXPOSE 8765
ENTRYPOINT ["worklife"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
