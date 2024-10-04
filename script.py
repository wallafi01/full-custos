import boto3
import pandas as pd
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font

# Criando os clientes da AWS
ec2_client = boto3.client('ec2')
rds_client = boto3.client('rds')
s3_client = boto3.client('s3')
elb_client = boto3.client('elbv2')
vpc_client = boto3.client('ec2')
ecr_client = boto3.client('ecr')
ecs_client = boto3.client('ecs')
ce_client = boto3.client('ce')

# Obtendo o intervalo de datas para o custo
end_date = datetime.utcnow().date()
start_date = end_date - timedelta(days=30)  # Últimos 30 dias

# Função para obter o custo de um serviço específico por recurso
def get_cost_by_service(service_name):
    response = ce_client.get_cost_and_usage(
        TimePeriod={
            'Start': start_date.strftime('%Y-%m-%d'),
            'End': end_date.strftime('%Y-%m-%d')
        },
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        Filter={
            'Dimensions': {
                'Key': 'SERVICE',
                'Values': [service_name]
            }
        }
    )
    
    total_cost = sum(float(day['Total']['UnblendedCost']['Amount']) for day in response['ResultsByTime'])
    return total_cost

# Obtendo a região atual
region = boto3.session.Session().region_name

# Obtendo informações sobre EC2
ec2_instances = ec2_client.describe_instances()
ec2_data = []
for reservation in ec2_instances['Reservations']:
    for instance in reservation['Instances']:
        instance_name = next((tag['Value'] for tag in instance.get('Tags', []) if tag['Key'] == 'Name'), 'N/A')
        ec2_data.append({
            'Serviço': 'EC2',
            'Nome do Recurso': instance_name,
            'ID': instance['InstanceId'],
            'Tipo': instance['InstanceType'],
            'Status': instance['State']['Name'],
            'Custo': get_cost_by_service('Amazon Elastic Compute Cloud')
        })

# Obtendo informações sobre RDS
rds_instances = rds_client.describe_db_instances()
rds_data = []
for instance in rds_instances['DBInstances']:
    rds_data.append({
        'Serviço': 'RDS',
        'Nome do Recurso': instance['DBInstanceIdentifier'],
        'ID': instance['DBInstanceIdentifier'],
        'Tipo': instance['DBInstanceClass'],
        'Status': instance['DBInstanceStatus'],
        'Custo': get_cost_by_service('Amazon RDS')
    })

# Obtendo informações sobre S3 apenas nas regiões onde os buckets estão localizados
s3_buckets = s3_client.list_buckets()
s3_data = []
for bucket in s3_buckets['Buckets']:
    # Obtém a região do bucket
    bucket_region = s3_client.get_bucket_location(Bucket=bucket['Name'])['LocationConstraint']
    
    # Corrigindo 'None' para buckets criados na us-east-1
    if bucket_region is None:
        bucket_region = 'us-east-1'
    
    # Se o bucket estiver na mesma região que o cliente boto3
    if bucket_region == region:
        s3_data.append({
            'Serviço': 'S3',
            'Nome do Recurso': bucket['Name'],
            'ID': bucket['Name'],
            'Tipo': 'Bucket',
            'Status': 'Ativo',
            'Custo': get_cost_by_service('Amazon Simple Storage Service')
        })

# Obtendo informações sobre ELB
load_balancers = elb_client.describe_load_balancers()
elb_data = []
for lb in load_balancers['LoadBalancers']:
    elb_data.append({
        'Serviço': 'ELB',
        'Nome do Recurso': lb['LoadBalancerName'],
        'ID': lb['LoadBalancerArn'],
        'Tipo': lb['Type'],
        'Status': lb['State']['Code'],
        'Custo': get_cost_by_service('Elastic Load Balancing')
    })

# Obtendo informações sobre NAT Gateways
nat_gateways = vpc_client.describe_nat_gateways()
nat_data = []
for nat in nat_gateways['NatGateways']:
    nat_data.append({
        'Serviço': 'NAT Gateway',
        'Nome do Recurso': nat['NatGatewayId'],
        'ID': nat['NatGatewayId'],
        'Tipo': 'NAT Gateway',
        'Status': nat['State'],
        'Custo': get_cost_by_service('NAT Gateway')
    })

