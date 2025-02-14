#%%

import json
import boto3
import requests
import openai
import os
import zipfile
import time
import subprocess
from dotenv import load_dotenv

#%%
# Criar .env se não existir
env_path = ".env"
if not os.path.exists(env_path):
    with open(env_path, "w") as env_file:
        env_file.write(f"""
AWS_ACCESS_KEY_ID={os.getenv('AWS_ACCESS_KEY_ID', '')}
AWS_SECRET_ACCESS_KEY={os.getenv('AWS_SECRET_ACCESS_KEY', '')}
AWS_DEFAULT_REGION={os.getenv('AWS_DEFAULT_REGION', 'us-east-1')}
OPENAI_API_KEY={os.getenv('OPENAI_API_KEY', '')}
AWS_ACCOUNT_ID={os.getenv('AWS_ACCOUNT_ID', '')}
""")
    print("⚠️ O arquivo .env foi criado. Adicione suas credenciais nele antes de rodar o script novamente.")
    exit()

#%%
# Carregar variáveis de ambiente
load_dotenv()

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCOUNT_ID = os.getenv("AWS_ACCOUNT_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not AWS_ACCESS_KEY or not AWS_SECRET_KEY or not OPENAI_API_KEY or not AWS_ACCOUNT_ID:
    print("❌ Erro: Credenciais ausentes no .env!")
    exit()

#%%
# Criando clientes AWS
lambda_client = boto3.client("lambda", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)
apigateway_client = boto3.client("apigateway", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)
iam_client = boto3.client("iam", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)

#%%
# Instalar dependências na pasta package/
def install_dependencies():
    """
    Instala todas as dependências no diretório `package/` antes de empacotar.
    """
    dependencies = ["requests", "openai==0.28.0", "boto3", "pydantic==1.9.0", "python-dotenv", "jiter"]
    
    try:
        subprocess.run(["pip", "install", "-t", "package"] + dependencies, check=True)
        print("✅ Dependências instaladas com sucesso!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao instalar dependências: {e}")
        exit(1)

#%%
# Configuração AWS
LAMBDA_FUNCTION_NAME = "StarWarsStoryLambda"
API_NAME = "StarWarsAPI"
STAGE_NAME = "prod"

#%%
# Código da Lambda corrigido para OpenAI 0.28.0
import json
import requests
import openai
import os
import boto3

#%%
# Criar cliente para acessar a AWS Lambda
lambda_client = boto3.client("lambda", region_name="us-east-1")

#%%
# Definir a chave da OpenAI na AWS Lambda automaticamente
def update_lambda_environment():
    """
    Atualiza as variáveis de ambiente da função AWS Lambda, garantindo que `OPENAI_API_KEY` esteja configurada.
    """
    try:
        # Obtendo as variáveis de ambiente já existentes na Lambda
        response = lambda_client.get_function_configuration(FunctionName="StarWarsStoryLambda")

        # Variáveis já existentes
        current_env_vars = response.get("Environment", {}).get("Variables", {})

        # Definir a chave OpenAI caso não exista
        if "OPENAI_API_KEY" not in current_env_vars or not current_env_vars["OPENAI_API_KEY"]:
            print("🔹 Definindo OPENAI_API_KEY na Lambda...")

            # Atualizando variável de ambiente
            current_env_vars["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

            lambda_client.update_function_configuration(
                FunctionName="StarWarsStoryLambda",
                Environment={"Variables": current_env_vars}
            )

            print("✅ Variável OPENAI_API_KEY configurada na Lambda com sucesso!")
            print("⏳ Aguardando propagação das variáveis...")
            time.sleep(10)  # Espera para garantir que a chave foi propagada corretamente
        else:
            print("⚠️ OPENAI_API_KEY já está configurada na Lambda.")

    except Exception as e:
        print(f"❌ Erro ao configurar variáveis de ambiente na Lambda: {e}")

# Atualiza a variável de ambiente antes de carregar a OpenAI
update_lambda_environment()

# Carregar a chave da API da OpenAI da variável de ambiente AWS
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    raise ValueError("❌ ERRO: A chave da OpenAI não foi carregada. Verifique as variáveis de ambiente da Lambda.")

#%%
# Código da Lambda corrigido para OpenAI 0.28.0
LAMBDA_CODE = """import json
import requests
import openai
import os

# Carregar a chave da API da OpenAI da variável de ambiente AWS
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    raise ValueError("❌ ERRO: A chave da OpenAI não foi carregada. Verifique as variáveis de ambiente da Lambda.")

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        personagens = body.get("personagens", [])
        naves = body.get("naves", [])
        planetas = body.get("planetas", [])

        def obter_info_star_wars(tipo, nome):
            url = f"https://swapi.dev/api/{tipo}/?search={nome}"
            response = requests.get(url)
            if response.status_code == 200 and response.json()["count"] > 0:
                return response.json()["results"][0]
            return None

        dados_personagens = [obter_info_star_wars("people", p) for p in personagens]
        dados_naves = [obter_info_star_wars("starships", n) for n in naves]
        dados_planetas = [obter_info_star_wars("planets", pl) for pl in planetas]

        def gerar_historia(preferencias):
            prompt = f\"\"\"
Crie uma história envolvente no universo Star Wars considerando:
- Personagens: {preferencias.get('personagens', 'Não informados')}
- Naves: {preferencias.get('naves', 'Não informadas')}
- Planetas: {preferencias.get('planetas', 'Não informados')}
\"\"\"

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Ou "gpt-4" para uma resposta mais avançada
                messages=[
                    {"role": "system", "content": "Você é um escritor criativo no universo Star Wars."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            return response["choices"][0]["message"]["content"].strip()

        preferencias = {"personagens": dados_personagens, "naves": dados_naves, "planetas": dados_planetas}
        historia = gerar_historia(preferencias)

        return {"statusCode": 200, "body": json.dumps({"historia": historia}, ensure_ascii=False)}

    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"erro": str(e)})}
"""

# Criar lambda_function.py
with open("lambda_function.py", "w", encoding="utf-8") as f:
    f.write(LAMBDA_CODE)

print("✅ Arquivo lambda_function.py criado com sucesso!")


#%%
# Criar o ZIP para a Lambda
def create_lambda_zip():
    install_dependencies()
    with zipfile.ZipFile("lambda_function.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk("package"):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), "package"))
        zipf.write("lambda_function.py")
    print("✅ Arquivo lambda_function.zip criado com sucesso!")

#%%
def get_lambda_arn():
    """
    Obtém o ARN da função Lambda se ela já existir.
    """
    try:
        response = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        return response["Configuration"]["FunctionArn"]
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"⚠️ A função Lambda '{LAMBDA_FUNCTION_NAME}' não existe. Criando nova função...")
        return None

#%%

# Criar função Lambda
def create_lambda():
    try:
        with open("lambda_function.zip", "rb") as f:
            zipped_code = f.read()

        response = lambda_client.create_function(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Runtime="python3.9",
            Role=create_lambda_role(),
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zipped_code},
            Timeout=30
        )

        print(f"✅ Função Lambda criada com sucesso: {response['FunctionArn']}")
        return response["FunctionArn"]

    except lambda_client.exceptions.ResourceConflictException:
        print("⚠️ Função Lambda já existe. Obtendo ARN...")
        return get_lambda_arn()

#%%
# Criar a Role da Lambda
def create_lambda_role():
    role_name = "StarWarsStoryLambdaRole"
    try:
        response = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
            })
        )
        print(f"✅ Role IAM '{role_name}' criada com sucesso.")
    except iam_client.exceptions.EntityAlreadyExistsException:
        print(f"⚠️ Role IAM '{role_name}' já existe.")

    return iam_client.get_role(RoleName=role_name)["Role"]["Arn"]

