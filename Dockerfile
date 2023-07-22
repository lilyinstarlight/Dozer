FROM python:3.10.6
WORKDIR /app
COPY . /app
RUN pip install -Ur requirements.txt
RUN ln -s config/config.json /app/config.json
ENTRYPOINT ["python3", "-m",  "dozer"]
