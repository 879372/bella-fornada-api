import os
import subprocess
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Caminhos automáticos (funciona no Mac e na Railway)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# --- CONFIGURAÇÕES ---
S3_BUCKET = os.getenv('S3_BUCKET_NAME')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY_ID')
S3_SECRET_KEY = os.getenv('S3_SECRET_ACCESS_KEY')
S3_REGION = os.getenv('S3_REGION', 'us-east-1')
S3_ENDPOINT = os.getenv('S3_ENDPOINT')

DATABASE_URL = os.getenv('DATABASE_URL')

# Caminho Temporário (usa a pasta temporária do sistema na Railway)
BACKUP_DIR = "/tmp/backups"
os.makedirs(BACKUP_DIR, exist_ok=True)

DATE_STR = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
FILE_NAME = f"backup_railway_{DATE_STR}.sql.gz"
FILE_PATH = os.path.join(BACKUP_DIR, FILE_NAME)

def run_backup():
    if not DATABASE_URL:
        print("❌ DATABASE_URL não encontrada no .env")
        return

    print(f"[{datetime.now()}] Iniciando backup...")

    try:
        # Tenta usar pg_dump direto (Railway/Linux) com formato Custom (-Fc)
        print("Executando pg_dump (formato Custom)...")
        try:
            # -Fc: Binário e Compactado / --no-acl --no-owner: Evita erros de permissão
            dump_cmd = ["pg_dump", "-Fc", "--no-acl", "--no-owner", DATABASE_URL, "-f", FILE_PATH]
            subprocess.run(dump_cmd, capture_output=True, text=True, timeout=600, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            if isinstance(e, subprocess.CalledProcessError):
                print(f"pg_dump direto falhou com status {e.returncode}. Stderr: {e.stderr}")
            else:
                print("pg_dump direto não encontrado.")

            # Se falhar ou não achar pg_dump, tenta via Docker (Mac Local) usando postgres:18
            print("Tentando via Docker com postgres:18...")
            dump_cmd = ["docker", "run", "--rm", "postgres:18", "pg_dump", "-Fc", "--no-acl", "--no-owner", DATABASE_URL]
            try:
                with open(FILE_PATH, "wb") as f:
                    subprocess.check_call(dump_cmd, stdout=f, timeout=600)
            except Exception as docker_err:
                raise Exception(f"Erro tanto no pg_dump nativo quanto via Docker. Detalhes Docker: {docker_err}")
        except subprocess.TimeoutExpired:
            raise Exception("O backup demorou demais (mais de 10 min) e foi cancelado automaticamente.")

        # Verifica se o arquivo tem conteúdo
        file_size = os.path.getsize(FILE_PATH)
        if file_size < 100: # Um backup real compactado deve ter mais que 100 bytes
            raise Exception(f"O arquivo de backup gerado está muito pequeno ({file_size} bytes). Algo deu errado no dump.")

        print(f"Dump concluído ({file_size} bytes). Enviando para S3 ({S3_BUCKET})...")

        s3 = boto3.client(
            's3',
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT if S3_ENDPOINT else None
        )

        s3.upload_file(FILE_PATH, S3_BUCKET, f"backups/{FILE_NAME}")
        print(f"✅ Backup concluído com sucesso!")

        os.remove(FILE_PATH)

    except Exception as e:
        print(f"❌ ERRO no backup: {e}")

if __name__ == "__main__":
    run_backup()
