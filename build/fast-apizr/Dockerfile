ARG PYTHON_IMAGE_TAG

FROM python:${PYTHON_IMAGE_TAG}

ENV MODULE_NAME=fast-apizr
ENV PORT=5000

ADD src/$MODULE_NAME/ /app
ADD test/$MODULE_NAME/ /app/tests

# Set the working directory in the container
WORKDIR /app

# Install build dependencies, build the python packages, remove build dependencies
RUN set -ex \
    && apk add --no-cache --virtual .build-deps gcc musl-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Expose the service
EXPOSE $PORT

# Run the application
CMD ["uvicorn", "app:app", "--reload", "--host", "0.0.0.0", "--port", "${PORT}"]