# Obtendo informações sobre ECR
ecr_repositories = ecr_client.describe_repositories()
ecr_data = []
for repo in ecr_repositories['repositories']:
    ecr_data.append({
        'Serviço': 'ECR',
        'Nome do Recurso': repo['repositoryName'],
        'ID': repo['repositoryArn'],
        'Tipo': 'Repositório',
        'Status': 'Ativo',
        'Custo': get_cost_by_service('Amazon Elastic Container Registry')
    })

# Obtendo informações sobre ECS
ecs_clusters = ecs_client.list_clusters()
ecs_data = []
for cluster_arn in ecs_clusters['clusterArns']:
    cluster_name = cluster_arn.split('/')[-1]
    services = ecs_client.list_services(cluster=cluster_arn)
    
    for service in services['serviceArns']:
        service_desc = ecs_client.describe_services(cluster=cluster_arn, services=[service])
        task_def_arn = service_desc['services'][0]['taskDefinition']
        task_def_desc = ecs_client.describe_task_definition(taskDefinition=task_def_arn)
        
        ecs_data.append({
            'Serviço': 'ECS',
            'Nome do Recurso': service_desc['services'][0]['serviceName'],
            'ID': service_desc['services'][0]['serviceArn'],
            'Tipo': 'Serviço',
            'Status': service_desc['services'][0]['status'],
            'Custo': get_cost_by_service('Amazon Elastic Container Service')
        })

        # Adicionando a definição da tarefa
        ecs_data.append({
            'Serviço': 'ECS',
            'Nome do Recurso': task_def_desc['taskDefinition']['family'],
            'ID': task_def_arn,
            'Tipo': 'Definição de Tarefa',
            'Status': 'Ativo',
            'Custo': get_cost_by_service('Amazon Elastic Container Service')
        })

# Obtendo informações sobre volumes EBS
ebs_volumes = ec2_client.describe_volumes()
ebs_data = []
for volume in ebs_volumes['Volumes']:
    ebs_data.append({
        'Serviço': 'EBS',
        'Nome do Recurso': volume['VolumeId'],
        'ID': volume['VolumeId'],
        'Tipo': volume['VolumeType'],
        'Status': volume['State'],
        'Custo': get_cost_by_service('Amazon Elastic Block Store')
    })

# Obtendo informações sobre AMIs
amis = ec2_client.describe_images(Owners=['self'])  # Filtrando pelas AMIs criadas pelo usuário
ami_data = []
for ami in amis['Images']:
    ami_data.append({
        'Serviço': 'AMI',
        'Nome do Recurso': ami['Name'],
        'ID': ami['ImageId'],
        'Tipo': 'AMI',
        'Status': 'Disponível',
        'Custo': 'N/A'  # AMIs não têm custo direto separado
    })

# Unindo todos os dados
all_data = ec2_data + rds_data + s3_data + elb_data + nat_data + ecr_data + ecs_data + ebs_data + ami_data
df = pd.DataFrame(all_data)

# Salvando o relatório
output_filename = f'relatorios/aws_cost_usage_report_{region}.xlsx'
df.to_excel(output_filename, index=False)

# Formatando a planilha
wb = Workbook()
ws = wb.active
ws.title = "Relatório de Custos"

# Adicionando cabeçalhos
headers = df.columns.tolist()
ws.append(headers)


# Definindo estilos para os cabeçalhos
header_fill = PatternFill(start_color="00FFCC", end_color="00FFCC", fill_type="solid")
bold_font = Font(bold=True)

# Aplicando estilos aos cabeçalhos
for col in range(1, len(headers) + 1):
    cell = ws.cell(row=1, column=col)
    cell.fill = header_fill  # Preenchimento apenas para cabeçalhos
    cell.font = bold_font  # Texto em negrito

# Adicionando os dados
for row in df.itertuples(index=False):
    ws.append(row)

# Salvando a planilha formatada
wb.save(output_filename)

print(f'Relatório gerado com sucesso: {output_filename}')