#%%
def create_resource(api_id, parent_id, resource_path="story"):
    """
    Cria um recurso (endpoint) no API Gateway para a função Lambda.
    Se o recurso já existir, retorna seu ID.
    """
    response = apigateway_client.get_resources(restApiId=api_id)

    for item in response["items"]:
        if item.get("pathPart") == resource_path:
            print(f"⚠️ Recurso '{resource_path}' já existe. Usando ID existente: {item['id']}")
            return item["id"]

    response = apigateway_client.create_resource(
        restApiId=api_id,
        parentId=parent_id,
        pathPart=resource_path
    )

    print(f"✅ Recurso '/{resource_path}' criado com sucesso!")
    return response["id"]

#%%
def configure_method(api_id, resource_id):
    """
    Configura o método HTTP POST na API Gateway para que a Lambda possa receber requisições.
    """
    existing_methods = apigateway_client.get_resource(restApiId=api_id, resourceId=resource_id)
    existing_http_methods = existing_methods.get("resourceMethods", {}).keys()

    if "POST" in existing_http_methods:
        print("⚠️ Método POST já existe para este recurso. Pulando criação.")
        return

    apigateway_client.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="POST",
        authorizationType="NONE"
    )

    print("✅ Método POST configurado com sucesso!")

#%%
def configure_method_response(api_id, resource_id):
    """
    Configura a resposta do método HTTP POST para evitar erro de autenticação no API Gateway.
    """
    existing_responses = apigateway_client.get_method(restApiId=api_id, resourceId=resource_id, httpMethod="POST")

    if "200" in existing_responses.get("methodResponses", {}):
        print("⚠️ Resposta para método POST já existe. Pulando criação.")
        return

    apigateway_client.put_method_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="POST",
        statusCode="200",
        responseModels={"application/json": "Empty"}
    )

    print("✅ Resposta do método POST configurada com sucesso!")

