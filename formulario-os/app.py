import os
import csv
from flask import Flask, request, render_template_string, send_from_directory, jsonify
from werkzeug.utils import secure_filename
import datetime

app = Flask(__name__)

# --- Configuração ---
UPLOAD_FOLDER = 'uploads'
CSV_FILE = 'submissions.csv'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Funções Auxiliares ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Rotas da Aplicação ---

# Rota principal: Exibe o formulário
@app.route('/')
def form():
    # Lê os parâmetros da URL para pré-preencher o formulário
    protocolo = request.args.get('protocolo', '')
    nome_cliente = request.args.get('nome_cliente', '')
    endereco = request.args.get('endereco', '')
    nome_tecnico = request.args.get('nome_tecnico', '')
    
    # Carrega o template HTML e insere os valores
    with open('templates/form.html', 'r', encoding='utf-8') as f:
        template_string = f.read()
    return render_template_string(template_string, 
                                  protocolo=protocolo, 
                                  nome_cliente=nome_cliente, 
                                  endereco=endereco,
                                  nome_tecnico=nome_tecnico)

# Rota para receber os dados do formulário
@app.route('/submit', methods=['POST'])
def submit():
    # Obter dados do formulário
    data = {
        'timestamp': datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
        'protocolo': request.form.get('protocolo'),
        'nome_tecnico': request.form.get('nome_tecnico'),
        'servico_executado': request.form.get('servico_executado'),
        'senha_cliente': request.form.get('senha_cliente'),
        'foto_servico_url': '',
        'foto_documento_url': ''
    }

    # Processar upload de ficheiros
    base_url = request.host_url
    for key in ['foto_servico', 'foto_documento']:
        if key in request.files:
            file = request.files[key]
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(f"{data['protocolo']}_{key}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                data[f'{key}_url'] = f"{base_url}uploads/{filename}"

    # Guardar dados no ficheiro CSV
    file_exists = os.path.isfile(CSV_FILE)
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Carimbo de data/hora', 'Protocolo/Assistência', 'Seu nome completo', 'Descrição do serviço executado', 'Senha do cliente', 'Foto do serviço executado', 'Foto da assinatura/documento do cliente']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
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

    return "<h1>Obrigado!</h1><p>A sua resposta foi enviada com sucesso.</p>"

# Rota para servir os ficheiros de upload
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Rota para o seu programa Python descarregar o CSV
@app.route('/get-csv')
def get_csv():
    if not os.path.exists(CSV_FILE):
        return "Ficheiro CSV ainda não foi criado.", 404
    return send_from_directory(os.getcwd(), CSV_FILE)

if __name__ == '__main__':
    app.run(debug=True)