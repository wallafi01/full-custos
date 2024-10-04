# Usando uma imagem base do Python
FROM python:3.9-slim

# Definindo o diretório de trabalho dentro do container
WORKDIR /app

# Copiando os arquivos requirements.txt e o script Python para o diretório de trabalho
COPY requirements.txt requirements.txt
COPY script.py script.py

# Instalando as dependências
RUN pip install --no-cache-dir -r requirements.txt

# Comando padrão para executar o script Python
CMD ["python", "script.py"]
