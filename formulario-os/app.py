import os
import csv
import base64
from flask import Flask, request, render_template_string, jsonify
from werkzeug.utils import secure_filename
import datetime
from pytz import timezone
from github import Github, GithubException
from io import StringIO

app = Flask(__name__)

# --- Configuração do GitHub ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
CSV_FILE_PATH = 'submissions.csv'
UPLOAD_FOLDER_PATH = 'uploads'

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def form():
    protocolo = request.args.get('protocolo', '')
    nome_cliente = request.args.get('nome_cliente', '')
    endereco = request.args.get('endereco', '')
    nome_tecnico = request.args.get('nome_tecnico', '')

    with open('templates/form.html', 'r', encoding='utf-8') as f:
        template_string = f.read()
    return render_template_string(template_string, 
                                  protocolo=protocolo, 
                                  nome_cliente=nome_cliente, 
                                  endereco=endereco,
                                  nome_tecnico=nome_tecnico)

@app.route('/submit', methods=['POST'])
def submit():
    sao_paulo_tz = timezone('America/Sao_Paulo')
    now_sao_paulo = datetime.datetime.now(sao_paulo_tz)

    data = {
        'timestamp': now_sao_paulo.strftime('%d/%m/%Y %H:%M:%S'),
        'protocolo': request.form.get('protocolo'),
        'nome_tecnico': request.form.get('nome_tecnico'),
        'servico_executado': request.form.get('servico_executado'),
        'senha_cliente': request.form.get('senha_cliente'),
        'foto_servico_url': '',
        'foto_documento_url': ''
    }

    # Upload de ficheiros para o GitHub
    for key in ['foto_servico', 'foto_documento']:
        if key in request.files:
            file = request.files[key]
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{data['protocolo']}_{key}_{file.filename}")
                file_content = file.read()
                file_path_in_repo = f"{UPLOAD_FOLDER_PATH}/{filename}"

                try:
                    # Verifica se o ficheiro já existe para o atualizar
                    contents = repo.get_contents(file_path_in_repo)
                    repo.update_file(contents.path, f"Atualiza {filename}", file_content, contents.sha)
                except GithubException:
                    # Se não existir, cria um novo
                    repo.create_file(file_path_in_repo, f"Adiciona {filename}", file_content)

                data[f'{key}_url'] = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{file_path_in_repo}"

    # Atualiza o ficheiro CSV no GitHub
    try:
        file_content_obj = repo.get_contents(CSV_FILE_PATH)
        csv_content = base64.b64decode(file_content_obj.content).decode('utf-8')
        file_exists = True
    except GithubException:
        csv_content = ""
        file_exists = False

    output = StringIO()
    fieldnames = ['Carimbo de data/hora', 'Protocolo/Assistência', 'Seu nome completo', 'Descrição do serviço executado', 'Senha do cliente', 'Foto do serviço executado', 'Foto da assinatura/documento do cliente']
    writer = csv.DictWriter(output, fieldnames=fieldnames)

    if not file_exists:
        writer.writeheader()

    writer.writerow({
        'Carimbo de data/hora': data['timestamp'],
        'Protocolo/Assistência': data['protocolo'],
        'Seu nome completo': data['nome_tecnico'],
        'Descrição do serviço executado': data['servico_executado'],
        'Senha do cliente': data['senha_cliente'],
        'Foto do serviço executado': data['foto_servico_url'],
        'Foto da assinatura/documento do cliente': data['foto_documento_url']
    })

    new_csv_row = output.getvalue()
    updated_csv_content = csv_content + new_csv_row

    if file_exists:
        repo.update_file(CSV_FILE_PATH, "Adiciona nova resposta ao CSV", updated_csv_content.encode('utf-8'), file_content_obj.sha)
    else:
        repo.create_file(CSV_FILE_PATH, "Cria ficheiro CSV de respostas", updated_csv_content.encode('utf-8'))

    return "<h1>Obrigado!</h1><p>A sua resposta foi enviada com sucesso.</p>"


@app.route('/get-csv')
def get_csv():
    try:
        file_content_obj = repo.get_contents(CSV_FILE_PATH)
        csv_content = base64.b64decode(file_content_obj.content).decode('utf-8')
        return csv_content, 200, {'Content-Type': 'text/csv'}
    except GithubException:
        return "Ficheiro CSV ainda não foi criado.", 404

if __name__ == '__main__':
    app.run(debug=True)
