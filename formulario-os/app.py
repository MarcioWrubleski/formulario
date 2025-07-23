import os
import csv
import base64
from flask import Flask, request, render_template_string, jsonify, Response
from werkzeug.utils import secure_filename
import datetime
from pytz import timezone
from github import Github, GithubException
from io import StringIO

app = Flask(__name__)

# --- Configuração do GitHub e Admin ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD') # Senha para a área de limpeza
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

    for key in ['foto_servico', 'foto_documento']:
        if key in request.files:
            file = request.files[key]
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{data['protocolo']}_{key}_{file.filename}")
                file_content = file.read()
                file_path_in_repo = f"{UPLOAD_FOLDER_PATH}/{filename}"

                try:
                    contents = repo.get_contents(file_path_in_repo)
                    repo.update_file(contents.path, f"Atualiza {filename}", file_content, contents.sha)
                except GithubException:
                    repo.create_file(file_path_in_repo, f"Adiciona {filename}", file_content)

                data[f'{key}_url'] = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{file_path_in_repo}"

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

    new_csv_row = output.getvalue().splitlines()[1] + '\n' if file_exists else output.getvalue()
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
        return Response(csv_content, mimetype='text/csv')
    except GithubException:
        return "Ficheiro CSV ainda não foi criado.", 404

# --- NOVAS ROTAS DE ADMINISTRAÇÃO ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            try:
                file_content_obj = repo.get_contents(CSV_FILE_PATH)
                csv_content = base64.b64decode(file_content_obj.content).decode('utf-8')
                num_lines = len(csv_content.strip().split('\n')) -1
                if num_lines < 0: num_lines = 0
            except GithubException:
                num_lines = 0

            with open('templates/admin.html', 'r', encoding='utf-8') as f:
                template_string = f.read()
            return render_template_string(template_string, num_lines=num_lines)
        else:
            return "Senha incorreta.", 403

    with open('templates/login.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/admin/clear', methods=['POST'])
def clear_csv():
    password = request.form.get('password')
    if password != ADMIN_PASSWORD:
        return "Não autorizado", 403

    try:
        cutoff_date_str = request.form.get('cutoff_date')
        cutoff_date = datetime.datetime.strptime(cutoff_date_str, '%Y-%m-%d').date()

        file_content_obj = repo.get_contents(CSV_FILE_PATH)
        csv_content = base64.b64decode(file_content_obj.content).decode('utf-8')

        reader = csv.reader(StringIO(csv_content))
        header = next(reader)

        kept_rows = []
        deleted_count = 0
        for row in reader:
            try:
                row_date = datetime.datetime.strptime(row[0].split(' ')[0], '%d/%m/%Y').date()
                if row_date >= cutoff_date:
                    kept_rows.append(row)
                else:
                    deleted_count += 1
            except (ValueError, IndexError):
                kept_rows.append(row) # Mantém linhas com formato de data inválido

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(header)
        writer.writerows(kept_rows)
        new_csv_content = output.getvalue()

        repo.update_file(CSV_FILE_PATH, f"Limpeza de {deleted_count} registos antigos", new_csv_content.encode('utf-8'), file_content_obj.sha)

        return f"<h1>Limpeza Concluída</h1><p>{deleted_count} registos anteriores a {cutoff_date_str} foram apagados com sucesso.</p><a href='/admin'>Voltar</a>"

    except Exception as e:
        return f"Ocorreu um erro: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
