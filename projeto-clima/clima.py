import os
import requests
import time
import mysql.connector
import concurrent.futures
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()  

CHAVE_API = os.getenv("API_KEY")
CIDADES = ["São Paulo, BR", "Rio de Janeiro, BR", "Belo Horizonte, BR", "Curitiba, BR", "Salvador, BR"]
URL_BASE = "https://api.openweathermap.org/data/2.5/weather?q={}&APPID={}&lang=pt_br&units=metric"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("clima.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def conectar_db():
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=3306
        )
        logger.info("Conexão com o banco de dados estabelecida.")
        return connection
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise

def criar_tabela(connection):
    try:
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS clima (
                id INT PRIMARY KEY AUTO_INCREMENT,
                cidade VARCHAR(255),
                temperatura FLOAT,
                sensacao_termica FLOAT,
                temperatura_maxima FLOAT,
                umidade INT,
                descricao TEXT,
                data_coleta TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_cidade (cidade),
                INDEX idx_data (data_coleta)
            )
        ''')
        connection.commit()
        logger.info("Tabela 'clima' verificada/criada.")
    except Exception as e:
        logger.error(f"Erro ao criar tabela: {e}")
        raise

def dados_recente(cursor, intervalo_minutos=1):
    tempo_limite = datetime.now() - timedelta(minutes=intervalo_minutos)
    cursor.execute(
        "SELECT cidade FROM clima WHERE data_coleta >= %s LIMIT 1",
        (tempo_limite,)
    )
    return cursor.fetchone()

def inserir_dados(cursor, connection, cidade, dados):
    try:
        cursor.execute(
            "INSERT INTO clima (cidade, temperatura, sensacao_termica, temperatura_maxima, umidade, descricao) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (cidade, dados['temp'], dados['feels_like'], dados['temp_max'], dados['humidity'], dados['description'])
        )
        connection.commit()
        logger.info(f"Dados de {cidade} inseridos com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inserir dados de {cidade}: {e}")
        connection.rollback()

def buscar_dados_cidade(cidade):
    try:
        resposta = requests.get(URL_BASE.format(cidade, CHAVE_API), timeout=10)
        resposta.raise_for_status()
        dados = resposta.json()
        return {
            'temp': dados['main']['temp'],
            'feels_like': dados['main']['feels_like'],
            'temp_max': dados['main']['temp_max'],
            'humidity': dados['main']['humidity'],
            'description': dados['weather'][0]['description']
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Falha na API para {cidade}: {e}")
        return None

def buscar_armazenar():
    try:
        connection = conectar_db()
        criar_tabela(connection)
        cursor = connection.cursor()

        if dados_recente(cursor):
            logger.info("Dados já coletados recentemente. Pulando...")
            return

        for cidade in CIDADES:
            dados = buscar_dados_cidade(cidade)
            if dados:
                inserir_dados(cursor, connection, cidade.split(",")[0], dados)
            time.sleep(1)  

    except Exception as e:
        logger.error(f"Erro geral em buscar_armazenar: {e}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()

if __name__ == "__main__":
    logger.info("Iniciando coleta de dados climáticos.")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:  
        futures = [executor.submit(buscar_armazenar) for _ in range(len(CIDADES))]
        for future in concurrent.futures.as_completed(futures):
            future.result() 