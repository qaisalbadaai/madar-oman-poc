# Reproduces the notebook in a clean container:
#   docker build -t madar-oman-poc .
#   docker run --rm -v "$PWD/results:/app/results" madar-oman-poc
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace", "notebooks/01_flood_shaheen_khaburah.ipynb"]
