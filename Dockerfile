FROM python:3.8.2
LABEL maintainer="Lily Foster <lily@lily.flowers>"
WORKDIR /app
COPY . /app
RUN pip install -Ur requirements.txt
RUN ln -s config/config.json /app/config.json
ENTRYPOINT ["python3", "-m",  "dozer"]
