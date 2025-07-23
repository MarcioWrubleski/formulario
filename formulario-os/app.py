import os
import csv
import base64
from flask import Flask, request, render_template_string, Response
from werkzeug.utils import secure_filename
import datetime
from pytz import timezone
from github import Github, GithubException
from io import StringIO

app = Flask(__name__)

# --- Configuração do GitHub e Admin ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
CSV_FILE_PATH = 'submissions.csv'
UPLOAD_FOLDER_PATH = 'uploads'

# Validação inicial das variáveis de ambiente
if not all([GITHUB_TOKEN, GITHUB_REPO, ADMIN_PASSWORD]):
    print("ERRO: Variáveis de ambiente GITHUB_TOKEN, GITHUB_REPO, e ADMIN_PASSWORD são obrigatórias.")
    # Esta parte não irá parar o Render, mas irá registar o erro

g = Github(GITHUB_TOKEN)
repo = g.get_repo(GITHUB_REPO)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# --- Templates HTML incorporados ---
FORM_TEMPLATE = """
<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Relatório do Serviço</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;background-color:#f4f4f9;color:#333;margin:0;padding:20px}.container{max-width:700px;margin:auto;background:#fff;padding:20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,.1)}h1{color:#0056b3}.form-group{margin-bottom:15px}label{display:block;margin-bottom:5px;font-weight:700}input[type=text],textarea{width:100%;padding:10px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}input[type=file]{padding:5px}button{background-color:#007bff;color:#fff;padding:12px 20px;border:none;border-radius:4px;cursor:pointer;font-size:16px;width:100%}button:hover{background-color:#0056b3}.readonly{background-color:#e9ecef}.footer{text-align:center;margin-top:25px;font-size:.9em;color:#777}</style></head><body><div class="container"><h1>Relatório do Serviço</h1><form action="/submit" method="post" enctype="multipart/form-data"><div class="form-group"><label for="protocolo">Protocolo/Assistência</label><input type="text" id="protocolo" name="protocolo" value="{{ protocolo }}" class="readonly" readonly></div><div class="form-group"><label for="nome_cliente">Cliente</label><input type="text" id="nome_cliente" name="nome_cliente" value="{{ nome_cliente }}" class="readonly" readonly></div><div class="form-group"><label for="endereco">Endereço</label><input type="text" id="endereco" name="endereco" value="{{ endereco }}" class="readonly" readonly></div><div class="form-group"><label for="nome_tecnico">Seu nome completo</label><input type="text" id="nome_tecnico" name="nome_tecnico" value="{{ nome_tecnico }}" required></div><div class="form-group"><label for="servico_executado">Descrição do serviço executado</label><textarea id="servico_executado" name="servico_executado" rows="6" required></textarea></div><div class="form-group"><label for="senha_cliente">Senha do cliente</label><input type="text" id="senha_cliente" name="senha_cliente"></div><div class="form-group"><label for="foto_servico">Foto do serviço executado</label><input type="file" id="foto_servico" name="foto_servico" accept="image/*" required></div><div class="form-group"><label for="foto_documento">Foto da assinatura/documento do cliente</label><input type="file" id="foto_documento" name="foto_documento" accept="image/*" required></div><button type="submit">Finalizar serviço</button></form><div class="footer"><p>© Wrubleski</p></div></div></body></html>
"""
LOGIN_TEMPLATE = """
<!DOCTYPE html><html lang="pt-BR"><head><title>Admin Login</title><style>body{font-family: sans-serif; background: #f4f4f9;} .login-box{width: 300px; margin: 100px auto; padding: 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center;} input[type="password"]{width: 90%; padding: 10px; margin-top: 10px; margin-bottom: 20px;} button{padding: 10px 20px;}</style></head><body><div class="login-box"><h2>Acesso à Administração</h2><form method="post"><label for="password">Senha:</label><input type="password" id="password" name="password" required><button type="submit">Entrar</button></form></div></body></html>
"""
ADMIN_TEMPLATE = """
<!DOCTYPE html><html lang="pt-BR"><head><title>Admin</title><style>body{font-family: sans-serif; background: #f4f4f9;} .admin-box{width: 500px; margin: 50px auto; padding: 20px; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);} button{padding: 10px 20px; margin-top: 15px;}</style></head><body><div class="admin-box"><h1>Gerir Respostas</h1><p>Atualmente existem <strong>{{ num_lines }}</strong> respostas no ficheiro.</p><hr><h3>Apagar Respostas Antigas</h3><p>Selecione uma data. Todas as respostas <strong>anteriores</strong> a esta data serão apagadas permanentemente.</p><form action="/admin/clear" method="post"><label for="cutoff_date">Apagar registos antes de:</label><input type="date" id="cutoff_date" name="cutoff_date" required><input type="hidden" name="password" value="{{ password }}"><br><button type="submit" onclick="return confirm('Tem a certeza que deseja apagar os registos antigos? Esta ação não pode ser desfeita.')">Apagar Registos Antigos</button></form></div></body></html>
"""

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def form():
    protocolo = request.args.get('protocolo', '')
    nome_cliente = request.args.get('nome_cliente', '')
    endereco = request.args.get('endereco', '')
    nome_tecnico = request.args.get('nome_tecnico', '')

    return render_template_string(FORM_TEMPLATE, 
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

            return render_template_string(ADMIN_TEMPLATE, num_lines=num_lines, password=password)
        else:
            return "Senha incorreta.", 403

    return render_template_string(LOGIN_TEMPLATE)

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
                kept_rows.append(row)

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
