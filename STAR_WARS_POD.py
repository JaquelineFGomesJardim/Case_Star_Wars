#%%
import json
import boto3
import requests
import openai
import os
import zipfile
import time
import subprocess
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

#%%
# Configuração do logger para monitoramento no AWS CloudWatch
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

#%% 
# Criar cliente do AWS Secrets Manager
secrets_client = boto3.client("secretsmanager", region_name="us-east-1")

def get_secret(secret_name):
    """
    Recupera um segredo armazenado no AWS Secrets Manager.
    Se não for encontrado, exibe um erro e encerra a execução.
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret = json.loads(response["SecretString"])
        return secret
    except secrets_client.exceptions.ResourceNotFoundException:
        logger.error(f"❌ ERRO: O segredo '{secret_name}' não foi encontrado no AWS Secrets Manager.")
        exit(1)
    except Exception as e:
        logger.error(f"❌ ERRO ao recuperar segredo: {e}")
        exit(1)

# Obtendo credenciais de forma segura
secrets = get_secret("StarWarsStorySecret")

# Definir as chaves API
OPENAI_API_KEY = secrets.get("OPENAI_API_KEY")
AWS_ACCESS_KEY = secrets.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = secrets.get("AWS_SECRET_ACCESS_KEY")
AWS_REGION = secrets.get("AWS_DEFAULT_REGION", "us-east-1")
AWS_ACCOUNT_ID = secrets.get("AWS_ACCOUNT_ID")

if not OPENAI_API_KEY or not AWS_ACCESS_KEY or not AWS_SECRET_KEY:
    logger.error("❌ ERRO: Algumas credenciais não foram carregadas corretamente.")
    exit(1)

# Configurar OpenAI
openai.api_key = OPENAI_API_KEY

#%% 

# Criando clientes AWS
lambda_client = boto3.client("lambda", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)
apigateway_client = boto3.client("apigateway", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)
iam_client = boto3.client("iam", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY, region_name=AWS_REGION)

#%% 

# Instalar dependências na pasta package/
def install_dependencies():
    dependencies = ["requests", "openai==0.28.0", "boto3", "pydantic==1.9.0", "python-dotenv"]
    try:
        subprocess.run(["pip", "install", "-t", "package"] + dependencies, check=True)
        logger.info("✅ Dependências instaladas com sucesso!")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Erro ao instalar dependências: {e}")
        exit(1)

#%% 

# Configuração AWS
LAMBDA_FUNCTION_NAME = "StarWarsStoryLambda"
API_NAME = "StarWarsAPI"
STAGE_NAME = "prod"

#%% 

# Criar cliente para acessar a AWS Lambda
lambda_client = boto3.client("lambda", region_name="us-east-1")

#%% 

# Atualizar variável OPENAI_API_KEY na Lambda
def update_lambda_environment():
    """
    Atualiza as variáveis de ambiente da função AWS Lambda.
    Agora, verifica se a função realmente existe antes de tentar atualizar.
    """
    try:
        # Verifica se a função Lambda já existe antes de atualizar
        response = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        current_env_vars = response.get("Configuration", {}).get("Environment", {}).get("Variables", {})

        if not current_env_vars.get("OPENAI_API_KEY"):
            logger.info("🔹 Definindo OPENAI_API_KEY na Lambda...")
            current_env_vars["OPENAI_API_KEY"] = OPENAI_API_KEY

            lambda_client.update_function_configuration(
                FunctionName=LAMBDA_FUNCTION_NAME,
                Environment={"Variables": current_env_vars}
            )

            logger.info("✅ Variável OPENAI_API_KEY configurada na Lambda com sucesso!")
            time.sleep(10)
        else:
            logger.info("⚠️ OPENAI_API_KEY já está configurada na Lambda.")

    except lambda_client.exceptions.ResourceNotFoundException:
        logger.error(f"❌ Erro: A função '{LAMBDA_FUNCTION_NAME}' ainda não existe. Pulando atualização de variáveis.")
    except Exception as e:
        logger.error(f"❌ Erro ao configurar variáveis de ambiente na Lambda: {e}")

#%% 

# Código da Lambda otimizado para baixa latência
LAMBDA_CODE = """import json
import requests
import openai
import os
import logging
from concurrent.futures import ThreadPoolExecutor

# Configuração do logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# Carregar a chave da API da OpenAI da variável de ambiente AWS
openai.api_key = os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    raise ValueError("❌ ERRO: A chave da OpenAI não foi carregada. Verifique as variáveis de ambiente da Lambda.")

def obter_info_star_wars(tipo, nome):
    url = f"https://swapi.dev/api/{tipo}/?search={nome}"
    response = requests.get(url)
    if response.status_code == 200 and response.json()["count"] > 0:
        return response.json()["results"][0]
    return None