#%%
def configure_lambda_integration(api_id, resource_id, lambda_arn):
    """
    Configura a integração entre a API Gateway e a função Lambda.
    """
    apigateway_client.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="POST",
        type="AWS_PROXY",
        integrationHttpMethod="POST",
        uri=f"arn:aws:apigateway:{AWS_REGION}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    )

    print("✅ Integração da API Gateway com a Lambda configurada!")

#%%
def add_lambda_permission(api_id):
    """
    Adiciona permissões para permitir que a API Gateway invoque a função Lambda.
    """
    try:
        lambda_client.add_permission(
            FunctionName=LAMBDA_FUNCTION_NAME,
            StatementId="APIGatewayInvoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{AWS_REGION}:{AWS_ACCOUNT_ID}:{api_id}/prod/POST/story"
        )
        print("✅ Permissão adicionada para API Gateway chamar a Lambda!")
    except lambda_client.exceptions.ResourceConflictException:
        print("⚠️ Permissão 'APIGatewayInvoke' já existe. Pulando este passo.")

#%%
def deploy_api(api_id):
    """
    Implanta a API Gateway no stage 'prod', tornando-a acessível publicamente.
    """
    try:
        apigateway_client.create_deployment(
            restApiId=api_id,
            stageName=STAGE_NAME
        )
        print(f"✅ API implantada no stage '{STAGE_NAME}'!")
    except Exception as e:
        print(f"❌ Erro ao implantar API Gateway: {e}")


#%%
def create_api_gateway():
    """
    Verifica se a API já existe antes de criar uma nova no API Gateway.
    """
    try:
        existing_apis = apigateway_client.get_rest_apis(limit=50)  # Obtém as APIs existentes
        for api in existing_apis["items"]:
            if api["name"] == API_NAME:
                print(f"⚠️ API '{API_NAME}' já existe. Usando API ID existente: {api['id']}")
                return api["id"], apigateway_client.get_resources(restApiId=api["id"])["items"][0]["id"]

        response = apigateway_client.create_rest_api(
            name=API_NAME,
            description="API para processar histórias do Star Wars",
            endpointConfiguration={"types": ["REGIONAL"]}
        )

        api_id = response["id"]
        root_id = apigateway_client.get_resources(restApiId=api_id)["items"][0]["id"]
        print(f"✅ API '{API_NAME}' criada com sucesso. ID: {api_id}")
        return api_id, root_id

    except Exception as e:
        print(f"❌ Erro ao criar API Gateway: {e}")
        exit(1)

#%%
# Executa todo o processo
def main():
    """
    Executa todas as etapas necessárias para criar a função AWS Lambda,
    configurar o API Gateway e implantar a API na AWS.
    """

    print("🔹 Atualizando variáveis de ambiente na Lambda...")
    update_lambda_environment()  # 🔹 Adiciona automaticamente a chave OPENAI_API_KEY na AWS Lambda

    print("🔹 Criando pacote ZIP para Lambda...")
    create_lambda_zip()

    print("🔹 Criando função Lambda na AWS...")
    lambda_arn = create_lambda()

    print("🔹 Criando API Gateway...")
    api_id, root_id = create_api_gateway()

    print("🔹 Criando recurso na API Gateway...")
    resource_id = create_resource(api_id, root_id)

    print("🔹 Configurando método HTTP POST na API Gateway...")
    configure_method(api_id, resource_id)

    print("🔹 Configurando resposta para o método POST...")
    configure_method_response(api_id, resource_id)

    print("🔹 Integrando API Gateway com a Lambda...")
    configure_lambda_integration(api_id, resource_id, lambda_arn)

    print("🔹 Adicionando permissões para a API Gateway chamar a Lambda...")
    add_lambda_permission(api_id)

    print("🔹 Implantando a API Gateway no stage 'prod'...")
    deploy_api(api_id)

    api_url = f"https://{api_id}.execute-api.{AWS_REGION}.amazonaws.com/{STAGE_NAME}/story"

    print(f"🎯 Deploy concluído com sucesso!")
    print(f"🚀 Sua API está disponível em: {api_url}")


if __name__ == "__main__":
    main()