def obter_varios_itens(tipo, nomes):
    with ThreadPoolExecutor() as executor:
        resultados = list(executor.map(lambda nome: obter_info_star_wars(tipo, nome), nomes))
    return [item for item in resultados if item]

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        personagens = body.get("personagens", [])
        naves = body.get("naves", [])
        planetas = body.get("planetas", [])
        ideias_extras = body.get("ideias_extras", "")

        dados_personagens = obter_varios_itens("people", personagens)
        dados_naves = obter_varios_itens("starships", naves)
        dados_planetas = obter_varios_itens("planets", planetas)

        def gerar_historia(personagens, naves, planetas, ideias_extras):
            prompt = f\"\"\"
Crie uma história envolvente no universo Star Wars considerando os seguintes elementos:
- Personagens: {personagens}
- Naves: {naves}
- Planetas: {planetas}
- Ideias Extras: {ideias_extras}
\"\"\"
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return response["choices"][0]["message"]["content"].strip()

        historia = gerar_historia(dados_personagens, dados_naves, dados_planetas, ideias_extras)

        return {
            "statusCode": 200,
            "body": json.dumps({"historia": historia}, ensure_ascii=False)
        }

    except Exception as e:
        logger.error(f"Erro na execução da Lambda: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"erro": str(e)})
        }
"""

# Criar `lambda_function.py` corretamente
with open("lambda_function.py", "w", encoding="utf-8") as f:
    f.write(LAMBDA_CODE)
logger.info("✅ Arquivo lambda_function.py criado com sucesso!")

# Criar ZIP da Lambda
def create_lambda_zip():
    install_dependencies()
    with zipfile.ZipFile("lambda_function.zip", "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk("package"):
            for file in files:
                zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), "package"))
        zipf.write("lambda_function.py")
    logger.info("✅ Arquivo lambda_function.zip criado com sucesso!")

# Atualizar variável de ambiente na Lambda
update_lambda_environment()

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
def create_lambda_role():
    """
    Cria ou atualiza a Role IAM da Lambda garantindo que todas as permissões necessárias estejam configuradas.
    """
    role_name = "StarWarsStoryLambdaRole"

    try:
        role = iam_client.get_role(RoleName=role_name)
        print(f"✅ Role IAM '{role_name}' encontrada.")

    except iam_client.exceptions.NoSuchEntityException:
        print(f"🔹 Criando a Role IAM '{role_name}'...")
        try:
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole"
                        }
                    ]
                })
            )
            print(f"✅ Role IAM '{role_name}' criada com sucesso.")
            time.sleep(5)  # Pequena pausa para garantir propagação da Role
        except Exception as e:
            print(f"❌ Erro ao criar a Role '{role_name}': {e}")
            return None

    # Lista das permissões necessárias
    required_policies = [
        "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",  # Logs no CloudWatch
        "arn:aws:iam::aws:policy/AmazonSSMFullAccess",  # Acesso ao SSM Parameter Store (se necessário)
        "arn:aws:iam::aws:policy/SecretsManagerReadWrite"  # Acesso ao AWS Secrets Manager
    ]

    # Lista permissões já anexadas
    attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)["AttachedPolicies"]
    attached_arns = [policy["PolicyArn"] for policy in attached_policies]

    # Adiciona apenas permissões que não estão anexadas
    for policy in required_policies:
        if policy not in attached_arns:
            iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy)
            print(f"✅ Permissão '{policy}' adicionada à Role '{role_name}'.")

    print(f"✅ Role '{role_name}' está totalmente configurada e pronta para uso.")

    # Aguarde a propagação da Role antes de usá-la
    for _ in range(5):  # Tenta verificar a Role por 5 tentativas
        try:
            role = iam_client.get_role(RoleName=role_name)
            print(f"✅ Role propagada com sucesso!")
            break
        except iam_client.exceptions.NoSuchEntityException:
            print("🔄 Aguardando propagação da Role...")
            time.sleep(5)

    role = iam_client.get_role(RoleName=role_name)
    return role["Role"]["Arn"]

#%%
def create_lambda():
    """
    Cria a função AWS Lambda com a Role correta e configura a integração.
    """
    lambda_role_arn = create_lambda_role()

    try:
        response = lambda_client.create_function(
            FunctionName=LAMBDA_FUNCTION_NAME,
            Runtime="python3.9",
            Role=lambda_role_arn,  # Agora a Role é garantida antes da Lambda ser criada
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": open("lambda_function.zip", "rb").read()},
            Timeout=30
        )
        logger.info(f"✅ Função Lambda '{LAMBDA_FUNCTION_NAME}' criada com sucesso.")

        # 🔄 Aguarda alguns segundos para evitar erros de integração
        logger.info("🔄 Aguardando a Lambda estar completamente disponível...")
        time.sleep(5)  

        return response["FunctionArn"]

    except lambda_client.exceptions.ResourceConflictException:
        logger.warning(f"⚠️ A função Lambda '{LAMBDA_FUNCTION_NAME}' já existe. Obtendo ARN...")
        response = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
        return response["Configuration"]["FunctionArn"]

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

    print("🔹 Criando pacote ZIP para Lambda...")
    create_lambda_zip()

    print("🔹 Criando função Lambda na AWS...")
    lambda_arn = create_lambda()

    print("🔹 Atualizando variáveis de ambiente na Lambda...")
    update_lambda_environment()

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
